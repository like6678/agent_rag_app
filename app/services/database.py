"""
文档元数据存储 (MySQL)
- 存储文档元数据
- 基于 MD5 实现文件去重
- 文档增删查
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from app.services.mysql import mysql_service


class DatabaseService:
    """MySQL 文档元数据存储"""

    def add_document(self, record: Dict[str, Any]) -> bool:
        """
        新增文档记录
        Returns: True=新增成功, False=MD5已存在(跳过)
        """
        now = datetime.now()
        try:
            affected = mysql_service.execute(
                """
                INSERT INTO documents
                    (doc_id, filename, md5, object_name, file_size, content_type,
                     char_count, chunk_count, vector_count, status, created_at, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record["doc_id"],
                    record["filename"],
                    record["md5"],
                    record["object_name"],
                    record["file_size"],
                    record.get("content_type", ""),
                    record.get("char_count", 0),
                    record.get("chunk_count", 0),
                    record.get("vector_count", 0),
                    record.get("status", "active"),
                    now,
                    now,
                ),
            )
            logger.info(f"文档记录已入库: {record['filename']} (md5={record['md5'][:12]}...)")
            return True
        except Exception as e:
            # MD5 重复(MySQL 唯一约束)
            if "Duplicate" in str(e) or "1062" in str(e):
                logger.info(f"文档已存在(MD5重复),跳过: {record['filename']}")
                return False
            raise

    def get_by_md5(self, md5: str) -> Optional[Dict[str, Any]]:
        """按 MD5 查询文档(去重检查)"""
        return mysql_service.query_one("SELECT * FROM documents WHERE md5 = %s", (md5,))

    def get_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """按 doc_id 查询单个文档"""
        return mysql_service.query_one("SELECT * FROM documents WHERE doc_id = %s", (doc_id,))

    def list_documents(self) -> List[Dict[str, Any]]:
        """列出所有文档"""
        return mysql_service.query("SELECT * FROM documents ORDER BY created_at DESC")

    def delete_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        按 doc_id 删除文档记录
        Returns: 被删除的记录(含 object_name 供清理 MinIO), 不存在返回 None
        """
        record = mysql_service.query_one("SELECT * FROM documents WHERE doc_id = %s", (doc_id,))
        if record is None:
            return None
        mysql_service.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
        logger.info(f"文档记录已删除: {doc_id}")
        return record

    def clear_all(self) -> int:
        """清空所有文档记录(知识库重建时调用)"""
        # MySQL 不返回 DELETE 的 rowcount 给 cursor, 需先查再删
        count_row = mysql_service.query_one("SELECT COUNT(*) as cnt FROM documents")
        count = count_row["cnt"] if count_row else 0
        mysql_service.execute("DELETE FROM documents")
        logger.info(f"清空文档记录: {count} 条")
        return count

    def update_status(self, doc_id: str, status: str):
        """更新文档状态"""
        mysql_service.execute(
            "UPDATE documents SET status = %s, updated_at = NOW() WHERE doc_id = %s",
            (status, doc_id),
        )


# 单例
db_service = DatabaseService()
