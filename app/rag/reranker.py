"""
重排器 - 对向量检索结果进行二次排序
- llm: 用大模型对检索结果按相关性重新打分排序
- none: 不重排, 直接返回原序
"""
import json
from typing import List, Dict, Any
from loguru import logger

from app.services.dashscope import dashscope_service
from app.services.config_store import get_rag_config


class Reranker:
    """检索结果重排器"""

    def rerank(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        method: str = None,
        top_k: int = None,
    ) -> List[Dict[str, Any]]:
        """
        对检索结果重排

        Args:
            query: 用户查询
            hits: 原始检索结果
            method: 重排方法 (none/llm)
            top_k: 重排后保留数量
        Returns:
            重排后的结果列表
        """
        config = get_rag_config()
        method = method or config.get("rerank_model", "none")
        top_k = top_k or config.get("rerank_top_k", 3)

        if not hits or method == "none":
            return hits[:top_k] if top_k else hits

        if method == "llm":
            return self._rerank_llm(query, hits, top_k)

        return hits[:top_k] if top_k else hits

    def _rerank_llm(
        self, query: str, hits: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        """用大模型对检索结果按与查询的相关性重新排序"""
        # 构造候选列表(截断避免过长)
        candidates = []
        for i, hit in enumerate(hits):
            text = (hit.get("text") or "")[:200]
            candidates.append({"index": i, "text": text, "score": hit.get("score", 0)})

        prompt = f"""请根据查询对以下检索结果按相关性从高到低排序。
查询: {query}

检索结果:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

请返回 JSON 数组, 按相关性从高到低排列, 每个元素包含 index 和 relevance_score(0-1)。
只返回 JSON 数组, 不要其他内容。"""

        try:
            result = dashscope_service.chat(
                [{"role": "user", "content": prompt}],
                tools=None,
                temperature=0.1,
            )
            content = result.get("content", "").strip()

            # 解析排序结果
            import re
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if not match:
                logger.warning("LLM 重排解析失败,返回原序")
                return hits[:top_k]

            ranked = json.loads(match.group())
            reranked_hits = []
            for item in ranked:
                idx = item.get("index")
                if idx is not None and 0 <= idx < len(hits):
                    hit = dict(hits[idx])
                    hit["rerank_score"] = item.get("relevance_score", 0)
                    reranked_hits.append(hit)

            if reranked_hits:
                logger.info(f"LLM 重排完成: {len(hits)} -> {len(reranked_hits[:top_k])}")
                return reranked_hits[:top_k]

        except Exception as e:
            logger.warning(f"LLM 重排失败: {e},返回原序")

        return hits[:top_k]


reranker = Reranker()
