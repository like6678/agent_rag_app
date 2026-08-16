"""
Pydantic 数据模型 - 请求/响应 schema
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field



# ==================== 技能 ====================

class SkillInfo(BaseModel):
    id: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = []
    source: str = "imported"
    enabled: bool = True
    file_count: int = 0
    used_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class SkillStoreItem(BaseModel):
    name: str = ""
    display_name: str = ""
    description: str = ""
    version: str = ""
    author: str = ""
    tags: List[str] = []
    installed: bool = False


class SkillFileInfo(BaseModel):
    name: str = ""
    object_name: str = ""
    download_url: str = ""
    format: str = "md"
    size: int = 0
    created_at: str = ""


class SkillInstallRequest(BaseModel):
    name: str = Field(..., description="商店技能名, 对应 skills_catalog/<name>")


class SkillEnableRequest(BaseModel):
    enabled: bool = Field(..., description="true=启用 false=停用")

# ==================== 对话 ====================

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话ID,用于隔离多轮对话记忆", examples=["session-001"])
    message: str = Field(..., description="用户消息", examples=["什么是 RAG?"])
    use_rag: bool = Field(True, description="是否启用 RAG + 工具调用")
    user_id: Optional[str] = Field(None, description="用户ID(可选, 提供后自动注入相关长期记忆)")
    skills: List[str] = Field(default_factory=list, description="显式指定的技能ID/名称列表(按钮触发)")
    auto_skill: bool = Field(True, description="是否允许模型根据用户意图隐式调用已启用技能(语言触发)")


class ToolCallInfo(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}
    result_preview: str = ""


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    tool_calls_made: List[ToolCallInfo] = []
    files: List[SkillFileInfo] = []


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]] = []


# ==================== 文档 ====================

class DocumentProcessResult(BaseModel):
    doc_id: str
    filename: str
    object_name: str
    md5: str = ""
    file_size: int = 0
    char_count: int
    chunk_count: int
    vector_count: int
    duplicated: bool = False
    message: str = ""


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    md5: str
    object_name: str
    file_size: int
    content_type: str = ""
    char_count: int = 0
    chunk_count: int = 0
    vector_count: int = 0
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""


class DocumentListResponse(BaseModel):
    total: int = 0
    documents: List[DocumentInfo] = []


class DocumentDeleteResponse(BaseModel):
    doc_id: str
    filename: str
    deleted_vectors: int
    message: str


# ==================== 知识库 ====================

class KBStatsResponse(BaseModel):
    collection: str
    num_entities: int


class KBDeleteDocResponse(BaseModel):
    doc_id: str
    deleted_vectors: int
    message: str


# ==================== RAG 配置 ====================

class RAGConfig(BaseModel):
    # 切片参数
    chunk_size: int = 500
    chunk_overlap: int = 50
    split_method: str = "recursive"
    # 召回参数
    retrieval_top_k: int = 4
    search_metric: str = "COSINE"
    nprobe: int = 16
    # 重排参数
    rerank_enabled: bool = False
    rerank_top_k: int = 3
    rerank_model: str = "none"
    # 生成参数
    dashscope_api_key: str = ""
    dashscope_base_url: str = ""
    dashscope_chat_model: str = "qwen-plus"
    dashscope_embed_model: str = "text-embedding-v3"
    temperature: float = 0.7
    max_tool_iterations: int = 8
    # 向量库参数
    embed_dim: int = 1024
    index_type: str = "IVF_FLAT"
    nlist: int = 128


class ConfigUpdateRequest(BaseModel):
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    split_method: Optional[str] = None
    retrieval_top_k: Optional[int] = None
    search_metric: Optional[str] = None
    nprobe: Optional[int] = None
    rerank_enabled: Optional[bool] = None
    rerank_top_k: Optional[int] = None
    rerank_model: Optional[str] = None
    dashscope_api_key: Optional[str] = None
    dashscope_base_url: Optional[str] = None
    dashscope_chat_model: Optional[str] = None
    dashscope_embed_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tool_iterations: Optional[int] = None
    index_type: Optional[str] = None
    nlist: Optional[int] = None


# ==================== 评测 ====================

class EvalTestItem(BaseModel):
    question: str
    expected_answer: str = ""
    expected_source: str = ""


class EvalRequest(BaseModel):
    test_items: List[EvalTestItem] = []
    use_current_config: bool = True
    # 可选: 评测时覆盖配置
    override_config: Optional[Dict[str, Any]] = None


class EvalDimensionScore(BaseModel):
    name: str
    score: float
    detail: str = ""


class EvalResultItem(BaseModel):
    question: str
    expected_answer: str = ""
    retrieved_context: str = ""
    generated_answer: str = ""
    recall_hit: bool = False
    context_relevance: float = 0.0
    answer_faithfulness: float = 0.0
    answer_relevance: float = 0.0


class EvalReport(BaseModel):
    total: int = 0
    recall_rate: float = 0.0
    avg_context_relevance: float = 0.0
    avg_answer_faithfulness: float = 0.0
    avg_answer_relevance: float = 0.0
    overall_score: float = 0.0
    dimensions: List[EvalDimensionScore] = []
    items: List[EvalResultItem] = []
    config_snapshot: Dict[str, Any] = {}


# ==================== 长期记忆 ====================

class MemoryCreateRequest(BaseModel):
    user_id: str = Field(..., description="用户ID(隔离)")
    content: str = Field(..., description="记忆内容")
    importance: Optional[float] = Field(None, ge=0, le=1, description="重要度(0-1, 留空自动评分)")
    summary: str = ""


class MemorySearchRequest(BaseModel):
    user_id: str = Field(..., description="用户ID")
    query: str = Field(..., description="检索查询")
    top_k: int = Field(5, ge=1, le=20)
    min_importance: float = Field(0.0, ge=0, le=1)


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    importance: Optional[float] = Field(None, ge=0, le=1)
    summary: Optional[str] = None


class MemoryInfo(BaseModel):
    memory_id: str = ""
    user_id: str = ""
    content: str = ""
    summary: str = ""
    importance_score: float = 0.5
    access_count: int = 0
    status: str = "active"
    created_at: str = ""
    last_accessed_at: str = ""


class ConsolidateRequest(BaseModel):
    user_id: str = Field(..., description="用户ID")
    session_id: str = Field(..., description="会话ID(从中提取记忆)")
