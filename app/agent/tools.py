"""
工具定义 - 供 Agent Function Call 使用
每个工具包含:
- schema: OpenAI function 格式定义
- handler: 实际执行函数

技能扩展:
- skill_<name>: 隐式触发技能(模型按用户意图调用, 返回技能指令)
- get_skill_file: 读取技能模板/资料资产
- export_document: 把生成内容导出为 MD/PDF 到 MinIO, 返回下载链接
"""
from typing import Dict, Any, List, Optional
from loguru import logger

from app.rag.retriever import retriever
from app.services.minio import minio_service
from app.services.milvus import milvus_service
from app.services.database import db_service
from app.services.skill_store import skill_store


# ==================== 工具实现 ====================

def tool_knowledge_search(args: Dict[str, Any], session_id: Optional[str] = None) -> str:
    """知识库检索工具: 根据查询从知识库中检索相关文档片段"""
    query = args.get("query", "")
    top_k = int(args.get("top_k", 4))
    if not query:
        return "错误: 缺少 query 参数"
    hits = retriever.search(query, top_k=top_k)
    if not hits:
        return "未在知识库中找到相关内容。"
    return retriever.build_context(hits)


def tool_list_documents(args: Dict[str, Any], session_id: Optional[str] = None) -> str:
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


def tool_knowledge_base_stats(args: Dict[str, Any], session_id: Optional[str] = None) -> str:
    """知识库统计信息"""
    stats = milvus_service.stats()
    doc_count = len(db_service.list_documents())
    return (
        f"知识库统计: 集合={stats['collection']}, "
        f"向量总数={stats['num_entities']}, 文档数={doc_count}"
    )


def tool_export_document(args: Dict[str, Any], session_id: Optional[str] = None):
    """导出文档工具: 生成 MD/PDF 存入 MinIO, 返回 (结果文本, 生成文件列表)"""
    from app.services.skill_artifacts import export_document
    title = args.get("title") or "导出文档"
    content_md = args.get("content_md") or ""
    fmt = (args.get("format") or "md").lower()
    if not content_md.strip():
        return "错误: content_md 不能为空", []
    try:
        info = export_document(
            title=title,
            content_md=content_md,
            format=fmt,
            session_id=session_id or "unknown",
        )
        return (
            f"文档已生成并保存:\n"
            f"文件名: {info['name']}\n"
            f"格式: {info['format']}\n"
            f"大小: {info['size']} bytes\n"
            f"下载链接: {info['download_url']}",
            [info],
        )
    except Exception as e:
        logger.error(f"导出文档失败: {e}")
        return f"文档生成失败: {e}", []


def tool_get_skill_file(args: Dict[str, Any], session_id: Optional[str] = None) -> str:
    """读取技能资产文件(模板/资料)"""
    skill = args.get("skill") or args.get("skill_id") or ""
    path = args.get("path") or ""
    if not skill or not path:
        return "错误: 需要 skill 与 path 两个参数"
    try:
        data, ct, fname = skill_store.get_asset(skill, path)
        text = data.decode("utf-8", errors="replace")
        return f"技能资产 {fname} ({ct}, {len(data)} bytes) 内容:\n{text[:3000]}"
    except Exception as e:
        return f"读取技能资产失败: {e}"


def _invoke_skill(skill_name: str, session_id: Optional[str] = None) -> str:
    """隐式触发技能: 返回技能说明供模型遵循, 并记录使用次数"""
    skill = skill_store.get_skill(skill_name)
    if skill is None:
        return f"错误: 技能 {skill_name} 不存在"
    if not skill["enabled"]:
        return f"错误: 技能 {skill_name} 未启用"
    skill_store.increment_used(skill["id"])
    assets = skill_store.list_assets(skill["id"])
    parts = [
        f"技能已启用: {skill['display_name']} (name={skill['name']})",
        f"请严格按照以下技能说明执行, 完成用户的目标:\n{skill['content']}",
    ]
    if assets:
        names = ", ".join(a["path"] for a in assets)
        parts.append(f"技能附带资产文件: {names}")
        parts.append("如需读取资产内容, 调用 get_skill_file(skill=<技能name>, path=<文件相对路径>)")
    return "\n\n".join(parts)


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
                    "query": {"type": "string", "description": "检索查询关键词或问题"},
                    "top_k": {"type": "integer", "description": "返回的最相关结果数量,默认4", "default": 4},
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

EXPORT_DOCUMENT_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "export_document",
        "description": "把内容生成文档文件(Markdown 或 PDF), 保存到对象存储并返回下载链接。当用户要求生成/导出报告、周报、纪要、文档文件时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "文档标题(用作文件名)"},
                "content_md": {"type": "string", "description": "文档完整内容, Markdown 格式"},
                "format": {
                    "type": "string",
                    "enum": ["md", "pdf"],
                    "description": "输出格式, 默认 md; 正式文档可用 pdf",
                },
            },
            "required": ["title", "content_md"],
        },
    },
}

GET_SKILL_FILE_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_skill_file",
        "description": "读取已启用技能的模板/资料资产文件内容(如模板、示例)。技能说明中列出资产文件时, 先读取再使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "技能 name(如 weekly-report)"},
                "path": {"type": "string", "description": "资产文件相对路径, 如 files/template.md"},
            },
            "required": ["skill", "path"],
        },
    },
}


def build_tools_schema(
    use_rag: bool = True,
    explicit_skills: Optional[List[str]] = None,
    auto_skill: bool = True,
) -> List[Dict[str, Any]]:
    """构建本次对话的工具列表

    - use_rag=True 时包含知识库检索/文档工具
    - 存在技能(显式选择或已启用)时附带 export_document / get_skill_file
    - auto_skill=True 时为每个已启用技能注册 skill_<name>(隐式触发)
    """
    tools: List[Dict[str, Any]] = list(TOOLS_SCHEMA) if use_rag else []
    explicit = set(explicit_skills or [])
    try:
        installed = [s for s in skill_store.list_skills() if s["enabled"]]
    except Exception as e:
        logger.warning(f"加载技能列表失败: {e}")
        installed = []

    active = installed or bool(explicit)
    if not active:
        return tools

    tools.append(EXPORT_DOCUMENT_SCHEMA)
    tools.append(GET_SKILL_FILE_SCHEMA)

    if auto_skill:
        for s in installed:
            if s["name"] in explicit:
                continue
            tool_name = f"skill_{s['name']}"
            if len(tool_name) > 64:
                logger.warning(f"技能名过长, 跳过隐式注册: {s['name']}")
                continue
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": (
                        f"技能: {s['display_name']}。{s['description']} "
                        f"当用户意图与此技能匹配时调用该技能, 然后按其说明执行。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string", "description": "用户希望技能完成的目标或要求"}
                        },
                    },
                },
            })
    return tools


# 工具名 -> 执行函数 映射(handler 签名: (args, session_id=None))
TOOL_HANDLERS = {
    "knowledge_search": tool_knowledge_search,
    "list_documents": tool_list_documents,
    "knowledge_base_stats": tool_knowledge_base_stats,
    "export_document": tool_export_document,
    "get_skill_file": tool_get_skill_file,
}


def execute_tool(name: str, arguments: Dict[str, Any], session_id: Optional[str] = None):
    """执行工具调用, 返回 (结果文本, 生成的技能文件列表)"""
    if name.startswith("skill_"):
        return _invoke_skill(name[len("skill_"):], session_id=session_id), []
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        logger.warning(f"未知工具: {name}")
        return f"错误: 未知工具 '{name}'", []
    try:
        logger.info(f"执行工具 {name}, 参数: {arguments}")
        result = handler(arguments, session_id=session_id)
        logger.info(f"工具 {name} 执行完成")
        if isinstance(result, tuple):
            return result
        return result, []
    except Exception as e:
        logger.error(f"工具 {name} 执行失败: {e}")
        return f"工具执行失败: {e}", []