"""
对话接口
- POST   /api/chat                多轮对话(非流式, 支持 Function Call)
- POST   /api/chat/stream         多轮对话(SSE 流式输出)
- GET    /api/chat/sessions       会话列表
- POST   /api/chat/sessions       创建新会话
- PATCH  /api/chat/sessions/{id}  更新会话标题
- DELETE /api/chat/sessions/{id}  删除会话(元数据+记忆)
- GET    /api/chat/history/{id}   获取会话历史
- DELETE /api/chat/{id}           清空会话记忆(不删除会话)
- POST   /api/chat/new-session    生成新会话ID(兼容旧接口)
"""
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from loguru import logger

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    ToolCallInfo,
)
from app.agent.core import agent
from app.agent.memory import memory_store
from app.services.session_store import session_store
from app.services.dashscope import dashscope_service
from app.rag.retriever import retriever
from app.agent.tools import execute_tool, TOOLS_SCHEMA

router = APIRouter()


def _ensure_session(session_id: str, first_message: str = ""):
    """确保会话存在, 首条消息时设置标题"""
    session = session_store.ensure_session(session_id, title="新对话")
    # 如果是新会话且有消息, 用首条消息作标题
    if first_message and (session.get("message_count", 0) == 0 or session.get("title") == "新对话"):
        title = first_message[:30] + ("..." if len(first_message) > 30 else "")
        session_store.update_session(session_id, title=title)
    session_store.increment_message_count(session_id)
    return session


# ==================== 对话接口 ====================

@router.post("", response_model=ChatResponse, summary="多轮对话(非流式)")
async def chat(req: ChatRequest):
    """多轮对话(支持 RAG + Function Call)"""
    try:
        _ensure_session(req.session_id, req.message)
        result = agent.chat(
            session_id=req.session_id,
            user_message=req.message,
            use_rag=req.use_rag,
        )
        session_store.increment_message_count(req.session_id)
        return ChatResponse(
            session_id=result["session_id"],
            answer=result["answer"],
            tool_calls_made=[
                ToolCallInfo(**tc) for tc in result.get("tool_calls_made", [])
            ],
        )
    except Exception as e:
        logger.error(f"对话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream", summary="多轮对话(SSE 流式输出)")
async def chat_stream(req: ChatRequest):
    """
    SSE 流式对话:
    - 逐 token 返回大模型生成内容
    - 启用 RAG 时先检索知识库增强上下文
    - 如需 Function Call 工具循环, 请用非流式 /api/chat 接口
    """
    _ensure_session(req.session_id, req.message)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # 1. 获取历史记忆
            history = memory_store.get_messages(req.session_id)
            # 根据 use_rag 选择系统提示词
            sys_prompt = _RAG_SYSTEM_PROMPT if req.use_rag else _NORMAL_SYSTEM_PROMPT
            messages = [{"role": "system", "content": sys_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": req.message})

            # 2. 记录用户消息
            memory_store.add_message(req.session_id, "user", req.message)

            # 3. RAG 检索增强(如果启用)
            rag_context = ""
            tool_calls_info = []
            if req.use_rag:
                try:
                    hits = retriever.search(req.message)
                    if hits:
                        rag_context = retriever.build_context(hits)
                        tool_calls_info.append({
                            "name": "knowledge_search",
                            "arguments": {"query": req.message},
                            "result_preview": rag_context[:200],
                        })
                        # 将检索结果作为系统上下文注入
                        messages.insert(
                            -1,
                            {
                                "role": "system",
                                "content": f"以下是从知识库检索到的相关内容,请基于此回答:\n\n{rag_context}",
                            },
                        )
                except Exception as e:
                    logger.warning(f"流式对话 RAG 检索失败: {e}")

            # 4. 发送 tool_calls 信息(如果有)
            if tool_calls_info:
                yield f"data: {json.dumps({'type': 'tool_calls', 'tool_calls': tool_calls_info}, ensure_ascii=False)}\n\n"

            # 5. 流式调用大模型
            full_answer = ""
            for chunk in dashscope_service.chat_stream(messages, tools=None):
                content = chunk.get("content", "")
                if content:
                    full_answer += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content}, ensure_ascii=False)}\n\n"

                if chunk.get("finish_reason"):
                    yield f"data: {json.dumps({'type': 'finish', 'finish_reason': chunk['finish_reason']}, ensure_ascii=False)}\n\n"

            # 6. 保存完整回答到记忆
            memory_store.add_message(req.session_id, "assistant", full_answer)
            session_store.increment_message_count(req.session_id)

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"流式对话失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# 流式对话系统提示词(根据 use_rag 动态切换)
_NORMAL_SYSTEM_PROMPT = """你是一个智能助手,可以与用户进行多轮对话。
请基于你的知识回答用户问题,回答使用中文,语言简洁清晰。
如果没有把握,请如实说明。"""

_RAG_SYSTEM_PROMPT = """你是一个智能助手,可以使用检索到的知识库内容回答用户问题。
工作原则:
1. 优先基于检索到的知识库内容回答,引用相关上下文
2. 如果知识库内容能完全回答问题,基于其回答
3. 如果知识库内容不足,可以补充你的通用知识,但要说明
4. 回答使用中文,语言简洁清晰"""


# ==================== 会话管理 ====================

@router.get("/sessions", summary="获取会话列表")
async def list_sessions():
    """列出所有会话(按更新时间倒序)"""
    sessions = session_store.list_sessions()
    return {"total": len(sessions), "sessions": sessions}


@router.post("/sessions", summary="创建新会话")
async def create_session(title: str = Body("新对话", embed=True)):
    """创建新会话, 返回 session_id"""
    session_id = str(uuid.uuid4())
    session = session_store.create_session(session_id, title=title)
    return session


@router.patch("/sessions/{session_id}", summary="更新会话标题")
async def update_session_title(session_id: str, title: str = Body(..., embed=True)):
    """更新会话标题"""
    ok = session_store.update_session(session_id, title=title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"session_id": session_id, "title": title}


@router.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(session_id: str):
    """删除会话(元数据 + 记忆)"""
    session_store.delete_session(session_id)
    memory_store.clear(session_id)
    return {"session_id": session_id, "message": "会话已删除"}


# ==================== 历史 & 清空(兼容旧接口) ====================

@router.get("/history/{session_id}", response_model=ChatHistoryResponse, summary="获取会话历史")
async def get_history(session_id: str):
    """获取指定会话的全部历史消息"""
    messages = agent.get_history(session_id)
    return ChatHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/{session_id}", summary="清空会话记忆")
async def clear_session(session_id: str):
    """清空指定会话的记忆(不删除会话元数据)"""
    agent.reset_session(session_id)
    return {"session_id": session_id, "message": "会话记忆已清空"}


@router.post("/new-session", summary="生成新会话ID")
async def new_session():
    """生成新会话ID(自动创建会话记录)"""
    session_id = str(uuid.uuid4())
    session_store.create_session(session_id, title="新对话")
    return {"session_id": session_id}
