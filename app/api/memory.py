"""
长期记忆管理接口
- POST   /api/memory             新增长期记忆(自动评分+去重+向量化)
- GET    /api/memory/{user_id}   列出用户记忆
- POST   /api/memory/search      语义检索(user_id 隔离)
- GET    /api/memory/detail/{memory_id}  获取单条
- PATCH  /api/memory/{memory_id} 更新记忆
- DELETE /api/memory/{memory_id} 删除记忆
- POST   /api/memory/decay       执行时间衰减遗忘
- POST   /api/memory/consolidate 从短期会话记忆沉淀到长期记忆
"""
from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from app.models.schemas import (
    MemoryCreateRequest,
    MemorySearchRequest,
    MemoryUpdateRequest,
    ConsolidateRequest,
)
from app.services.long_term_memory import long_term_memory
from app.agent.memory import memory_store

router = APIRouter()


@router.post("", summary="新增长期记忆")
async def add_memory(req: MemoryCreateRequest):
    """新增记忆: 自动评分 + 相似度去重 + 向量化 + 存储"""
    try:
        result = long_term_memory.add_memory(
            user_id=req.user_id,
            content=req.content,
            importance=req.importance,
            summary=req.summary,
        )
        return result
    except Exception as e:
        logger.error(f"新增记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}", summary="列出用户记忆")
async def list_memories(
    user_id: str,
    status: str = Query("active"),
    limit: int = Query(100, ge=1, le=500),
):
    """列出用户的所有长期记忆"""
    try:
        return {"total": 0, "memories": long_term_memory.list_memories(user_id, status, limit)}
    except Exception as e:
        logger.error(f"列出记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", summary="语义检索记忆")
async def search_memory(req: MemorySearchRequest):
    """语义检索用户长期记忆(带 user_id 隔离 + 时间衰减)"""
    try:
        results = long_term_memory.search_memory(
            user_id=req.user_id,
            query=req.query,
            top_k=req.top_k,
            min_importance=req.min_importance,
        )
        return {"total": len(results), "results": results}
    except Exception as e:
        logger.error(f"检索记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detail/{memory_id}", summary="获取单条记忆")
async def get_memory(memory_id: str):
    """获取单条记忆详情"""
    record = long_term_memory.get_memory(memory_id)
    if not record:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return record


@router.patch("/{memory_id}", summary="更新记忆")
async def update_memory(memory_id: str, req: MemoryUpdateRequest):
    """更新记忆内容/重要度/摘要"""
    try:
        ok = long_term_memory.update_memory(
            memory_id,
            content=req.content,
            importance=req.importance,
            summary=req.summary,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"memory_id": memory_id, "message": "记忆已更新"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{memory_id}", summary="删除记忆")
async def delete_memory(memory_id: str):
    """删除记忆(MySQL + Milvus)"""
    try:
        ok = long_term_memory.delete_memory(memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail="记忆不存在")
        return {"memory_id": memory_id, "message": "记忆已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decay", summary="执行时间衰减遗忘")
async def apply_decay(threshold: float = Query(0.05, ge=0, le=1)):
    """将衰减后重要度低于阈值的记忆标记为 forgotten"""
    try:
        count = long_term_memory.apply_decay(threshold)
        return {"forgotten": count, "threshold": threshold, "message": f"{count} 条记忆被遗忘"}
    except Exception as e:
        logger.error(f"遗忘执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consolidate", summary="从短期记忆沉淀到长期记忆")
async def consolidate(req: ConsolidateRequest):
    """从短期会话记忆中提取值得长期记住的信息, 存入长期记忆"""
    try:
        # 获取短期记忆消息
        messages = memory_store.get_messages(req.session_id)
        if not messages:
            raise HTTPException(status_code=400, detail="会话无消息")
        results = long_term_memory.consolidate_from_short_term(req.user_id, messages)
        return {"total": len(results), "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"沉淀失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
