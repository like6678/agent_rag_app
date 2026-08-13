"""
向量化服务 - 封装 DashScope Embedding
"""
from typing import List
from loguru import logger

from app.services.dashscope import dashscope_service


class Embedder:
    """文本向量化封装"""

    @staticmethod
    def embed_documents(texts: List[str]) -> List[List[float]]:
        """批量文档向量化"""
        if not texts:
            return []
        return dashscope_service.embed(texts)

    @staticmethod
    def embed_query(text: str) -> List[float]:
        """查询向量化"""
        return dashscope_service.embed_query(text)


embedder = Embedder()
