"""
向量库检索器
- 查询向量化 -> Milvus 检索 -> 拼接上下文
"""
from typing import List, Dict, Any
from loguru import logger

from app.services.milvus import milvus_service
from app.services.config_store import get_rag_config
from app.rag.embedder import embedder


class Retriever:
    """向量检索器(读取运行时配置: top_k / 重排开关)"""

    @staticmethod
    def search(query: str, top_k: int = None) -> List[Dict[str, Any]]:
        """
        检索相关知识片段

        配置联动:
        - top_k 缺省时读取配置中心 retrieval_top_k(配置页改动实时生效)
        - 配置开启重排(rerank_enabled + rerank_model != none)时,
          先放大召回(2 倍), 再用重排器截断到 top_k, 提升最终上下文相关性

        Args:
            query: 用户查询
            top_k: 返回数量
        Returns:
            [{"text", "doc_id", "source", "score", ...}]
        """
        config = get_rag_config()
        top_k = top_k or config.get("retrieval_top_k", 4)

        # 1. 查询向量化
        query_vector = embedder.embed_query(query)

        # 2. Milvus 检索(启用重排时放大召回, 给重排留出候选空间)
        rerank_on = config.get("rerank_enabled") and config.get("rerank_model", "none") != "none"
        recall_k = top_k * 2 if rerank_on else top_k
        hits = milvus_service.search(query_vector, top_k=recall_k)

        # 3. 可选重排(此前重排只在评测链路生效, 真实对话检索不走重排, 配置形同虚设)
        if rerank_on and hits:
            from app.rag.reranker import reranker
            hits = reranker.rerank(query, hits, method=config.get("rerank_model"), top_k=top_k)
        else:
            hits = hits[:top_k]

        logger.info(f"检索查询: '{query[:50]}...' -> {len(hits)} 条结果 (rerank={'on' if rerank_on else 'off'})")
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
