"""
短期会话记忆 - 三层记忆之第一层
- Redis 存储(分布式安全, 禁止内存存储用于生产)
- 滑动窗口: 保留最近 N 条消息
- 摘要压缩: 超过窗口时用 LLM 摘要早期消息, 防止上下文膨胀
- 会话 TTL: 自动过期清理
"""
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from app.config import settings


class BaseMemory:
    """记忆接口(保持向后兼容)"""

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def add_message(self, session_id: str, role: str, content: str, **extra):
        raise NotImplementedError

    def add_messages(self, session_id: str, messages: List[Dict[str, Any]]):
        for m in messages:
            self.add_message(session_id, m["role"], m.get("content", ""),
                             **{k: v for k, v in m.items() if k not in ("role", "content")})

    def clear(self, session_id: str):
        raise NotImplementedError


class RedisShortTermMemory(BaseMemory):
    """
    Redis 短期会话记忆
    - 滑动窗口 + 摘要压缩
    - 会话 TTL 自动过期
    """

    def __init__(self, window: int = None, ttl: int = None):
        import redis
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self.window = window or settings.short_term_window
        self.ttl = ttl or settings.short_term_ttl
        self._prefix = "agent:memory:"
        self._summary_prefix = "agent:summary:"
        # 测试连接
        try:
            self._redis.ping()
            logger.info(f"短期记忆使用 Redis (窗口={self.window}, TTL={self.ttl}s)")
        except Exception as e:
            logger.error(f"Redis 连接失败: {e}")
            raise

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def _summary_key(self, session_id: str) -> str:
        return f"{self._summary_prefix}{session_id}"

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话消息(含历史摘要 + 最近窗口消息)"""
        pipe = self._redis.pipeline()
        pipe.get(self._summary_key(session_id))
        pipe.lrange(self._key(session_id), 0, -1)
        summary_json, msg_jsons = pipe.execute()

        messages: List[Dict[str, Any]] = []
        # 如果有历史摘要, 放在最前面
        if summary_json:
            try:
                summary = json.loads(summary_json)
                messages.append({
                    "role": "system",
                    "content": f"[之前对话摘要] {summary.get('content', '')}",
                })
            except json.JSONDecodeError:
                pass

        # 最近窗口消息
        for mj in msg_jsons:
            try:
                messages.append(json.loads(mj))
            except json.JSONDecodeError:
                continue

        return messages

    def add_message(self, session_id: str, role: str, content: str, **extra):
        """添加消息, 自动滑动窗口 + 摘要压缩"""
        msg = {"role": role, "content": content}
        msg.update(extra)

        key = self._key(session_id)
        pipe = self._redis.pipeline()
        pipe.rpush(key, json.dumps(msg, ensure_ascii=False))
        pipe.ltrim(key, -self.window * 2, -1)  # 临时保留 2 倍窗口, 等摘要压缩
        pipe.expire(key, self.ttl)
        pipe.expire(self._summary_key(session_id), self.ttl)
        pipe.execute()

        # 检查是否需要摘要压缩
        self._maybe_compress(session_id)

    def clear(self, session_id: str):
        """清空会话记忆(消息 + 摘要)"""
        self._redis.delete(self._key(session_id), self._summary_key(session_id))

    def _maybe_compress(self, session_id: str):
        """检查是否需要摘要压缩(异步触发, 不阻塞主流程)"""
        try:
            current_len = self._redis.llen(self._key(session_id))
            if current_len <= self.window:
                return

            # 取出超出窗口的早期消息
            overflow = current_len - self.window
            old_msgs_json = self._redis.lrange(self._key(session_id), 0, overflow - 1)

            if not old_msgs_json:
                return

            old_messages = []
            for mj in old_msgs_json:
                try:
                    old_messages.append(json.loads(mj))
                except json.JSONDecodeError:
                    continue

            # 生成摘要
            summary = self._generate_summary(session_id, old_messages)
            if summary:
                # 删除已摘要的旧消息
                self._redis.ltrim(self._key(session_id), overflow, -1)
                logger.info(f"会话 {session_id} 摘要压缩: {overflow} 条 -> 1 条摘要")
        except Exception as e:
            logger.warning(f"摘要压缩失败(不影响主流程): {e}")

    def _generate_summary(self, session_id: str, messages: List[Dict]) -> Optional[str]:
        """用 LLM 生成对话摘要"""
        try:
            from app.services.dashscope import dashscope_service

            # 获取已有摘要
            existing = self._redis.get(self._summary_key(session_id))
            existing_text = ""
            if existing:
                existing_text = json.loads(existing).get("content", "")

            # 构建摘要 prompt
            conv_text = "\n".join(
                f"{m.get('role', '?')}: {m.get('content', '')[:200]}" for m in messages
            )

            prompt = f"""请将以下对话内容压缩为简洁的摘要,保留关键信息(事实、偏好、决策)。

{"已有摘要: " + existing_text if existing_text else ""}
最新对话:
{conv_text[:2000]}

请输出更新后的摘要(不超过300字):"""

            result = dashscope_service.chat(
                [{"role": "user", "content": prompt}],
                tools=None,
                temperature=0.3,
            )
            summary_text = result.get("content", "").strip()

            if summary_text:
                summary_data = {
                    "content": summary_text,
                    "updated_at": datetime.now().isoformat(),
                }
                self._redis.setex(
                    self._summary_key(session_id),
                    self.ttl,
                    json.dumps(summary_data, ensure_ascii=False),
                )
                return summary_text
        except Exception as e:
            logger.warning(f"LLM 摘要生成失败: {e}")
        return None


class InMemoryStore(BaseMemory):
    """内存存储(仅单机开发降级使用, 不推荐生产)"""

    def __init__(self, max_messages: int = 50):
        from collections import defaultdict
        self._store: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.max_messages = max_messages
        logger.warning("⚠️ 使用内存会话记忆(仅开发模式, 分布式环境不可用)")

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._store[session_id])

    def add_message(self, session_id: str, role: str, content: str, **extra):
        msg = {"role": role, "content": content}
        msg.update(extra)
        self._store[session_id].append(msg)
        if len(self._store[session_id]) > self.max_messages:
            self._store[session_id] = self._store[session_id][-self.max_messages:]

    def clear(self, session_id: str):
        self._store.pop(session_id, None)


def create_memory() -> BaseMemory:
    """根据配置创建记忆存储实例(默认 Redis, 失败降级内存)"""
    if settings.memory_backend == "redis":
        try:
            return RedisShortTermMemory()
        except Exception as e:
            logger.warning(f"Redis 连接失败,降级为内存存储: {e}")
            return InMemoryStore()
    else:
        return InMemoryStore()


# 全局单例
memory_store = create_memory()
