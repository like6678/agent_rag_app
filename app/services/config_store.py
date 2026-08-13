"""
RAG 系统配置存储 (MySQL 持久化)
- 单行配置表, 支持动态读取/更新
- 环境变量作为初始默认值
- 运行时各模块通过 get_config() 获取当前配置
"""
import json
from typing import Dict, Any, List
from loguru import logger

from app.config import settings
from app.services.mysql import mysql_service


# ==================== 配置项定义 ====================

# chunk_size 可选项(考虑 embedding 输入上限 8192 tokens ≈ 6000 字符,
# 以及 top_k 检索后送入 LLM 的总上下文不宜超过 LLM 上下文的 1/4)
CHUNK_SIZE_OPTIONS = [200, 500, 800, 1000, 1500, 2000]

CHUNK_OVERLAP_OPTIONS = [0, 50, 100, 200, 300]

TOP_K_OPTIONS = [1, 2, 3, 4, 5, 8, 10]

SPLIT_METHODS = [
    {"value": "recursive", "label": "递归字符切片", "desc": "按分隔符递归切分(默认,通用性强)"},
    {"value": "fixed", "label": "固定大小切片", "desc": "按固定字符数硬切分"},
    {"value": "semantic", "label": "语义感知切片", "desc": "按段落/空行等语义边界切分"},
    {"value": "structure", "label": "文档结构切片", "desc": "按 Markdown 标题/章节切分"},
    {"value": "sentence", "label": "句子切片", "desc": "按句子粒度切分"},
    {"value": "llm", "label": "LLM 智能切片", "desc": "用大模型按主题段落切分(消耗 token)"},
]

CHAT_MODELS = [
    {"value": "qwen3.8-max", "label": "qwen3.8-max", "desc": "2026最新最强能力"},
    {"value": "qwen3.7-plus", "label": "qwen3.7-plus", "desc": "2026均衡性能(推荐)"},
    {"value": "qwen3.7-flash", "label": "qwen3.7-flash", "desc": "2026快速响应, 低成本"},
    {"value": "qwen-plus", "label": "qwen-plus", "desc": "经典版均衡"},
    {"value": "qwen-max", "label": "qwen-max", "desc": "经典版最强"},
    {"value": "qwen-turbo", "label": "qwen-turbo", "desc": "经典版快速"},
    {"value": "qwen-long", "label": "qwen-long", "desc": "超长上下文(百万token)"},
]

EMBED_MODELS = [
    {"value": "text-embedding-v3", "label": "text-embedding-v3", "desc": "最新版, 1024维(推荐)"},
    {"value": "text-embedding-v2", "label": "text-embedding-v2", "desc": "v2版, 1536维"},
    {"value": "text-embedding-v1", "label": "text-embedding-v1", "desc": "v1版, 1536维"},
]

# embed_model -> dim 映射
EMBED_DIM_MAP = {
    "text-embedding-v1": 1536,
    "text-embedding-v2": 1536,
    "text-embedding-v3": 1024,
}

SEARCH_METRICS = [
    {"value": "COSINE", "label": "余弦相似度", "desc": "最常用, 适合语义检索"},
    {"value": "L2", "label": "欧氏距离", "desc": "L2 距离"},
    {"value": "IP", "label": "内积", "desc": "内积相似度"},
]

INDEX_TYPES = [
    {"value": "IVF_FLAT", "label": "IVF_FLAT", "desc": "倒排索引, 精确度高(推荐中小规模)"},
    {"value": "HNSW", "label": "HNSW", "desc": "图索引, 检索速度快(推荐大规模)"},
    {"value": "FLAT", "label": "FLAT", "desc": "暴力搜索, 100%精确(适合小数据集)"},
]

RERANK_MODELS = [
    {"value": "none", "label": "不重排", "desc": "直接使用向量检索结果"},
    {"value": "llm", "label": "LLM 重排", "desc": "用大模型对检索结果重新排序"},
]

# 默认配置(从环境变量初始化)
DEFAULT_CONFIG: Dict[str, Any] = {
    # 切片参数
    "chunk_size": settings.chunk_size,
    "chunk_overlap": settings.chunk_overlap,
    "split_method": "recursive",
    # 召回参数
    "retrieval_top_k": settings.retrieval_top_k,
    "search_metric": "COSINE",
    "nprobe": 16,
    # 重排参数
    "rerank_enabled": False,
    "rerank_top_k": 3,
    "rerank_model": "none",
    # 生成参数
    "dashscope_api_key": settings.dashscope_api_key,
    "dashscope_base_url": "",  # 自定义 endpoint(空=默认国内版)
    "dashscope_chat_model": settings.dashscope_chat_model,
    "dashscope_embed_model": settings.dashscope_embed_model,
    "temperature": 0.7,
    "max_tool_iterations": settings.max_tool_iterations,
    # 向量库参数
    "embed_dim": settings.embed_dim,
    "index_type": "IVF_FLAT",
    "nlist": 128,
}

# 所有可选项(供前端渲染)
CONFIG_OPTIONS = {
    "chunk_size": CHUNK_SIZE_OPTIONS,
    "chunk_overlap": CHUNK_OVERLAP_OPTIONS,
    "retrieval_top_k": TOP_K_OPTIONS,
    "split_methods": SPLIT_METHODS,
    "chat_models": CHAT_MODELS,
    "embed_models": EMBED_MODELS,
    "search_metrics": SEARCH_METRICS,
    "index_types": INDEX_TYPES,
    "rerank_models": RERANK_MODELS,
    "embed_dim_map": EMBED_DIM_MAP,
}


class ConfigStore:
    """RAG 配置存储(MySQL 单行表)"""

    def get_config(self) -> Dict[str, Any]:
        """读取当前配置(MySQL 不可用时返回默认值, 不崩溃)"""
        try:
            row = mysql_service.query_one("SELECT config_json FROM rag_config WHERE id = 1")
            if row is None:
                return dict(DEFAULT_CONFIG)
            return json.loads(row["config_json"])
        except Exception as e:
            logger.warning(f"读取 RAG 配置失败, 使用默认值: {e}")
            return dict(DEFAULT_CONFIG)

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新配置(部分更新, 合并)"""
        row = mysql_service.query_one("SELECT config_json FROM rag_config WHERE id = 1")
        current = json.loads(row["config_json"]) if row else dict(DEFAULT_CONFIG)
        # 合并更新
        current.update(updates)
        # 联动: embed_model 变化时自动更新 embed_dim
        if "dashscope_embed_model" in updates:
            model = updates["dashscope_embed_model"]
            current["embed_dim"] = EMBED_DIM_MAP.get(model, 1024)
        mysql_service.execute(
            "UPDATE rag_config SET config_json = %s, updated_at = NOW() WHERE id = 1",
            (json.dumps(current, ensure_ascii=False),),
        )
        logger.info(f"RAG 配置已更新: {list(updates.keys())}")
        return current

    def reset_config(self) -> Dict[str, Any]:
        """重置为默认配置"""
        mysql_service.execute(
            "UPDATE rag_config SET config_json = %s, updated_at = NOW() WHERE id = 1",
            (json.dumps(DEFAULT_CONFIG, ensure_ascii=False),),
        )
        logger.info("RAG 配置已重置为默认值")
        return dict(DEFAULT_CONFIG)


# 单例
config_store = ConfigStore()


def get_rag_config() -> Dict[str, Any]:
    """快捷函数: 获取当前 RAG 配置"""
    return config_store.get_config()
