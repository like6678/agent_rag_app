"""
RAG 评测服务
- 对测试集执行完整 RAG 流程
- 用 LLM 评估检索质量和回答质量
- 生成五维度评测报告(切片/召回/重排/生成/向量库)
"""
import json
import re
from typing import List, Dict, Any
from loguru import logger

from app.services.dashscope import dashscope_service
from app.services.milvus import milvus_service
from app.services.config_store import get_rag_config
from app.rag.embedder import embedder
from app.rag.retriever import retriever
from app.rag.reranker import reranker


class EvaluationService:
    """RAG 系统评测"""

    def evaluate(
        self,
        test_items: List[Dict[str, Any]],
        override_config: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        执行评测

        Args:
            test_items: [{"question", "expected_answer", "expected_source"}]
            override_config: 评测时覆盖的配置
        Returns:
            EvalReport dict
        """
        config = get_rag_config()
        if override_config:
            config.update(override_config)

        logger.info(f"开始评测: {len(test_items)} 个测试项, 配置: top_k={config.get('retrieval_top_k')}, split={config.get('split_method')}")

        results: List[Dict[str, Any]] = []
        total_recall = 0
        sum_context_rel = 0.0
        sum_answer_faith = 0.0
        sum_answer_rel = 0.0

        for i, item in enumerate(test_items):
            question = item.get("question", "")
            expected = item.get("expected_answer", "")
            expected_source = item.get("expected_source", "")

            logger.info(f"评测 [{i+1}/{len(test_items)}]: {question[:50]}...")

            try:
                result = self._evaluate_single(question, expected, expected_source, config)
                results.append(result)

                if result["recall_hit"]:
                    total_recall += 1
                sum_context_rel += result["context_relevance"]
                sum_answer_faith += result["answer_faithfulness"]
                sum_answer_rel += result["answer_relevance"]
            except Exception as e:
                logger.error(f"评测项 {i+1} 失败: {e}")
                results.append({
                    "question": question,
                    "expected_answer": expected,
                    "retrieved_context": "",
                    "generated_answer": f"评测失败: {e}",
                    "recall_hit": False,
                    "context_relevance": 0.0,
                    "answer_faithfulness": 0.0,
                    "answer_relevance": 0.0,
                })

        n = len(results) or 1
        recall_rate = total_recall / n
        avg_context_rel = sum_context_rel / n
        avg_answer_faith = sum_answer_faith / n
        avg_answer_rel = sum_answer_rel / n

        # 五维度评分
        dimensions = self._compute_dimensions(
            config, recall_rate, avg_context_rel, avg_answer_faith, avg_answer_rel, results
        )

        # 综合评分(五维度加权平均)
        overall = sum(d["score"] for d in dimensions) / len(dimensions) if dimensions else 0

        report = {
            "total": len(results),
            "recall_rate": round(recall_rate, 4),
            "avg_context_relevance": round(avg_context_rel, 4),
            "avg_answer_faithfulness": round(avg_answer_faith, 4),
            "avg_answer_relevance": round(avg_answer_rel, 4),
            "overall_score": round(overall, 4),
            "dimensions": dimensions,
            "items": results,
            "config_snapshot": config,
        }

        logger.info(f"评测完成: 综合评分={overall:.2f}, 召回率={recall_rate:.2%}")
        return report

    def _evaluate_single(
        self, question: str, expected: str, expected_source: str, config: Dict
    ) -> Dict[str, Any]:
        """评测单个问题"""
        top_k = config.get("retrieval_top_k", 4)

        # 1. 检索
        hits = retriever.search(question, top_k=top_k)

        # 2. 重排(如果启用)
        if config.get("rerank_enabled") and config.get("rerank_model") != "none":
            hits = reranker.rerank(question, hits, method=config.get("rerank_model"), top_k=config.get("rerank_top_k", 3))

        retrieved_text = retriever.build_context(hits)

        # 3. 评估检索质量
        recall_hit, context_relevance = self._eval_retrieval(question, expected, expected_source, hits)

        # 4. 生成回答
        generated_answer = self._generate_answer(question, retrieved_text, config)

        # 5. 评估回答质量
        answer_faith, answer_rel = self._eval_answer(question, generated_answer, retrieved_text, expected)

        return {
            "question": question,
            "expected_answer": expected,
            "retrieved_context": retrieved_text[:500],
            "generated_answer": generated_answer,
            "recall_hit": recall_hit,
            "context_relevance": round(context_relevance, 4),
            "answer_faithfulness": round(answer_faith, 4),
            "answer_relevance": round(answer_rel, 4),
        }

    def _eval_retrieval(self, question, expected, expected_source, hits) -> tuple:
        """用 LLM 评估检索质量: 召回命中 + 上下文相关性"""
        if not hits:
            return False, 0.0

        retrieved_texts = [h.get("text", "")[:200] for h in hits]
        prompt = f"""请评估以下检索结果对回答用户问题的帮助程度。

用户问题: {question}
期望答案: {expected}
{'期望来源: ' + expected_source if expected_source else ''}

检索结果:
{json.dumps(retrieved_texts, ensure_ascii=False)}

请返回 JSON, 包含:
1. "recall_hit": 检索结果是否包含回答问题所需的信息(true/false)
2. "context_relevance": 检索结果与问题的相关性评分(0-1)

只返回 JSON, 不要其他内容。"""

        try:
            result = dashscope_service.chat(
                [{"role": "user", "content": prompt}], tools=None, temperature=0.1
            )
            content = result.get("content", "").strip()
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return bool(data.get("recall_hit", False)), float(data.get("context_relevance", 0))
        except Exception as e:
            logger.warning(f"检索评估失败: {e}")

        # 降级: 基于关键词重叠的简单判断
        hit = any(expected and expected[:20] in h.get("text", "") for h in hits) if expected else False
        return hit, 0.5

    def _generate_answer(self, question: str, context: str, config: Dict) -> str:
        """基于检索上下文生成回答"""
        if not context:
            return "未检索到相关信息,无法回答。"

        prompt = f"""请基于以下检索到的上下文回答问题。如果上下文中没有相关信息,请说明。

上下文:
{context[:3000]}

问题: {question}

回答:"""

        try:
            result = dashscope_service.chat(
                [{"role": "user", "content": prompt}],
                tools=None,
                temperature=config.get("temperature", 0.7),
            )
            return result.get("content", "").strip()
        except Exception as e:
            return f"生成失败: {e}"

    def _eval_answer(self, question, answer, context, expected) -> tuple:
        """用 LLM 评估回答质量: 忠实度 + 相关性"""
        prompt = f"""请评估以下回答的质量。

问题: {question}
{'期望答案: ' + expected if expected else ''}
检索上下文: {context[:1000]}
实际回答: {answer}

请返回 JSON, 包含:
1. "answer_faithfulness": 回答是否忠实于检索上下文(0-1, 不编造)
2. "answer_relevance": 回答与问题的相关性(0-1, 切题程度)

只返回 JSON, 不要其他内容。"""

        try:
            result = dashscope_service.chat(
                [{"role": "user", "content": prompt}], tools=None, temperature=0.1
            )
            content = result.get("content", "").strip()
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return float(data.get("answer_faithfulness", 0)), float(data.get("answer_relevance", 0))
        except Exception as e:
            logger.warning(f"回答评估失败: {e}")

        return 0.5, 0.5

    def _compute_dimensions(
        self, config, recall_rate, ctx_rel, ans_faith, ans_rel, results
    ) -> List[Dict[str, Any]]:
        """计算五维度评分(各 0-1)"""
        dims = []

        # 1. 切片参数维度
        chunk_size = config.get("chunk_size", 500)
        # 启发式: 500-1000 为最佳区间
        if 500 <= chunk_size <= 1000:
            split_score = 0.85
        elif 200 <= chunk_size < 500 or 1000 < chunk_size <= 1500:
            split_score = 0.7
        else:
            split_score = 0.5
        split_method = config.get("split_method", "recursive")
        method_bonus = {"recursive": 0.1, "semantic": 0.08, "structure": 0.08, "llm": 0.12, "sentence": 0.05, "fixed": 0.0}
        split_score = min(1.0, split_score + method_bonus.get(split_method, 0))
        dims.append({
            "name": "切片参数",
            "score": round(split_score, 2),
            "detail": f"方式={split_method}, 块大小={chunk_size}, 重叠={config.get('chunk_overlap', 50)}",
        })

        # 2. 召回参数维度
        dims.append({
            "name": "召回参数",
            "score": round(recall_rate, 2),
            "detail": f"top_k={config.get('retrieval_top_k', 4)}, metric={config.get('search_metric', 'COSINE')}, 召回率={recall_rate:.1%}",
        })

        # 3. 重排参数维度
        rerank_enabled = config.get("rerank_enabled", False)
        if rerank_enabled:
            rerank_score = min(1.0, ctx_rel + 0.1)  # 重排提升上下文相关性
            rerank_detail = f"已启用, 模型={config.get('rerank_model')}, 保留={config.get('rerank_top_k')}"
        else:
            rerank_score = ctx_rel * 0.8  # 未重排时维度分略低
            rerank_detail = "未启用重排"
        dims.append({
            "name": "重排参数",
            "score": round(rerank_score, 2),
            "detail": rerank_detail,
        })

        # 4. 生成参数维度
        gen_score = (ans_faith + ans_rel) / 2
        dims.append({
            "name": "生成参数",
            "score": round(gen_score, 2),
            "detail": f"模型={config.get('dashscope_chat_model')}, 温度={config.get('temperature', 0.7)}, 忠实度={ans_faith:.2f}, 相关性={ans_rel:.2f}",
        })

        # 5. 向量库参数维度
        embed_model = config.get("dashscope_embed_model", "text-embedding-v3")
        index_type = config.get("index_type", "IVF_FLAT")
        model_score = {"text-embedding-v3": 0.95, "text-embedding-v2": 0.85, "text-embedding-v1": 0.75}
        index_score = {"HNSW": 0.9, "IVF_FLAT": 0.85, "FLAT": 0.95}
        vec_score = (model_score.get(embed_model, 0.8) + index_score.get(index_type, 0.85)) / 2
        dims.append({
            "name": "向量库参数",
            "score": round(vec_score, 2),
            "detail": f"嵌入模型={embed_model}, 索引={index_type}, 维度={config.get('embed_dim', 1024)}",
        })

        return dims


evaluation_service = EvaluationService()
