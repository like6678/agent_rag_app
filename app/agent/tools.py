"""
工具定义 - 供 Agent Function Call 使用
每个工具包含:
- schema: OpenAI function 格式定义
- handler: 实际执行函数
"""
from typing import Dict, Any, List
from loguru import logger

from app.rag.retriever import retriever
from app.services.minio import minio_service
from app.services.milvus import milvus_service
from app.services.database import db_service


# ==================== 工具实现 ====================

def tool_knowledge_search(query: str, top_k: int = 4) -> str:
    """知识库检索工具: 根据查询从知识库中检索相关文档片段"""
    hits = retriever.search(query, top_k=top_k)
    if not hits:
        return "未在知识库中找到相关内容。"
    context = retriever.build_context(hits)
    return context


def tool_list_documents() -> str:
    """列出已上传的文档(从数据库读取元数据)"""
    docs = db_service.list_documents()
    if not docs:
        return "当前没有已上传的文档。"
    lines = [
        f"- {d['filename']} (doc_id={d['doc_id'][:8]}, "
        f"大小={d['file_size']}bytes, 块数={d['chunk_count']}, 向量数={d['vector_count']})"
        for d in docs
    ]
    return f"已上传文档列表(共{len(docs)}个):\n" + "\n".join(lines)


def tool_knowledge_base_stats() -> str:
    """知识库统计信息"""
    stats = milvus_service.stats()
    doc_count = len(db_service.list_documents())
    return (
        f"知识库统计: 集合={stats['collection']}, "
        f"向量总数={stats['num_entities']}, 文档数={doc_count}"
    )


# ==================== 工具 Schema (OpenAI function 格式) ====================

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": "从知识库中检索与用户问题相关的文档片段。当用户提问涉及已上传文档的内容时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索查询关键词或问题",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回的最相关结果数量,默认4",
                        "default": 4,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "列出知识库中已上传的所有文档文件。当用户想知道有哪些文档可用时使用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_base_stats",
            "description": "查询知识库的统计信息,包括向量总数等。当用户想了解知识库规模时使用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

# 工具名 -> 执行函数 映射
TOOL_HANDLERS = {
    "knowledge_search": lambda args: tool_knowledge_search(
        query=args["query"], top_k=args.get("top_k", 4)
    ),
    "list_documents": lambda args: tool_list_documents(),
    "knowledge_base_stats": lambda args: tool_knowledge_base_stats(),
}


def execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """执行工具调用"""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        logger.warning(f"未知工具: {name}")
        return f"错误: 未知工具 '{name}'"
    try:
        logger.info(f"执行工具 {name}, 参数: {arguments}")
        result = handler(arguments)
        logger.info(f"工具 {name} 执行完成")
        return result
    except Exception as e:
        logger.error(f"工具 {name} 执行失败: {e}")
        return f"工具执行失败: {e}"
