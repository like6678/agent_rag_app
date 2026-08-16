import React, { useEffect, useRef, useState } from 'react';
import {
  Layout,
  Button,
  Input,
  List,
  Card,
  Space,
  Switch,
  Tag,
  Tooltip,
  Empty,
  Spin,
  Popconfirm,
  message,
  Typography,
  theme,
} from 'antd';
import {
  PlusOutlined,
  SendOutlined,
  DeleteOutlined,
  ClearOutlined,
  ReloadOutlined,
  StopOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { chatApi, Session, ToolCallInfo, errorMsg } from '@/services';

const { Sider, Content } = Layout;
const { Text } = Typography;

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  tool_calls?: ToolCallInfo[];
  pending?: boolean; // 流式生成中
}

const Chat: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [useRag, setUseRag] = useState(true);
  const [userId, setUserId] = useState('user-001');
  const [streamMode, setStreamMode] = useState(true);
  const [sending, setSending] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const msgsEndRef = useRef<HTMLDivElement>(null);
  const { token } = theme.useToken();

  // 直接更新消息列表最后一条(流式时逐段追加, 消息始终在列表里, 不存在"结束后再补写"导致丢失)
  const patchLast = (patch: Partial<Msg> | ((m: Msg) => Msg)) => {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const last = prev[prev.length - 1];
      const next = typeof patch === 'function' ? patch(last) : { ...last, ...patch };
      return [...prev.slice(0, -1), next];
    });
  };
  const appendMessage = (m: Msg) => setMessages((prev) => [...prev, m]);
  const loadSessions = async () => {
    setLoadingSessions(true);
    try {
      const r = await chatApi.listSessions();
      setSessions(r.sessions);
    } catch (e) {
      errorMsg(e);
    } finally {
      setLoadingSessions(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    msgsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const selectSession = async (sid: string) => {
    setCurrent(sid);
    setLoadingHistory(true);
    setMessages([]);
    try {
      const r = await chatApi.history(sid);
      setMessages(
        (r.messages || [])
          .filter((m) => m.role === 'user' || m.role === 'assistant')
          .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })),
      );
    } catch (e) {
      errorMsg(e);
    } finally {
      setLoadingHistory(false);
    }
  };

  const onNewSession = async () => {
    try {
      const r = await chatApi.newSession();
      const s: Session = {
        session_id: r.session_id,
        title: '新对话',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        message_count: 0,
      };
      setSessions((prev) => [s, ...prev]);
      setCurrent(r.session_id);
      setMessages([]);
    } catch (e) {
      errorMsg(e);
    }
  };
  const onDeleteSession = async (sid: string) => {
    try {
      await chatApi.deleteSession(sid);
      setSessions((prev) => prev.filter((s) => s.session_id !== sid));
      if (current === sid) {
        setCurrent(null);
        setMessages([]);
      }
      message.success('会话已删除');
    } catch (e) {
      errorMsg(e);
    }
  };

  const onClearMemory = async () => {
    if (!current) return;
    try {
      await chatApi.clearMemory(current);
      setMessages([]);
      message.success('会话记忆已清空');
    } catch (e) {
      errorMsg(e);
    }
  };

  const stopGenerate = () => abortRef.current?.abort();

  // 流式对话: 收到 content 增量就原地追加到最后一条助手消息
  const streamChat = async (req: {
    session_id: string;
    message: string;
    use_rag: boolean;
    user_id?: string;
  }) => {
    const controller = new AbortController();
    abortRef.current = controller;
    const res = await fetch(chatApi.streamUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) {
      const t = await res.text().catch(() => '');
      throw new Error('流式请求失败: ' + (t || res.statusText));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const t = line.trim();
          if (!t.startsWith('data:')) continue;
          const data = t.slice(5).trim();
          if (data === '[DONE]') return;
          if (controller.signal.aborted) return;
          try {
            const obj = JSON.parse(data);
            if (obj.type === 'tool_calls') {
              patchLast({ tool_calls: obj.tool_calls || [] });
            } else if (obj.type === 'content') {
              const chunk: string = obj.content || '';
              patchLast((m) => ({ ...m, content: m.content + chunk }));
            } else if (obj.type === 'error') {
              throw new Error(obj.message || '流式错误');
            }
          } catch (e) {
            if (e instanceof Error && e.message.startsWith('流式')) throw e;
          }
        }
      }
    } finally {
      abortRef.current = null;
    }
  };
  const onSend = async () => {
    if (!current) {
      message.warning('请先创建或选择一个会话');
      return;
    }
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    appendMessage({ role: 'user', content: text });
    // 先创建一条空的助手消息, 流式过程中原地追加内容(ChatGPT 同款模式)
    appendMessage({ role: 'assistant', content: '', pending: true });
    setSending(true);
    try {
      if (streamMode) {
        await streamChat({ session_id: current, message: text, use_rag: useRag, user_id: userId });
      } else {
        const r = await chatApi.chat({ session_id: current, message: text, use_rag: useRag, user_id: userId });
        patchLast({ content: r.answer, tool_calls: r.tool_calls_made });
      }
      loadSessions();
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === 'AbortError';
      patchLast((m) => ({
        ...m,
        content: aborted ? m.content || '(已停止)' : '⚠️ ' + (e instanceof Error ? e.message : '请求失败'),
      }));
    } finally {
      patchLast((m) => {
        if (m.role !== 'assistant') return m;
        const content =
          m.content ||
          (m.tool_calls && m.tool_calls.length ? '(已调用工具, 无文本回复)' : '(空回复)');
        return { ...m, content, pending: false };
      });
      setSending(false);
    }
  };

  const renderMessage = (m: Msg, idx: number) => {
    if (m.role === 'user') {
      return (
        <div key={idx} className="chat-row user">
          <div className="chat-bubble user">{m.content}</div>
        </div>
      );
    }
    return (
      <div key={idx} className="chat-row assistant">
        <div style={{ maxWidth: 780, width: '100%' }}>
          <div className="chat-meta">
            <RobotOutlined style={{ marginRight: 6 }} />
            助手
            {m.pending && (
              <Tag color="processing" style={{ marginLeft: 8 }}>
                生成中
              </Tag>
            )}
          </div>
          {m.tool_calls && m.tool_calls.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              {m.tool_calls.map((tc, i) => (
                <Card key={i} size="small" className="tool-card" title={`🔧 ${tc.name}`}>
                  <Text code>{JSON.stringify(tc.arguments)}</Text>
                  <div style={{ color: token.colorTextSecondary, marginTop: 4 }}>{tc.result_preview}</div>
                </Card>
              ))}
            </div>
          )}
          <div className={'chat-bubble assistant' + (m.pending ? ' pending' : '')}>
            {m.content}
            {m.pending && <span className="stream-cursor" />}
          </div>
        </div>
      </div>
    );
  };
  return (
    <Layout className="chat-layout">
      <Sider
        width={240}
        theme="dark"
        style={{
          background: 'transparent',
          borderRight: '1px solid ' + token.colorBorderSecondary,
          overflow: 'auto',
        }}
      >
        <div style={{ padding: 12 }}>
          <Button type="primary" block icon={<PlusOutlined />} onClick={onNewSession}>
            新建对话
          </Button>
        </div>
        <Spin spinning={loadingSessions}>
          {sessions.length === 0 ? (
            <Empty description="暂无会话" style={{ marginTop: 40 }} />
          ) : (
            <List
              dataSource={sessions}
              renderItem={(s) => (
                <List.Item
                  style={{
                    cursor: 'pointer',
                    padding: '10px 12px',
                    background: current === s.session_id ? 'rgba(34,211,238,0.12)' : 'transparent',
                    border: 'none',
                    borderRadius: 8,
                    margin: '0 8px',
                  }}
                  onClick={() => selectSession(s.session_id)}
                  actions={[
                    <Popconfirm
                      key="del"
                      title="删除该会话？"
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        onDeleteSession(s.session_id);
                      }}
                    >
                      <DeleteOutlined onClick={(e) => e.stopPropagation()} />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Text ellipsis style={{ maxWidth: 140 }}>
                        {s.title}
                      </Text>
                    }
                    description={
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {s.message_count} 条 · {s.updated_at?.replace('T', ' ').slice(5, 16)}
                      </Text>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Spin>
      </Sider>
      <Content style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div
          style={{
            padding: '8px 16px',
            borderBottom: '1px solid ' + token.colorBorderSecondary,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 8,
          }}
        >
          <Space size={12}>
            <Tooltip title="用户ID：提供后对话会自动注入该用户的长期记忆">
              <Input
                size="small"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="用户ID"
                style={{ width: 110 }}
                prefix={<span style={{ color: token.colorTextSecondary }}>👤</span>}
              />
            </Tooltip>
            <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>RAG</span>
            <Switch checked={useRag} onChange={setUseRag} size="small" />
            <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>流式</span>
            <Switch checked={streamMode} onChange={setStreamMode} size="small" />
          </Space>
          <Space size={8}>
            {current && (
              <Tooltip title="清空当前会话记忆（不删除会话）">
                <Button size="small" icon={<ClearOutlined />} onClick={onClearMemory}>
                  清空
                </Button>
              </Tooltip>
            )}
            <Button size="small" icon={<ReloadOutlined />} onClick={loadSessions} />
          </Space>
        </div>
        <div className="chat-msgs" style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
          <div style={{ width: '100%', maxWidth: 800 }}>
            {!current ? (
              <Empty description="请选择或新建一个会话" style={{ marginTop: 80 }} />
            ) : loadingHistory ? (
              <div style={{ textAlign: 'center', marginTop: 80 }}>
                <Spin />
              </div>
            ) : messages.length === 0 ? (
              <div style={{ textAlign: 'center', marginTop: 80 }}>
                <RobotOutlined style={{ fontSize: 40, color: token.colorPrimary }} />
                <div style={{ marginTop: 12, color: token.colorTextSecondary }}>有什么可以帮你的？</div>
              </div>
            ) : (
              messages.map(renderMessage)
            )}
            <div ref={msgsEndRef} />
          </div>
        </div>
        <div
          style={{
            padding: '12px 16px 16px',
            borderTop: '1px solid ' + token.colorBorderSecondary,
            display: 'flex',
            justifyContent: 'center',
          }}
        >
          <div style={{ width: '100%', maxWidth: 800 }}>
            <Space.Compact style={{ width: '100%' }}>
              <Input.TextArea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={current ? '输入消息，Enter 发送，Shift+Enter 换行' : '请先选择会话'}
                autoSize={{ minRows: 1, maxRows: 4 }}
                disabled={!current || sending}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault();
                    onSend();
                  }
                }}
              />
              {sending ? (
                <Button type="primary" danger icon={<StopOutlined />} onClick={stopGenerate}>
                  停止
                </Button>
              ) : (
                <Button type="primary" icon={<SendOutlined />} onClick={onSend} disabled={!current}>
                  发送
                </Button>
              )}
            </Space.Compact>
            <div
              style={{
                textAlign: 'center',
                marginTop: 6,
                color: token.colorTextTertiary,
                fontSize: 12,
              }}
            >
              知识库检索增强 · 长期记忆 · 流式输出
            </div>
          </div>
        </div>
      </Content>
    </Layout>
  );
};

export default Chat;
