"""
对话接口
- POST   /api/chat                多轮对话(非流式, 支持 Function Call + 技能)
- POST   /api/chat/stream         多轮对话(SSE 流式输出, 打字机效果)
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

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse
from loguru import logger

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    ToolCallInfo,
    SkillFileInfo,
)
from app.agent.core import agent
from app.agent.memory import memory_store
from app.services.session_store import session_store

router = APIRouter()


def _ensure_configured():
    """初始化校验: API Key / 对话模型 / 嵌入模型未配置时拒绝对话, 引导用户先去配置页"""
    from app.services.config_store import config_store
    setup = config_store.get_setup_status()
    if not setup["configured"]:
        missing_names = {
            "dashscope_api_key": "API Key",
            "dashscope_chat_model": "对话模型",
            "dashscope_embed_model": "嵌入模型",
        }
        labels = [missing_names.get(f, f) for f in setup["missing"]]
        raise HTTPException(
            status_code=400,
            detail="尚未完成初始化配置, 请先到「RAG 配置」页填写: " + "、".join(labels),
        )


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

# 注: 本模块端点均为同步 def —— FastAPI 会自动将同步端点放入线程池执行,
# 避免 agent.chat 内的同步 LLM/检索调用阻塞事件循环(此前 def 会卡死所有并发请求)
@router.post("", response_model=ChatResponse, summary="多轮对话(非流式)")
def chat(req: ChatRequest):
    """多轮对话(支持 RAG + Function Call + 长期记忆注入 + 技能)"""
    _ensure_configured()
    try:
        _ensure_session(req.session_id, req.message)
        result = agent.chat(
            session_id=req.session_id,
            user_message=req.message,
            use_rag=req.use_rag,
            user_id=req.user_id,
            skills=req.skills,
            auto_skill=req.auto_skill,
        )
        session_store.increment_message_count(req.session_id)
        return ChatResponse(
            session_id=result["session_id"],
            answer=result["answer"],
            tool_calls_made=[
                ToolCallInfo(**tc) for tc in result.get("tool_calls_made", [])
            ],
            files=[SkillFileInfo(**f) for f in result.get("files", [])],
        )
    except Exception as e:
        logger.error(f"对话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream", summary="多轮对话(SSE 流式输出)")
def chat_stream(req: ChatRequest):
    """
    SSE 流式对话(打字机效果):
    - 统一工具循环: 工具调用即时推送 tool_calls 事件
    - 最终回答逐 token 推送 content 事件
    - 结束后推送 files 事件(技能生成的文档下载链接)
    """
    _ensure_configured()
    _ensure_session(req.session_id, req.message)

    def event_generator():
        try:
            for event in agent.chat_stream(
                session_id=req.session_id,
                user_message=req.message,
                use_rag=req.use_rag,
                user_id=req.user_id,
                skills=req.skills,
                auto_skill=req.auto_skill,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
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


# ==================== 会话管理 ====================

@router.get("/sessions", summary="获取会话列表")
def list_sessions():
    """列出所有会话(按更新时间倒序)"""
    sessions = session_store.list_sessions()
    return {"total": len(sessions), "sessions": sessions}


@router.post("/sessions", summary="创建新会话")
def create_session(title: str = Body("新对话", embed=True)):
    """创建新会话, 返回 session_id"""
    session_id = str(uuid.uuid4())
    session = session_store.create_session(session_id, title=title)
    return session


@router.patch("/sessions/{session_id}", summary="更新会话标题")
def update_session_title(session_id: str, title: str = Body(..., embed=True)):
    """更新会话标题"""
    ok = session_store.update_session(session_id, title=title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"session_id": session_id, "title": title}


@router.delete("/sessions/{session_id}", summary="删除会话")
def delete_session(session_id: str):
    """删除会话(元数据 + 记忆)"""
    session_store.delete_session(session_id)
    memory_store.clear(session_id)
    return {"session_id": session_id, "message": "会话已删除"}


# ==================== 历史 & 清空(兼容旧接口) ====================

@router.get("/history/{session_id}", response_model=ChatHistoryResponse, summary="获取会话历史")
def get_history(session_id: str):
    """获取指定会话的全部历史消息(含技能生成文件的下载信息)"""
    messages = agent.get_history(session_id)
    return ChatHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/{session_id}", summary="清空会话记忆")
def clear_session(session_id: str):
    """清空指定会话的记忆(不删除会话元数据)"""
    agent.reset_session(session_id)
    return {"session_id": session_id, "message": "会话记忆已清空"}


@router.post("/new-session", summary="生成新会话ID")
def new_session():
    """生成新会话ID(自动创建会话记录)"""
    session_id = str(uuid.uuid4())
    session_store.create_session(session_id, title="新对话")
    return {"session_id": session_id}