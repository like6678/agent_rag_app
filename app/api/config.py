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


def _mask_api_key(config: dict) -> dict:
    """脱敏返回: API Key 属于敏感凭据, 不应明文下发到前端/日志。
    只保留前 6 位 + 后 4 位, 中间用 * 代替"""
    masked = dict(config)
    key = masked.get("dashscope_api_key") or ""
    if len(key) > 10:
        masked["dashscope_api_key"] = key[:6] + "*" * 8 + key[-4:]
    elif key:
        masked["dashscope_api_key"] = "*" * len(key)
    return masked


@router.get("", summary="获取当前 RAG 配置")
def get_config():
    """获取当前配置 + 所有可选项 + 默认值(API Key 脱敏返回)"""
    config = config_store.get_config()
    return {
        "config": _mask_api_key(config),
        "options": CONFIG_OPTIONS,
        "defaults": _mask_api_key(DEFAULT_CONFIG),
    }


@router.put("", summary="更新 RAG 配置")
def update_config(req: ConfigUpdateRequest):
    """
    更新配置(部分更新, 只传需要修改的字段)
    embed_model 变化时自动联动 embed_dim
    """
    try:
        # 过滤 None 值
        updates = {k: v for k, v in req.model_dump().items() if v is not None}
        # 前端回显的是脱敏 Key: 若用户未修改(原样提交掩码值), 则丢弃该字段, 保留原 Key
        if "dashscope_api_key" in updates and "*" in str(updates["dashscope_api_key"]):
            updates.pop("dashscope_api_key")
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
def reset_config():
    """重置所有配置为默认值"""
    try:
        config = config_store.reset_config()
        return {"message": "配置已重置为默认值", "config": config}
    except Exception as e:
        logger.error(f"重置配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
