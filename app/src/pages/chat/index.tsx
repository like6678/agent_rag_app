/**
 * 智能对话页 - SSE 流式输出 + 历史会话列表
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Avatar,
  Button,
  Input,
  Space,
  Switch,
  Tooltip,
  Typography,
  Spin,
  Empty,
  Tag,
  List,
  Popconfirm,
  message,
} from 'antd';
import {
  UserOutlined,
  RobotOutlined,
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ChatRequest,
  ChatMessage,
  ToolCallInfo,
  SessionInfo,
  chatStream,
  getChatHistory,
  createSession,
  deleteSession as apiDeleteSession,
  listSessions,
  clearSession,
} from '@/services/api';

const { Text } = Typography;

const STORAGE_KEY = 'agent_rag_current_session';

interface DisplayMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  tool_calls?: ToolCallInfo[];
  streaming?: boolean;
}

const ChatPage: React.FC = () => {
  const [sessionId, setSessionId] = useState<string>('');
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [useRag, setUseRag] = useState(true);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /** 加载会话列表 */
  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const res = await listSessions();
      setSessions(res.sessions || []);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  /** 初始化: 加载会话列表 + 恢复上次会话 */
  useEffect(() => {
    loadSessions();
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      setSessionId(saved);
      loadHistory(saved);
    }
  }, []);

  /** 加载会话历史 */
  const loadHistory = async (sid: string) => {
    setLoadingHistory(true);
    try {
      const res = await getChatHistory(sid);
      const history = (res.messages || []).map((m: ChatMessage) => ({
        role: m.role as DisplayMessage['role'],
        content: m.content || '',
      }));
      setMessages(history);
    } catch {
      setMessages([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  /** 新建对话 */
  const handleNewSession = async () => {
    try {
      const res = await createSession('新对话');
      setSessionId(res.session_id);
      setMessages([]);
      localStorage.setItem(STORAGE_KEY, res.session_id);
      await loadSessions();
    } catch (err: any) {
      message.error(`创建会话失败: ${err?.message || '未知错误'}`);
    }
  };

  /** 切换会话 */
  const handleSwitchSession = async (sid: string) => {
    setSessionId(sid);
    localStorage.setItem(STORAGE_KEY, sid);
    await loadHistory(sid);
  };

  /** 删除会话 */
  const handleDeleteSession = async (sid: string) => {
    try {
      await apiDeleteSession(sid);
      if (sid === sessionId) {
        setSessionId('');
        setMessages([]);
        localStorage.removeItem(STORAGE_KEY);
      }
      await loadSessions();
      message.success('会话已删除');
    } catch (err: any) {
      message.error(`删除失败: ${err?.message || '未知错误'}`);
    }
  };

  /** 清空当前会话记忆 */
  const handleClear = async () => {
    if (!sessionId) return;
    try {
      await clearSession(sessionId);
      setMessages([]);
      message.success('会话记忆已清空');
    } catch {
      // ignore
    }
  };

  /** 发送消息(流式) */
  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    // 如果没有 session_id, 先创建
    let sid = sessionId;
    if (!sid) {
      try {
        const res = await createSession(text.slice(0, 30));
        sid = res.session_id;
        setSessionId(sid);
        localStorage.setItem(STORAGE_KEY, sid);
        await loadSessions();
      } catch (err: any) {
        message.error(`创建会话失败: ${err?.message || '未知错误'}`);
        return;
      }
    }

    // 显示用户消息
    const userMsg: DisplayMessage = { role: 'user', content: text };
    // 显示助手占位(流式)
    const assistantMsg: DisplayMessage = { role: 'assistant', content: '', streaming: true };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setLoading(true);

    const req: ChatRequest = { session_id: sid, message: text, use_rag: useRag };

    await chatStream(req, {
      onContent: (content) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant') {
            last.content += content;
          }
          return updated;
        });
      },
      onToolCalls: (toolCalls) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant') {
            last.tool_calls = toolCalls;
          }
          return updated;
        });
      },
      onFinish: () => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant') {
            last.streaming = false;
          }
          return updated;
        });
      },
      onError: (error) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant') {
            last.content = `⚠️ 请求失败: ${error}`;
            last.streaming = false;
          }
          return updated;
        });
      },
    });

    setLoading(false);
    // 刷新会话列表(标题/消息数可能更新)
    loadSessions();
  };

  /** 渲染单条消息 */
  const renderMessage = (msg: DisplayMessage, index: number) => {
    const isUser = msg.role === 'user';
    return (
      <div className={`chat-message ${isUser ? 'user' : 'assistant'}`} key={index}>
        <Avatar
          className="chat-avatar"
          icon={isUser ? <UserOutlined /> : <RobotOutlined />}
          style={{ backgroundColor: isUser ? '#1677ff' : '#52c41a' }}
        />
        <div className="chat-bubble">
          {msg.role === 'assistant' ? (
            msg.content ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            ) : msg.streaming ? (
              <Spin size="small" /> 
            ) : (
              <Text type="secondary">(空回复)</Text>
            )
          ) : (
            <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
          )}
          {msg.streaming && msg.content && (
            <span style={{ display: 'inline-block', width: 8, height: 16, background: '#1677ff', marginLeft: 2, animation: 'blink 1s infinite', verticalAlign: 'text-bottom' }} />
          )}
          {msg.tool_calls && msg.tool_calls.length > 0 && (
            <div className="chat-tool-calls">
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {msg.tool_calls.map((tc, i) => (
                  <div key={i}>
                    <Tag icon={<MessageOutlined />} color="blue">{tc.name}</Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {tc.result_preview?.slice(0, 120)}
                      {(tc.result_preview?.length || 0) > 120 ? '...' : ''}
                    </Text>
                  </div>
                ))}
              </Space>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 64px)', background: '#f5f5f5' }}>
      {/* 左侧: 历史会话列表 */}
      <div style={{ width: 260, background: '#fff', borderRight: '1px solid #e8e8e8', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: 12, borderBottom: '1px solid #e8e8e8' }}>
          <Button type="primary" block icon={<PlusOutlined />} onClick={handleNewSession}>
            新建对话
          </Button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <Spin spinning={loadingSessions}>
            {sessions.length === 0 ? (
              <Empty style={{ marginTop: 40 }} description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                dataSource={sessions}
                renderItem={(s) => (
                  <List.Item
                    style={{
                      padding: '10px 12px',
                      cursor: 'pointer',
                      background: s.session_id === sessionId ? '#e6f4ff' : 'transparent',
                      borderLeft: s.session_id === sessionId ? '3px solid #1677ff' : '3px solid transparent',
                    }}
                    onClick={() => handleSwitchSession(s.session_id)}
                    actions={[
                      <Popconfirm
                        key="del"
                        title="删除此会话?"
                        onConfirm={(e) => { e?.stopPropagation(); handleDeleteSession(s.session_id); }}
                      >
                        <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={<Text ellipsis style={{ maxWidth: 160 }}>{s.title || '新对话'}</Text>}
                      description={
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {s.message_count} 条消息 · {s.updated_at?.slice(5, 16).replace('T', ' ')}
                        </Text>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Spin>
        </div>
      </div>

      {/* 右侧: 对话区域 */}
      <div className="chat-container" style={{ flex: 1 }}>
        {/* 顶部工具栏 */}
        <div style={{ padding: '8px 16px', background: '#fff', borderBottom: '1px solid #e8e8e8', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Text strong>当前会话:</Text>
            <Text type="secondary" copyable style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {sessionId ? sessionId.slice(0, 8) + '...' : '未创建'}
            </Text>
          </Space>
          <Space>
            <Tooltip title="启用后自动检索知识库">
              <Space>
                <Text>RAG 检索</Text>
                <Switch checked={useRag} onChange={setUseRag} size="small" />
              </Space>
            </Tooltip>
            <Tooltip title="清空当前会话记忆">
              <Button size="small" icon={<DeleteOutlined />} onClick={handleClear} disabled={!sessionId} />
            </Tooltip>
          </Space>
        </div>

        {/* 消息列表 */}
        <div className="chat-messages" style={{ flex: 1 }}>
          {loadingHistory ? (
            <div style={{ textAlign: 'center', marginTop: 80 }}>
              <Spin tip="加载历史..." />
            </div>
          ) : messages.length === 0 ? (
            <Empty style={{ marginTop: 80 }} description="开始一段新对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            messages.map(renderMessage)
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区 */}
        <div className="chat-input-area">
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="输入消息, Enter 发送, Shift+Enter 换行"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading}
          />
          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
            <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading} disabled={!input.trim()}>
              发送
            </Button>
          </div>
        </div>
      </div>

      <style>{`@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }`}</style>
    </div>
  );
};

export default ChatPage;
