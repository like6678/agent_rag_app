"""
会话管理服务 (MySQL 持久化)
- 会话列表 CRUD
- 会话标题自动生成(首条消息)
- 与 memory_store 配合: memory_store 存消息内容, session_store 存会话元数据
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from app.services.mysql import mysql_service


class SessionStore:
    """聊天会话元数据存储(MySQL)"""

    def create_session(self, session_id: str, title: str = "新对话") -> Dict[str, Any]:
        """创建新会话(已存在则忽略)"""
        now = datetime.now()
        try:
            mysql_service.execute(
                "INSERT IGNORE INTO chat_sessions (session_id, title, created_at, updated_at, message_count) VALUES (%s, %s, %s, %s, 0)",
                (session_id, title, now, now),
            )
        except Exception as e:
            logger.warning(f"创建会话失败(可能已存在): {e}")
        logger.info(f"创建会话: {session_id}")
        return {"session_id": session_id, "title": title, "created_at": str(now), "updated_at": str(now), "message_count": 0}

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话(按更新时间倒序)"""
        return mysql_service.query("SELECT * FROM chat_sessions ORDER BY updated_at DESC")

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话"""
        return mysql_service.query_one("SELECT * FROM chat_sessions WHERE session_id = %s", (session_id,))

    def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        message_count: Optional[int] = None,
    ) -> bool:
        """更新会话标题/消息数"""
        sets = ["updated_at = NOW()"]
        params = []
        if title is not None:
            sets.append("title = %s")
            params.append(title)
        if message_count is not None:
            sets.append("message_count = %s")
            params.append(message_count)
        params.append(session_id)
        affected = mysql_service.execute(
            f"UPDATE chat_sessions SET {', '.join(sets)} WHERE session_id = %s",
            tuple(params),
        )
        return affected > 0

    def touch_session(self, session_id: str):
        """更新会话时间戳(对话时调用)"""
        self.update_session(session_id)

    def increment_message_count(self, session_id: str):
        """消息计数+1"""
        mysql_service.execute(
            "UPDATE chat_sessions SET message_count = message_count + 1, updated_at = NOW() WHERE session_id = %s",
            (session_id,),
        )

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        affected = mysql_service.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
        return affected > 0

    def ensure_session(self, session_id: str, title: str = "新对话") -> Dict[str, Any]:
        """确保会话存在,不存在则创建"""
        session = self.get_session(session_id)
        if session is None:
            return self.create_session(session_id, title)
        return session


# 单例
session_store = SessionStore()
