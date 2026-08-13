"""
统一配置管理 - 使用 pydantic-settings 从环境变量读取配置
"""
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，自动从 .env / 环境变量读取"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 通义千问 DashScope ----
    dashscope_api_key: str = ""
    dashscope_chat_model: str = "qwen-plus"
    dashscope_embed_model: str = "text-embedding-v3"

    # ---- Milvus ----
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "knowledge_base"

    # ---- MinIO ----
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"
    minio_secure: bool = False

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"
    memory_backend: Literal["memory", "redis"] = "redis"

    # ---- MySQL (长期记忆) ----
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "agent_rag"

    # ---- 记忆参数 ----
    # 短期记忆: 滑动窗口大小(超过则触发摘要压缩)
    short_term_window: int = 20
    short_term_ttl: int = 86400  # 会话 TTL(秒), 默认 24 小时
    # 长期记忆: 相似度去重阈值(余弦相似度 > 此值则视为重复)
    memory_dedup_threshold: float = 0.85
    # 时间衰减系数(lambda, 越大遗忘越快)
    memory_decay_lambda: float = 0.01

    # ---- 应用 ----
    upload_dir: str = "./data/uploads"
    db_path: str = "./data/app.db"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ---- RAG 参数 ----
    chunk_size: int = 500
    chunk_overlap: int = 50
    embed_dim: int = 1024  # text-embedding-v3 维度
    retrieval_top_k: int = 4

    # ---- Agent 参数 ----
    max_tool_iterations: int = 8


settings = Settings()
