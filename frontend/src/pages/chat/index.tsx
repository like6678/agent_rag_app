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
} from 'antd';
import {
  PlusOutlined,
  SendOutlined,
  DeleteOutlined,
  ClearOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { chatApi, Session, ToolCallInfo, errorMsg } from '@/services';

const { Sider, Content } = Layout;
const { Text } = Typography;

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  tool_calls?: ToolCallInfo[];
}

const Chat: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [useRag, setUseRag] = useState(true);
  const [streaming, setStreaming] = useState(true);
  const [sending, setSending] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const [streamText, setStreamText] = useState('');
  const [streamTools, setStreamTools] = useState<ToolCallInfo[]>([]);
  const streamTextRef = useRef('');
  const streamToolsRef = useRef<ToolCallInfo[]>([]);
  const msgsEndRef = useRef<HTMLDivElement>(null);

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
  }, [messages, streamText]);

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

  const streamChat = async (req: { session_id: string; message: string; use_rag: boolean }) => {
    const res = await fetch(chatApi.streamUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok || !res.body) {
      const txt = await res.text().catch(() => '');
      throw new Error('流式请求失败: ' + (txt || res.statusText));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
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
        try {
          const obj = JSON.parse(data);
          if (obj.type === 'tool_calls') {
            setStreamTools(obj.tool_calls || []);
            streamToolsRef.current = obj.tool_calls || [];
          } else if (obj.type === 'content') {
            setStreamText((p) => p + (obj.content || ''));
            streamTextRef.current += obj.content || '';
          } else if (obj.type === 'error') {
            throw new Error(obj.message || '流式错误');
          }
        } catch (e) {
          if (e instanceof Error && e.message) {
            // rethrow real errors (from throw above)
            if (e.message.startsWith('流式') || e.message.startsWith('流式错误')) throw e;
          }
        }
      }
    }
  };

  const onSend = async () => {
    if (!current) {
      message.warning('请先创建或选择一个会话');
      return;
    }
    const text = input.trim();
    if (!text) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setSending(true);
    setStreamText('');
    setStreamTools([]);
    streamTextRef.current = '';
    streamToolsRef.current = [];

    try {
      if (streaming) {
        await streamChat({ session_id: current, message: text, use_rag: useRag });
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: streamTextRef.current || '(空回复)', tool_calls: streamToolsRef.current },
        ]);
      } else {
        const r = await chatApi.chat({ session_id: current, message: text, use_rag: useRag });
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: r.answer, tool_calls: r.tool_calls_made },
        ]);
      }
      loadSessions();
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '⚠️ ' + (e instanceof Error ? e.message : '请求失败') },
      ]);
    } finally {
      setStreamText('');
      setStreamTools([]);
      streamTextRef.current = '';
      streamToolsRef.current = [];
      setSending(false);
    }
  };

  const renderBubble = (m: Msg, idx: number) => (
    <div key={idx} className={`chat-row ${m.role}`}>
      <div style={{ maxWidth: '75%' }}>
        <div className={`chat-meta`}>{m.role === 'user' ? '我' : '助手'}</div>
        {m.role === 'assistant' && m.tool_calls && m.tool_calls.length > 0 && (
          <div>
            {m.tool_calls.map((tc, i) => (
              <Card key={i} size="small" className="tool-card" title={`🔧 ${tc.name}`}>
                <div>
                  <Text type="secondary">参数：</Text>
                  <Text code>{JSON.stringify(tc.arguments)}</Text>
                </div>
                <div style={{ marginTop: 4, color: '#666' }}>
                  <Text type="secondary">结果：</Text>
                  {tc.result_preview}
                </div>
              </Card>
            ))}
          </div>
        )}
        <div className={`chat-bubble ${m.role}`}>{m.content}</div>
      </div>
    </div>
  );

  return (
    <Layout className="chat-layout">
      <Sider width={260} theme="light" style={{ borderRight: '1px solid #f0f0f0', overflow: 'auto' }}>
        <div style={{ padding: 12 }}>
          <Button type="primary" block icon={<PlusOutlined />} onClick={onNewSession}>
            新建会话
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
                    background: current === s.session_id ? '#e6f4ff' : 'transparent',
                    border: 'none',
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
                    title={<Text ellipsis style={{ maxWidth: 150 }}>{s.title}</Text>}
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

      <Content style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0', background: '#fafafa' }}>
          <Space>
            <span>RAG 检索增强</span>
            <Switch checked={useRag} onChange={setUseRag} size="small" />
            <span style={{ marginLeft: 16 }}>流式输出</span>
            <Switch checked={streaming} onChange={setStreaming} size="small" />
            {current && (
              <Tooltip title="清空当前会话记忆（不删除会话）">
                <Button size="small" icon={<ClearOutlined />} onClick={onClearMemory}>
                  清空记忆
                </Button>
              </Tooltip>
            )}
            <Button size="small" icon={<ReloadOutlined />} onClick={loadSessions} />
          </Space>
        </div>

        <div className="chat-msgs" style={{ flex: 1 }}>
          {!current ? (
            <Empty description="请选择或新建一个会话" style={{ marginTop: 80 }} />
          ) : loadingHistory ? (
            <div style={{ textAlign: 'center', marginTop: 80 }}>
              <Spin />
            </div>
          ) : (
            <>
              {messages.map(renderBubble)}
              {sending && (
                <div className="chat-row assistant">
                  <div style={{ maxWidth: '75%' }}>
                    <div className="chat-meta">助手{streaming && <Tag color="processing" style={{ marginLeft: 8 }}>生成中</Tag>}</div>
                    {streamTools.length > 0 && (
                      <div>
                        {streamTools.map((tc, i) => (
                          <Card key={i} size="small" className="tool-card" title={`🔧 ${tc.name}`}>
                            <Text code>{JSON.stringify(tc.arguments)}</Text>
                            <div style={{ color: '#666', marginTop: 4 }}>{tc.result_preview}</div>
                          </Card>
                        ))}
                      </div>
                    )}
                    <div className="chat-bubble assistant">
                      {streamText || <Spin size="small" />}
                    </div>
                  </div>
                </div>
              )}
              <div ref={msgsEndRef} />
            </>
          )}
        </div>

        <div style={{ padding: 12, borderTop: '1px solid #f0f0f0', background: '#fff' }}>
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
            <Button type="primary" icon={<SendOutlined />} onClick={onSend} loading={sending} disabled={!current}>
              发送
            </Button>
          </Space.Compact>
        </div>
      </Content>
    </Layout>
  );
};

export default Chat;