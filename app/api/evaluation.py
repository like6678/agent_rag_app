"""
RAG 评测接口
- POST /api/evaluation/run  执行评测(传入测试问答集)
"""
from fastapi import APIRouter, HTTPException
from loguru import logger

from app.models.schemas import EvalRequest, EvalReport
from app.services.evaluation import evaluation_service

router = APIRouter()


@router.post("/run", response_model=EvalReport, summary="执行 RAG 评测")
def run_evaluation(req: EvalRequest):
    """
    执行 RAG 系统评测

    输入测试问答集, 系统对每个问题:
    1. 执行向量检索(可加重排)
    2. 用 LLM 评估检索质量(召回/上下文相关性)
    3. 基于检索结果生成回答
    4. 用 LLM 评估回答质量(忠实度/相关性)

    生成五维度评测报告:
    切片参数 / 召回参数 / 重排参数 / 生成参数 / 向量库参数
    """
    if not req.test_items:
        raise HTTPException(status_code=400, detail="测试集不能为空")

    try:
        report = evaluation_service.evaluate(
            test_items=[item.model_dump() for item in req.test_items],
            override_config=req.override_config if not req.use_current_config else None,
        )
        return EvalReport(**report)
    except Exception as e:
        logger.error(f"评测失败: {e}")
        raise HTTPException(status_code=500, detail=f"评测执行失败: {e}")
