import { message } from 'antd';

/* ============ HTTP 基础封装 ============ */
export async function http<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (!(options?.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(url, { ...options, headers: { ...headers, ...(options?.headers as any) } });
  const text = await res.text();
  let data: any = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!res.ok) {
    const detail = data?.detail || data?.message || res.statusText;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data as T;
}

/* ============ 通用类型 ============ */
export interface ToolCallInfo {
  name: string;
  arguments: Record<string, any>;
  result_preview: string;
}
export interface ChatMessage {
  role: string;
  content: string;
}
export interface Session {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/* ============ 对话 ============ */
export interface ChatRequest {
  session_id: string;
  message: string;
  use_rag: boolean;
}
export interface ChatResponse {
  session_id: string;
  answer: string;
  tool_calls_made: ToolCallInfo[];
}

export const chatApi = {
  listSessions: () => http<{ total: number; sessions: Session[] }>('/api/chat/sessions'),
  newSession: () =>
    http<{ session_id: string }>('/api/chat/new-session', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  createSession: (title: string) =>
    http<Session>('/api/chat/sessions', { method: 'POST', body: JSON.stringify({ title }) }),
  updateSession: (session_id: string, title: string) =>
    http<any>(`/api/chat/sessions/${session_id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteSession: (session_id: string) =>
    http<any>(`/api/chat/sessions/${session_id}`, { method: 'DELETE' }),
  history: (session_id: string) =>
    http<{ session_id: string; messages: ChatMessage[] }>(`/api/chat/history/${session_id}`),
  clearMemory: (session_id: string) =>
    http<any>(`/api/chat/${session_id}`, { method: 'DELETE' }),
  chat: (req: ChatRequest) =>
    http<ChatResponse>('/api/chat', { method: 'POST', body: JSON.stringify(req) }),
  streamUrl: '/api/chat/stream',
};

/* ============ 文档 ============ */
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
export interface DocumentProcessResult {
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

export const docApi = {
  list: () => http<{ total: number; documents: DocumentInfo[] }>('/api/documents'),
  get: (doc_id: string) => http<DocumentInfo>(`/api/documents/${doc_id}`),
  remove: (doc_id: string) =>
    http<{ doc_id: string; filename: string; deleted_vectors: number; message: string }>(
      `/api/documents/${doc_id}`,
      { method: 'DELETE' },
    ),
  uploadUrl: '/api/documents/upload',
  previewUrl: (doc_id: string) => `/api/documents/${doc_id}/preview`,
  downloadUrl: (doc_id: string) => `/api/documents/${doc_id}/download`,
};

/* ============ 知识库 ============ */
export interface KBStats {
  collection: string;
  num_entities: number;
}
export interface KBHit {
  id: string;
  score: number;
  text: string;
  doc_id: string;
  source: string;
  chunk_index: number;
}

export const kbApi = {
  stats: () => http<KBStats>('/api/kb/stats'),
  search: (query: string, top_k = 4) =>
    http<{ query: string; total: number; results: KBHit[] }>('/api/kb/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k }),
    }),
  reset: () =>
    http<{ message: string; cleared_documents: number; collection: string }>(
      '/api/kb/collection',
      { method: 'DELETE' },
    ),
};

/* ============ 配置 ============ */
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
  dashscope_base_url: string;
  dashscope_chat_model: string;
  dashscope_embed_model: string;
  temperature: number;
  max_tool_iterations: number;
  embed_dim: number;
  index_type: string;
  nlist: number;
}
export interface ConfigOption {
  value: string | number;
  label: string;
  desc: string;
}

export const configApi = {
  get: () =>
    http<{
      config: RAGConfig;
      options: Record<string, any>;
      defaults: RAGConfig;
    }>('/api/config'),
  update: (updates: Partial<RAGConfig>) =>
    http<{ message: string; updated_fields: string[]; config: RAGConfig }>('/api/config', {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),
  reset: () => http<{ message: string; config: RAGConfig }>('/api/config/reset', { method: 'POST' }),
};

/* ============ 长期记忆 ============ */
export interface MemoryInfo {
  memory_id: string;
  user_id: string;
  content: string;
  summary: string;
  importance_score: number;
  access_count: number;
  status: string;
  created_at: string;
  last_accessed_at: string;
}

export const memoryApi = {
  list: (user_id: string, status = 'active', limit = 100) =>
    http<{ total: number; memories: MemoryInfo[] }>(
      `/api/memory/${encodeURIComponent(user_id)}?status=${status}&limit=${limit}`,
    ),
  add: (body: { user_id: string; content: string; importance?: number; summary?: string }) =>
    http<any>('/api/memory', { method: 'POST', body: JSON.stringify(body) }),
  search: (body: { user_id: string; query: string; top_k?: number; min_importance?: number }) =>
    http<{ total: number; results: any[] }>('/api/memory/search', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  get: (memory_id: string) => http<any>(`/api/memory/detail/${memory_id}`),
  update: (memory_id: string, body: { content?: string; importance?: number; summary?: string }) =>
    http<any>(`/api/memory/${memory_id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  remove: (memory_id: string) =>
    http<any>(`/api/memory/${memory_id}`, { method: 'DELETE' }),
  decay: (threshold = 0.05) =>
    http<{ forgotten: number; threshold: number; message: string }>(
      `/api/memory/decay?threshold=${threshold}`,
      { method: 'POST' },
    ),
  consolidate: (body: { user_id: string; session_id: string }) =>
    http<{ total: number; results: any[] }>('/api/memory/consolidate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};

/* ============ 评测 ============ */
export interface EvalTestItem {
  question: string;
  expected_answer: string;
  expected_source: string;
}
export interface EvalDimensionScore {
  name: string;
  score: number;
  detail: string;
}
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

export const evalApi = {
  run: (body: { test_items: EvalTestItem[]; use_current_config?: boolean; override_config?: any }) =>
    http<EvalReport>('/api/evaluation/run', { method: 'POST', body: JSON.stringify(body) }),
};

/* ============ 健康 ============ */
export const healthApi = {
  check: () => http<any>('/health'),
};

export function errorMsg(e: unknown) {
  message.error(e instanceof Error ? e.message : '请求失败');
}