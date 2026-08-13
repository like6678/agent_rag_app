/**
 * 后端 API 封装
 * 对应后端 FastAPI 接口
 */
import { request } from '@umijs/max';

// ==================== 类型定义 ====================

/** 对话请求 */
export interface ChatRequest {
  session_id: string;
  message: string;
  use_rag?: boolean;
}

/** 工具调用信息 */
export interface ToolCallInfo {
  name: string;
  arguments: Record<string, any>;
  result_preview: string;
}

/** 对话响应 */
export interface ChatResponse {
  session_id: string;
  answer: string;
  tool_calls_made: ToolCallInfo[];
}

/** 会话信息 */
export interface SessionInfo {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/** 会话历史消息 */
export interface ChatMessage {
  role: string;
  content: string;
  [key: string]: any;
}

/** 文档信息 */
export interface DocumentInfo {
  doc_id: string;
  filename: string;
  md5: string;
  object_name: string;
  file_size: number;
  content_type: string;
  char_count: number;
  chunk_count: number;
  vector_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

/** 文档上传结果 */
export interface UploadResult {
  doc_id: string;
  filename: string;
  object_name: string;
  md5: string;
  file_size: number;
  char_count: number;
  chunk_count: number;
  vector_count: number;
  duplicated: boolean;
  message: string;
}

/** 知识库统计 */
export interface KBStats {
  collection: string;
  num_entities: number;
}

/** 健康检查响应 */
export interface HealthData {
  status: string;
  milvus: string;
  minio: string;
  memory_backend: string;
}

/** 检索结果项 */
export interface SearchResultItem {
  id: string;
  score: number;
  text: string;
  doc_id: string;
  source: string;
  chunk_index: number;
}

// ==================== 对话接口 ====================

/** 多轮对话 */
export async function chat(data: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    data,
  });
}

/** 获取会话历史 */
export async function getChatHistory(
  sessionId: string,
): Promise<{ session_id: string; messages: ChatMessage[] }> {
  return request(`/api/chat/history/${sessionId}`, { method: 'GET' });
}

/** 清空会话记忆 */
export async function clearSession(
  sessionId: string,
): Promise<{ session_id: string; message: string }> {
  return request(`/api/chat/${sessionId}`, { method: 'DELETE' });
}

/** 生成新会话ID */
export async function newSession(): Promise<{ session_id: string }> {
  return request('/api/chat/new-session', { method: 'POST' });
}

/** 流式对话回调 */
export interface StreamCallbacks {
  onContent?: (content: string) => void;
  onToolCalls?: (toolCalls: ToolCallInfo[]) => void;
  onFinish?: (finishReason: string) => void;
  onError?: (error: string) => void;
}

/**
 * SSE 流式对话
 * 用 fetch + ReadableStream 解析 SSE, 逐 token 回调
 */
export async function chatStream(
  data: ChatRequest,
  callbacks: StreamCallbacks,
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const err = await response.text();
    callbacks.onError?.(err || `HTTP ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.('无法获取响应流');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // 按行解析 SSE
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const dataStr = line.slice(5).trim();
        if (dataStr === '[DONE]') return;
        try {
          const msg = JSON.parse(dataStr);
          if (msg.type === 'content') {
            callbacks.onContent?.(msg.content || '');
          } else if (msg.type === 'tool_calls') {
            callbacks.onToolCalls?.(msg.tool_calls || []);
          } else if (msg.type === 'finish') {
            callbacks.onFinish?.(msg.finish_reason || 'stop');
          } else if (msg.type === 'error') {
            callbacks.onError?.(msg.message || '未知错误');
          }
        } catch {
          // 忽略解析错误
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ==================== 会话管理接口 ====================

/** 获取会话列表 */
export async function listSessions(): Promise<{
  total: number;
  sessions: SessionInfo[];
}> {
  return request('/api/chat/sessions', { method: 'GET' });
}

/** 创建新会话 */
export async function createSession(
  title?: string,
): Promise<SessionInfo> {
  return request('/api/chat/sessions', {
    method: 'POST',
    data: { title: title || '新对话' },
  });
}

/** 更新会话标题 */
export async function updateSessionTitle(
  sessionId: string,
  title: string,
): Promise<{ session_id: string; title: string }> {
  return request(`/api/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    data: { title },
  });
}

/** 删除会话(元数据 + 记忆) */
export async function deleteSession(
  sessionId: string,
): Promise<{ session_id: string; message: string }> {
  return request(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' });
}

// ==================== 文档接口 ====================

/** 上传文档(multipart, 自动 MD5 去重) */
export async function uploadDocument(
  file: File,
  splitMethod?: string,
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  if (splitMethod) {
    formData.append('split_method', splitMethod);
  }
  return request<UploadResult>('/api/documents/upload', {
    method: 'POST',
    data: formData,
    requestType: 'form',
  });
}

/** 列出所有文档 */
export async function listDocuments(): Promise<{
  total: number;
  documents: DocumentInfo[];
}> {
  return request('/api/documents', { method: 'GET' });
}

/** 查询单个文档详情 */
export async function getDocument(docId: string): Promise<DocumentInfo> {
  return request(`/api/documents/${docId}`, { method: 'GET' });
}

/** 下载文档(返回 blob) */
export function downloadDocumentUrl(docId: string): string {
  return `/api/documents/${docId}/download`;
}

/** 在线预览文档 URL */
export function previewDocumentUrl(docId: string): string {
  return `/api/documents/${docId}/preview`;
}

/** 删除文档 */
export async function deleteDocument(
  docId: string,
): Promise<{ doc_id: string; filename: string; deleted_vectors: number; message: string }> {
  return request(`/api/documents/${docId}`, { method: 'DELETE' });
}

// ==================== 知识库接口 ====================

/** 知识库统计 */
export async function getKBStats(): Promise<KBStats> {
  return request('/api/kb/stats', { method: 'GET' });
}

/** 清空知识库(重建集合) */
export async function resetCollection(): Promise<{
  message: string;
  cleared_documents: number;
  collection: string;
}> {
  return request('/api/kb/collection', { method: 'DELETE' });
}

/** 检索测试 */
export async function searchKnowledge(
  query: string,
  top_k: number = 4,
): Promise<{ query: string; total: number; results: SearchResultItem[] }> {
  return request('/api/kb/search', {
    method: 'POST',
    data: { query, top_k },
  });
}

// ==================== 健康检查 ====================

export async function healthCheck(): Promise<{
  status: string;
  milvus: string;
  minio: string;
  memory_backend: string;
}> {
  return request('/health', { method: 'GET' });
}

// ==================== 配置接口 ====================

/** RAG 配置 */
export interface RAGConfig {
  chunk_size: number;
  chunk_overlap: number;
  split_method: string;
  retrieval_top_k: number;
  search_metric: string;
  nprobe: number;
  rerank_enabled: boolean;
  rerank_top_k: number;
  rerank_model: string;
  dashscope_api_key: string;
  dashscope_chat_model: string;
  dashscope_embed_model: string;
  temperature: number;
  max_tool_iterations: number;
  embed_dim: number;
  index_type: string;
  nlist: number;
}

/** 配置选项项 */
export interface ConfigOption {
  value: string | number;
  label: string;
  desc?: string;
}

/** 获取配置 */
export async function getConfig(): Promise<{
  config: RAGConfig;
  options: Record<string, any>;
  defaults: RAGConfig;
}> {
  return request('/api/config', { method: 'GET' });
}

/** 更新配置 */
export async function updateConfig(
  updates: Partial<RAGConfig>,
): Promise<{ message: string; updated_fields: string[]; config: RAGConfig }> {
  return request('/api/config', { method: 'PUT', data: updates });
}

/** 重置配置 */
export async function resetConfig(): Promise<{ message: string; config: RAGConfig }> {
  return request('/api/config/reset', { method: 'POST' });
}

// ==================== 评测接口 ====================

/** 评测测试项 */
export interface EvalTestItem {
  question: string;
  expected_answer?: string;
  expected_source?: string;
}

/** 维度评分 */
export interface EvalDimensionScore {
  name: string;
  score: number;
  detail: string;
}

/** 评测结果项 */
export interface EvalResultItem {
  question: string;
  expected_answer: string;
  retrieved_context: string;
  generated_answer: string;
  recall_hit: boolean;
  context_relevance: number;
  answer_faithfulness: number;
  answer_relevance: number;
}

/** 评测报告 */
export interface EvalReport {
  total: number;
  recall_rate: number;
  avg_context_relevance: number;
  avg_answer_faithfulness: number;
  avg_answer_relevance: number;
  overall_score: number;
  dimensions: EvalDimensionScore[];
  items: EvalResultItem[];
  config_snapshot: Record<string, any>;
}

/** 执行评测 */
export async function runEvaluation(
  testItems: EvalTestItem[],
  useCurrentConfig = true,
  overrideConfig?: Partial<RAGConfig>,
): Promise<EvalReport> {
  return request('/api/evaluation/run', {
    method: 'POST',
    data: {
      test_items: testItems,
      use_current_config: useCurrentConfig,
      override_config: overrideConfig,
    },
  });
}
