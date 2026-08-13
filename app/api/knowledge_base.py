"""
知识库管理接口
- GET    /api/kb/stats   知识库统计信息
- DELETE /api/kb/collection  删除并重建集合(清空知识库)
- POST   /api/kb/search  直接检索测试(不经过 Agent)
"""
from fastapi import APIRouter, HTTPException, Body
from loguru import logger

from app.models.schemas import KBStatsResponse
from app.services.milvus import milvus_service
from app.services.database import db_service
from app.config import settings
from app.rag.retriever import retriever

router = APIRouter()


@router.get("/stats", response_model=KBStatsResponse, summary="知识库统计")
async def kb_stats():
    """获取知识库(向量集合)的统计信息"""
    try:
        stats = milvus_service.stats()
        return KBStatsResponse(
            collection=stats["collection"],
            num_entities=stats["num_entities"],
        )
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collection", summary="清空知识库(重建集合)")
async def reset_collection():
    """
    删除当前集合并重新创建空集合
    同步清空数据库中的文档元数据记录
    """
    try:
        # 清空数据库文档记录
        cleared = db_service.clear_all()

        # 重建 Milvus 集合
        milvus_service.drop_collection()
        milvus_service.ensure_collection()

        return {
            "message": "知识库已清空并重建",
            "cleared_documents": cleared,
            "collection": settings.milvus_collection,
        }
    except Exception as e:
        logger.error(f"重建集合失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", summary="检索测试")
async def kb_search(
    query: str = Body(..., embed=True, description="检索查询"),
    top_k: int = Body(4, embed=True, description="返回数量"),
):
    """
    直接对知识库进行向量检索测试(不经过 Agent / 大模型)
    用于验证文档入库效果
    """
    try:
        hits = retriever.search(query, top_k=top_k)
        return {
            "query": query,
            "total": len(hits),
            "results": hits,
        }
    except Exception as e:
        logger.error(f"检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
