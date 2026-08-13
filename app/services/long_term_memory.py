"""
长期记忆 - 三层记忆之第二层
- MySQL 结构化存储(记忆实体 CRUD + 重要度打分)
- Milvus 语义召回(独立集合, user_id 过滤做用户隔离)
- 相似度去重(新增时检索, 超阈值跳过)
- 时间衰减遗忘(importance_score 随时间衰减)

注: RAG 知识库记忆(knowledge_base 集合)独立于本模块, 用于业务文档检索
"""
import uuid
import math
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from pymilvus import MilvusClient, DataType

from app.config import settings
from app.services.mysql import mysql_service
from app.services.dashscope import dashscope_service
from app.services.config_store import get_rag_config

# 长期记忆 Milvus 集合名(独立于 RAG knowledge_base)
LTM_COLLECTION = "long_term_memory"


class LongTermMemoryService:
    """长期记忆服务(MySQL + Milvus)"""

    def __init__(self):
        self._client: Optional[MilvusClient] = None

    def _get_client(self) -> MilvusClient:
        if self._client is None:
            uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
            self._client = MilvusClient(uri=uri)
            logger.info(f"长期记忆连接 Milvus: {uri}")
        return self._client

    def ensure_collection(self):
        """确保长期记忆 Milvus 集合存在"""
        client = self._get_client()
        if client.has_collection(LTM_COLLECTION):
            return

        config = get_rag_config()
        dim = config.get("embed_dim", settings.embed_dim)

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
        schema.add_field("content", DataType.VARCHAR, max_length=65535)
        schema.add_field("user_id", DataType.VARCHAR, max_length=64)
        schema.add_field("memory_id", DataType.VARCHAR, max_length=64)
        schema.add_field("importance_score", DataType.FLOAT)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )

        client.create_collection(
            collection_name=LTM_COLLECTION,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"长期记忆 Milvus 集合创建: {LTM_COLLECTION}")

    def init_all(self):
        """初始化 MySQL 表 + Milvus 集合"""
        mysql_service.init_tables()
        self.ensure_collection()

    # ==================== 核心功能 ====================

    def add_memory(
        self,
        user_id: str,
        content: str,
        importance: Optional[float] = None,
        summary: str = "",
    ) -> Dict[str, Any]:
        """
        新增长期记忆
        1. 重要度打分(未指定时用 LLM 评估)
        2. 向量化
        3. 相似度去重(检索已有记忆, 超阈值跳过)
        4. 存入 MySQL + Milvus
        """
        self.ensure_collection()

        # 1. 重要度打分
        if importance is None:
            importance = self._score_importance(content)

        # 2. 向量化
        vector = dashscope_service.embed_query(content)

        # 3. 相似度去重
        duplicates = self._search_milvus(user_id, vector, top_k=1)
        if duplicates:
            max_sim = duplicates[0].get("score", 0)
            if max_sim >= settings.memory_dedup_threshold:
                logger.info(f"长期记忆去重跳过: 相似度={max_sim:.3f} >= {settings.memory_dedup_threshold}")
                return {
                    "action": "duplicated",
                    "existing_memory_id": duplicates[0].get("memory_id"),
                    "similarity": max_sim,
                    "message": "记忆已存在(相似度去重), 跳过新增",
                }

        # 4. 存储
        memory_id = str(uuid.uuid4())
        milvus_id = f"ltm_{memory_id}"

        # MySQL
        mysql_service.execute(
            """
            INSERT INTO long_term_memories
                (memory_id, user_id, content, summary, importance_score, milvus_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
            """,
            (memory_id, user_id, content, summary, importance, milvus_id),
        )

        # Milvus
        client = self._get_client()
        client.insert(
            collection_name=LTM_COLLECTION,
            data=[{
                "id": milvus_id,
                "vector": vector,
                "content": content[:60000],
                "user_id": user_id,
                "memory_id": memory_id,
                "importance_score": importance,
            }],
        )

        logger.info(f"长期记忆新增: user={user_id}, id={memory_id}, importance={importance:.2f}")
        return {
            "action": "created",
            "memory_id": memory_id,
            "importance_score": importance,
            "message": "记忆已存储",
        }

    def search_memory(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        语义检索长期记忆(带 user_id 隔离)
        返回结果含动态衰减后的重要度
        """
        self.ensure_collection()
        vector = dashscope_service.embed_query(query)
        hits = self._search_milvus(user_id, vector, top_k=top_k * 2)

        results = []
        for hit in hits:
            memory_id = hit.get("memory_id")
            # 从 MySQL 获取完整信息
            record = mysql_service.query_one(
                "SELECT * FROM long_term_memories WHERE memory_id = %s AND status = 'active'",
                (memory_id,),
            )
            if not record:
                continue

            # 动态计算衰减后重要度
            decayed_score = self._decay_score(
                record["importance_score"],
                record["last_accessed_at"],
            )
            if decayed_score < min_importance:
                continue

            # 更新访问计数和时间
            mysql_service.execute(
                "UPDATE long_term_memories SET access_count = access_count + 1, last_accessed_at = NOW() WHERE memory_id = %s",
                (memory_id,),
            )

            results.append({
                "memory_id": memory_id,
                "content": record["content"],
                "summary": record.get("summary", ""),
                "importance_score": round(decayed_score, 4),
                "original_importance": record["importance_score"],
                "similarity": hit.get("score", 0),
                "access_count": record["access_count"] + 1,
                "created_at": str(record["created_at"]),
                "last_accessed_at": str(record["last_accessed_at"]),
            })

            if len(results) >= top_k:
                break

        logger.info(f"长期记忆检索: user={user_id}, query='{query[:30]}...' -> {len(results)} 条")
        return results

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """获取单条记忆"""
        return mysql_service.query_one(
            "SELECT * FROM long_term_memories WHERE memory_id = %s",
            (memory_id,),
        )

    def list_memories(
        self,
        user_id: str,
        status: str = "active",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出用户所有记忆"""
        return mysql_service.query(
            "SELECT * FROM long_term_memories WHERE user_id = %s AND status = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, status, limit),
        )

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        summary: Optional[str] = None,
    ) -> bool:
        """更新记忆(内容变更时同步更新 Milvus 向量)"""
        record = self.get_memory(memory_id)
        if not record:
            return False

        sets = []
        args = []
        if content is not None:
            sets.append("content = %s")
            args.append(content)
        if importance is not None:
            sets.append("importance_score = %s")
            args.append(importance)
        if summary is not None:
            sets.append("summary = %s")
            args.append(summary)

        if sets:
            args.append(memory_id)
            mysql_service.execute(
                f"UPDATE long_term_memories SET {', '.join(sets)} WHERE memory_id = %s",
                tuple(args),
            )

        # 内容变更时更新 Milvus 向量
        if content is not None:
            self._update_milvus_vector(memory_id, content, record["user_id"], record.get("importance_score", 0.5))

        return True

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆(MySQL + Milvus)"""
        record = self.get_memory(memory_id)
        if not record:
            return False

        # 删除 Milvus
        try:
            client = self._get_client()
            client.delete(collection_name=LTM_COLLECTION, filter=f'memory_id == "{memory_id}"')
        except Exception as e:
            logger.warning(f"删除 Milvus 记忆失败: {e}")

        # 删除 MySQL
        mysql_service.execute("DELETE FROM long_term_memories WHERE memory_id = %s", (memory_id,))
        logger.info(f"长期记忆删除: {memory_id}")
        return True

    def apply_decay(self, threshold: float = 0.05) -> int:
        """
        执行时间衰减遗忘: 将衰减后重要度低于阈值的记忆标记为 forgotten
        Returns: 被遗忘的记忆数
        """
        records = mysql_service.query(
            "SELECT memory_id, importance_score, last_accessed_at FROM long_term_memories WHERE status = 'active'"
        )
        forgotten = 0
        for r in records:
            decayed = self._decay_score(r["importance_score"], r["last_accessed_at"])
            if decayed < threshold:
                mysql_service.execute(
                    "UPDATE long_term_memories SET status = 'forgotten' WHERE memory_id = %s",
                    (r["memory_id"],),
                )
                forgotten += 1

        logger.info(f"时间衰减遗忘: {forgotten}/{len(records)} 条记忆被标记为 forgotten")
        return forgotten

    def consolidate_from_short_term(
        self,
        user_id: str,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        从短期会话记忆沉淀到长期记忆
        用 LLM 从对话中提取值得长期记住的信息
        """
        if not messages:
            return []

        conv_text = "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')[:300]}" for m in messages[-20:]
        )

        prompt = f"""请从以下对话中提取值得长期记住的信息(用户偏好、事实、重要决策等)。
每条记忆用 JSON 数组格式输出, 每个元素: {{"content": "记忆内容", "importance": 0.0-1.0}}
如果没有值得记住的信息, 返回空数组 []

对话:
{conv_text[:3000]}

只返回 JSON 数组:"""

        try:
            result = dashscope_service.chat(
                [{"role": "user", "content": prompt}],
                tools=None,
                temperature=0.3,
            )
            import re
            import json
            content = result.get("content", "").strip()
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if not match:
                return []
            items = json.loads(match.group())

            added = []
            for item in items:
                mem_content = item.get("content", "").strip()
                importance = float(item.get("importance", 0.5))
                if mem_content:
                    res = self.add_memory(user_id, mem_content, importance=importance)
                    added.append(res)
            logger.info(f"长期记忆沉淀: 从短期记忆提取 {len(added)} 条")
            return added
        except Exception as e:
            logger.warning(f"长期记忆沉淀失败: {e}")
            return []

    # ==================== 内部方法 ====================

    def _search_milvus(
        self, user_id: str, vector: List[float], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Milvus 语义检索(带 user_id 过滤)"""
        client = self._get_client()
        results = client.search(
            collection_name=LTM_COLLECTION,
            data=[vector],
            anns_field="vector",
            limit=top_k,
            search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
            filter=f'user_id == "{user_id}"',
            output_fields=["content", "user_id", "memory_id", "importance_score"],
        )
        hits = []
        for hit in (results[0] if results else []):
            if isinstance(hit, dict):
                entity = hit.get("entity", {}) or {}
                hits.append({
                    "id": hit.get("id"),
                    "score": float(hit.get("distance", 0)),
                    "content": entity.get("content"),
                    "user_id": entity.get("user_id"),
                    "memory_id": entity.get("memory_id"),
                    "importance_score": entity.get("importance_score"),
                })
        return hits

    def _update_milvus_vector(
        self, memory_id: str, content: str, user_id: str, importance: float
    ):
        """更新 Milvus 中的记忆向量"""
        client = self._get_client()
        # 先删除旧向量
        try:
            client.delete(collection_name=LTM_COLLECTION, filter=f'memory_id == "{memory_id}"')
        except Exception:
            pass

        # 重新插入
        vector = dashscope_service.embed_query(content)
        milvus_id = f"ltm_{memory_id}"
        client.insert(
            collection_name=LTM_COLLECTION,
            data=[{
                "id": milvus_id,
                "vector": vector,
                "content": content[:60000],
                "user_id": user_id,
                "memory_id": memory_id,
                "importance_score": importance,
            }],
        )

    def _score_importance(self, content: str) -> float:
        """用 LLM 评估记忆重要度(0-1)"""
        try:
            prompt = f"""请评估以下信息作为长期记忆的重要度(0-1分)。
评分标准:
- 0.9-1.0: 核心偏好/身份/关键事实
- 0.7-0.8: 重要信息/常用需求
- 0.4-0.6: 一般信息/上下文
- 0.1-0.3: 临时/琐碎信息

信息: {content[:500]}

只返回一个0到1的数字:"""

            result = dashscope_service.chat(
                [{"role": "user", "content": prompt}],
                tools=None,
                temperature=0.1,
            )
            score_str = result.get("content", "0.5").strip()
            import re
            match = re.search(r"[0-9]+\.?[0-9]*", score_str)
            if match:
                score = float(match.group())
                return max(0.0, min(1.0, score))
        except Exception as e:
            logger.warning(f"重要度评分失败: {e}")
        return 0.5

    def _decay_score(self, base_score: float, last_accessed: Any) -> float:
        """
        时间衰减: score = base * exp(-lambda * days)
        越久没访问, 重要度越低
        """
        if isinstance(last_accessed, str):
            try:
                last_accessed = datetime.fromisoformat(last_accessed.replace("Z", ""))
            except (ValueError, TypeError):
                return base_score

        if not isinstance(last_accessed, datetime):
            return base_score

        days = (datetime.now() - last_accessed).total_seconds() / 86400
        decayed = base_score * math.exp(-settings.memory_decay_lambda * days)
        return max(0.0, min(1.0, decayed))


# 单例
long_term_memory = LongTermMemoryService()
