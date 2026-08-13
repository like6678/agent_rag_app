"""
向量库检索器
- 查询向量化 -> Milvus 检索 -> 拼接上下文
"""
from typing import List, Dict, Any
from loguru import logger

from app.services.milvus import milvus_service
from app.rag.embedder import embedder
from app.config import settings


class Retriever:
    """向量检索器"""

    @staticmethod
    def search(query: str, top_k: int = None) -> List[Dict[str, Any]]:
        """
        检索相关知识片段

        Args:
            query: 用户查询
            top_k: 返回数量
        Returns:
            [{"text", "doc_id", "source", "score", ...}]
        """
        top_k = top_k or settings.retrieval_top_k

        # 1. 查询向量化
        query_vector = embedder.embed_query(query)

        # 2. Milvus 检索
        hits = milvus_service.search(query_vector, top_k=top_k)

        logger.info(f"检索查询: '{query[:50]}...' -> {len(hits)} 条结果")
        return hits

    @staticmethod
    def build_context(hits: List[Dict[str, Any]]) -> str:
        """将检索结果拼接为上下文文本"""
        if not hits:
            return ""

        parts = []
        for i, hit in enumerate(hits, 1):
            source = hit.get("source", "未知")
            score = hit.get("score", 0)
            text = hit.get("text", "")
            parts.append(f"[片段{i}] (来源: {source}, 相似度: {score:.3f})\n{text}")

        return "\n\n".join(parts)


retriever = Retriever()
