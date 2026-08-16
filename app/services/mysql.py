"""
MySQL 连接服务 (长期记忆结构化存储)
- 使用 pymysql + DBUtils 连接池
- 自动建表
- 提供查询/执行接口
"""
import threading
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Any, Optional
from loguru import logger

from app.config import settings


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """统一序列化 MySQL 行: datetime/date -> ISO 字符串, Decimal -> float, bytes -> utf-8 字符串
    避免下游 Pydantic 模型(str 字段)或 JSON 序列化失败
    """
    out = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (bytes, bytearray)):
            out[k] = v.decode("utf-8", errors="ignore")
        else:
            out[k] = v
    return out


class MySQLService:
    """MySQL 连接池服务"""

    def __init__(self):
        self._pool = None
        self._lock = threading.Lock()
        self._connected = False

    def _get_pool(self):
        """获取连接池(懒加载, 自动建库)"""
        if self._pool is not None:
            return self._pool
        with self._lock:
            if self._pool is not None:
                return self._pool
            try:
                from dbutils.pooled_db import PooledDB
                import pymysql

                # 先连到 MySQL 服务器(不指定 database), 自动创建数据库
                try:
                    admin_conn = pymysql.connect(
                        host=settings.mysql_host,
                        port=settings.mysql_port,
                        user=settings.mysql_user,
                        password=settings.mysql_password,
                        charset="utf8mb4",
                    )
                    with admin_conn.cursor() as cur:
                        cur.execute(
                            f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                        )
                    admin_conn.close()
                    logger.info(f"MySQL 数据库已确保存在: {settings.mysql_database}")
                except Exception as e:
                    logger.warning(f"自动建库失败(可能权限不足): {e}")

                self._pool = PooledDB(
                    creator=pymysql,
                    maxconnections=10,
                    mincached=2,
                    maxcached=5,
                    host=settings.mysql_host,
                    port=settings.mysql_port,
                    user=settings.mysql_user,
                    password=settings.mysql_password,
                    database=settings.mysql_database,
                    charset="utf8mb4",
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=True,
                )
                self._connected = True
                logger.info(
                    f"MySQL 连接池就绪: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
                )
            except Exception as e:
                logger.warning(f"MySQL 连接失败(将在运行时重试): {e}")
                self._connected = False
                raise
        return self._pool

    def get_conn(self):
        """从连接池获取连接"""
        pool = self._get_pool()
        return pool.connection()

    def query(self, sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
        """查询多行"""
        conn = self.get_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, args)
                rows = cursor.fetchall()
                return [_serialize_row(dict(r)) for r in rows] if rows else []
        finally:
            conn.close()

    def query_one(self, sql: str, args: tuple = ()) -> Optional[Dict[str, Any]]:
        """查询单行"""
        conn = self.get_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, args)
                row = cursor.fetchone()
                return _serialize_row(dict(row)) if row else None
        finally:
            conn.close()

    def execute(self, sql: str, args: tuple = ()) -> int:
        """执行写操作, 返回 affected rows"""
        conn = self.get_conn()
        try:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, args)
                return affected
        finally:
            conn.close()

    def execute_and_get_id(self, sql: str, args: tuple = ()) -> int:
        """执行插入并返回自增 ID"""
        conn = self.get_conn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, args)
                return cursor.lastrowid
        finally:
            conn.close()

    def init_tables(self):
        """初始化长期记忆表"""
        sql = """
        CREATE TABLE IF NOT EXISTS long_term_memories (
            id                BIGINT AUTO_INCREMENT PRIMARY KEY,
            memory_id         VARCHAR(64) NOT NULL UNIQUE COMMENT '记忆唯一标识(UUID)',
            user_id           VARCHAR(64) NOT NULL COMMENT '用户ID(隔离)',
            content           TEXT NOT NULL COMMENT '记忆内容',
            summary           VARCHAR(512) DEFAULT '' COMMENT '摘要',
            importance_score  FLOAT DEFAULT 0.5 COMMENT '重要度(0-1)',
            milvus_id         VARCHAR(64) DEFAULT '' COMMENT 'Milvus 向量ID',
            access_count      INT DEFAULT 0 COMMENT '访问次数',
            created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status            VARCHAR(20) DEFAULT 'active' COMMENT 'active/forgotten',
            INDEX idx_user (user_id),
            INDEX idx_status (status),
            INDEX idx_importance (importance_score),
            INDEX idx_last_access (last_accessed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='长期记忆实体表'
        """
        self.execute(sql)

        # 文档元数据表
        self.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id        VARCHAR(64) PRIMARY KEY,
            filename      VARCHAR(512) NOT NULL,
            md5           VARCHAR(64) NOT NULL UNIQUE,
            object_name   VARCHAR(512) NOT NULL,
            file_size     BIGINT NOT NULL,
            content_type  VARCHAR(128) DEFAULT '',
            char_count    INT DEFAULT 0,
            chunk_count   INT DEFAULT 0,
            vector_count  INT DEFAULT 0,
            status        VARCHAR(20) DEFAULT 'active',
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_md5 (md5),
            INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='文档元数据表'
        """)

        # RAG 配置表(单行)
        self.execute("""
        CREATE TABLE IF NOT EXISTS rag_config (
            id            INT PRIMARY KEY DEFAULT 1,
            config_json   TEXT NOT NULL,
            updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT single_row CHECK (id = 1)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='RAG 配置(单行表)'
        """)
        # 初始化默认配置(如果为空)
        from app.services.config_store import DEFAULT_CONFIG
        import json
        existing = self.query_one("SELECT id FROM rag_config WHERE id = 1")
        if existing is None:
            self.execute(
                "INSERT INTO rag_config (id, config_json, updated_at) VALUES (1, %s, NOW())",
                (json.dumps(DEFAULT_CONFIG, ensure_ascii=False),),
            )

        # 会话元数据表
        self.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id    VARCHAR(64) PRIMARY KEY,
            title         VARCHAR(256) DEFAULT '',
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            message_count INT DEFAULT 0,
            INDEX idx_session_updated (updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        COMMENT='会话元数据表'
        """)

        logger.info("MySQL 全部表初始化完成(documents/rag_config/chat_sessions/long_term_memories)")


# 单例
mysql_service = MySQLService()
