"""
FastAPI 应用入口
- 挂载路由: 对话 / 文档上传 / 知识库管理
- 生命周期: 启动时初始化 Milvus 集合、MinIO bucket
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from loguru import logger

from app.config import settings
from app.api import chat, documents, knowledge_base, config as config_api, evaluation as evaluation_api, memory as memory_api, skills as skills_api
from app.services.milvus import milvus_service
from app.services.minio import minio_service
from app.services.database import db_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动初始化 / 关闭清理"""
    logger.info("应用启动中...")

    # 确保上传目录存在
    os.makedirs(settings.upload_dir, exist_ok=True)

    # 初始化 MySQL(全部表: documents/rag_config/chat_sessions/long_term_memories)
    try:
        from app.services.mysql import mysql_service
        mysql_service.init_tables()
        logger.info(f"MySQL 就绪: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    except Exception as e:
        logger.warning(f"MySQL 初始化失败(将在运行时重试): {e}")

    # 初始化 MinIO bucket
    try:
        minio_service.ensure_bucket()
        logger.info(f"MinIO bucket 就绪: {settings.minio_bucket}")
    except Exception as e:
        logger.warning(f"MinIO 初始化失败(将在运行时重试): {e}")

    # 初始化 Milvus 集合
    try:
        milvus_service.ensure_collection()
        logger.info(f"Milvus 集合就绪: {settings.milvus_collection}")
    except Exception as e:
        logger.warning(f"Milvus 初始化失败(将在运行时重试): {e}")

    # 初始化长期记忆(MySQL 表 + Milvus 长期记忆集合)
    try:
        from app.services.long_term_memory import long_term_memory
        long_term_memory.init_all()
        logger.info("长期记忆系统就绪(MySQL + Milvus)")
    except Exception as e:
        logger.warning(f"长期记忆初始化失败(将在运行时重试): {e}")

    # 技能产物 TTL 清理(启动时清扫 7 天前的文件)
    try:
        from app.services.skill_artifacts import cleanup_artifacts
        cleanup_artifacts()
    except Exception as e:
        logger.warning(f"技能产物启动清理跳过: {e}")

    logger.info("应用启动完成")
    yield

    logger.info("应用关闭")


app = FastAPI(
    title="Agent RAG App",
    description="FastAPI + RAG + Agent + Milvus + MinIO + 通义千问",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    # 注意: allow_origins=["*"] 与 allow_credentials=True 是非法组合,
    # 浏览器会直接拒绝响应。本项目为纯 Bearer/无 Cookie 的 API, 关闭 credentials 即可。
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(chat.router, prefix="/api/chat", tags=["对话"])
app.include_router(documents.router, prefix="/api/documents", tags=["文档"])
app.include_router(knowledge_base.router, prefix="/api/kb", tags=["知识库"])
app.include_router(config_api.router, prefix="/api/config", tags=["配置"])
app.include_router(evaluation_api.router, prefix="/api/evaluation", tags=["评测"])
app.include_router(memory_api.router, prefix="/api/memory", tags=["长期记忆"])
app.include_router(skills_api.router, prefix="/api/skills", tags=["技能"])


FRONTEND_DIST = Path(settings.frontend_dist)


@app.get("/", tags=["健康检查"])
async def root():
    """根路径: 生产模式(前端已构建)返回 SPA 页面, 否则返回服务状态 JSON"""
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"status": "ok", "service": "Agent RAG App", "version": "1.0.0"}


def _health_payload():
    return {
        "status": "healthy",
        "milvus": settings.milvus_host,
        "minio": settings.minio_endpoint,
        "memory_backend": settings.memory_backend,
    }


@app.get("/health", tags=["健康检查"])
async def health():
    return _health_payload()


@app.get("/api/health", tags=["健康检查"])
async def health_api():
    return _health_payload()


# ---------------- 前端静态资源托管(生产模式) ----------------
# 当 frontend/dist 存在时, 由 FastAPI 直接托管前端:
#   - /assets/* 与 /umi.js 等真实文件 -> 返回文件
#   - 其余路径(SPA 路由 /chat /dashboard ...) -> 回退到 index.html
#   - 未匹配的 /api/* -> 404 (避免把 API 错误也回退到前端)
if FRONTEND_DIST.is_dir():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        try:
            candidate = (FRONTEND_DIST / full_path).resolve()
            dist_root = FRONTEND_DIST.resolve()
            if candidate.is_relative_to(dist_root) and candidate.is_file():
                return FileResponse(candidate)
        except (ValueError, OSError):
            pass
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not Found")
