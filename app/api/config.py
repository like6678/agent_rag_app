"""
RAG 配置管理接口
- GET    /api/config         获取当前配置 + 所有可选项
- PUT    /api/config         更新配置(部分更新)
- POST   /api/config/reset   重置为默认配置
"""
from fastapi import APIRouter, HTTPException
from loguru import logger

from app.models.schemas import RAGConfig, ConfigUpdateRequest
from app.services.config_store import config_store, CONFIG_OPTIONS, DEFAULT_CONFIG

router = APIRouter()


@router.get("", summary="获取当前 RAG 配置")
async def get_config():
    """获取当前配置 + 所有可选项 + 默认值"""
    config = config_store.get_config()
    return {
        "config": config,
        "options": CONFIG_OPTIONS,
        "defaults": DEFAULT_CONFIG,
    }


@router.put("", summary="更新 RAG 配置")
async def update_config(req: ConfigUpdateRequest):
    """
    更新配置(部分更新, 只传需要修改的字段)
    embed_model 变化时自动联动 embed_dim
    """
    try:
        # 过滤 None 值
        updates = {k: v for k, v in req.model_dump().items() if v is not None}
        if not updates:
            return {"message": "无更新字段", "config": config_store.get_config()}

        new_config = config_store.update_config(updates)
        return {
            "message": "配置已更新",
            "updated_fields": list(updates.keys()),
            "config": new_config,
        }
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset", summary="重置为默认配置")
async def reset_config():
    """重置所有配置为默认值"""
    try:
        config = config_store.reset_config()
        return {"message": "配置已重置为默认值", "config": config}
    except Exception as e:
        logger.error(f"重置配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
