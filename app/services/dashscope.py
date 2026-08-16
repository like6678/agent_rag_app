"""
通义千问 DashScope 大模型服务
- 使用 OpenAI 兼容接口调用(支持所有模型, 包括 2026 新模型 qwen3.7/qwen3.8)
- 对话 (支持 Function Call)
- 文本向量化 (Embedding)
- 每次调用前从 config_store 动态读取最新配置
"""
import os
import json
import requests
from typing import List, Dict, Any, Optional, Generator
from loguru import logger

from app.config import settings
from app.services.config_store import get_rag_config

# 默认 endpoint(国内版)
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 国际版 endpoint
INTL_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def _normalize_base_url(url: str) -> str:
    """规范化 base_url, 确保以 /compatible-mode/v1 结尾"""
    url = url.rstrip("/")
    # 如果已经包含 compatible-mode, 不再补全
    if "compatible-mode" in url:
        return url
    # 否则补全路径
    return url + "/compatible-mode/v1"


class DashScopeService:
    """通义千问大模型服务(OpenAI 兼容接口)"""

    def _get_runtime_config(self) -> Dict[str, Any]:
        """获取运行时配置(api_key / base_url / model 等)"""
        config = get_rag_config()
        api_key = config.get("dashscope_api_key") or settings.dashscope_api_key
        base_url = config.get("dashscope_base_url") or ""
        # base_url 为空时用默认国内版
        if not base_url:
            base_url = DEFAULT_BASE_URL
        else:
            base_url = _normalize_base_url(base_url)
        return {
            "api_key": api_key,
            "base_url": base_url,
            "chat_model": config.get("dashscope_chat_model") or settings.dashscope_chat_model,
            "embed_model": config.get("dashscope_embed_model") or settings.dashscope_embed_model,
            "temperature": config.get("temperature", 0.7),
            "config": config,
        }

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        对话接口(OpenAI 兼容, 支持 function calling)

        Args:
            messages: [{"role": "user|assistant|system", "content": "..."}]
            tools: 函数定义列表 (OpenAI function 格式)
            temperature: 温度(默认从 config 读)
        Returns:
            {"content": str, "tool_calls": list, "finish_reason": str, "raw": dict}
        """
        rt = self._get_runtime_config()
        api_key = rt["api_key"]
        base_url = rt["base_url"]
        chat_model = rt["chat_model"]
        if temperature is None:
            temperature = rt["temperature"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": chat_model,
            "messages": messages,
            "temperature": temperature,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        if tools:
            payload["tools"] = tools

        url = f"{base_url}/chat/completions"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            logger.error(f"DashScope 网络请求异常: {e}")
            raise RuntimeError(f"大模型网络请求异常: {e}")

        try:
            result = response.json()
        except ValueError:
            logger.error(f"DashScope 响应非 JSON: status={response.status_code}, body={response.text[:500]}")
            raise RuntimeError(f"大模型返回非 JSON 响应(HTTP {response.status_code})")

        if response.status_code != 200:
            error = result.get("error", {})
            error_msg = error.get("message", "") or response.text[:300]
            error_code = error.get("code", response.status_code)
            logger.error(
                f"DashScope 调用失败: model={chat_model}, url={url}, "
                f"code={error_code}, msg={error_msg}"
            )
            raise RuntimeError(f"大模型调用失败({error_code}): {error_msg}")

        choice = result.get("choices", [{}])[0]
        msg = choice.get("message", {})

        return {
            "content": msg.get("content", "") or "",
            "tool_calls": msg.get("tool_calls", []) or [],
            "finish_reason": choice.get("finish_reason", ""),
            "raw": result,
        }

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式对话(生成器, yield 每个 chunk)

        Yields:
            {"content": str, "tool_calls": list, "finish_reason": str|None}
            content 为本次增量文本; tool_calls 为增量工具调用
        """
        rt = self._get_runtime_config()
        api_key = rt["api_key"]
        base_url = rt["base_url"]
        chat_model = rt["chat_model"]
        if temperature is None:
            temperature = rt["temperature"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": chat_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if top_p is not None:
            payload["top_p"] = top_p
        if tools:
            payload["tools"] = tools

        url = f"{base_url}/chat/completions"
        try:
            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
        except requests.RequestException as e:
            logger.error(f"DashScope 流式请求异常: {e}")
            raise RuntimeError(f"大模型流式请求异常: {e}")

        if response.status_code != 200:
            try:
                err = response.json()
                error = err.get("error", {})
                raise RuntimeError(f"大模型调用失败({error.get('code', response.status_code)}): {error.get('message', '')}")
            except (ValueError, RuntimeError):
                raise RuntimeError(f"大模型调用失败(HTTP {response.status_code}): {response.text[:300]}")

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8", errors="ignore")
            if not line_str.startswith("data:"):
                continue
            data_str = line_str[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices", [])
            if not choices:
                # 部分 chunk(如 usage 统计)不含 choices, 跳过
                continue
            choice = choices[0]
            delta = choice.get("delta", {})
            yield {
                "content": delta.get("content", "") or "",
                "tool_calls": delta.get("tool_calls", []) or [],
                "finish_reason": choice.get("finish_reason"),
            }

    def embed(self, texts: List[str]) -> List[List[float]]:
        """文本向量化(OpenAI 兼容接口)"""
        if not texts:
            return []

        rt = self._get_runtime_config()
        api_key = rt["api_key"]
        base_url = rt["base_url"]
        embed_model = rt["embed_model"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        all_vectors: List[List[float]] = []
        url = f"{base_url}/embeddings"
        # 不同模型单次批量上限不同: text-embedding-v3 允许 25, qwen3.7-text-embedding 仅允许 20。
        # 取 20 作为安全默认; 若仍触发 batch size 限制, _embed_batch 会自动减半重试。
        batch_size = 20
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            all_vectors.extend(self._embed_batch(batch, url, headers, embed_model))

        logger.info(f"向量化完成: {len(texts)} 段文本 -> {len(all_vectors)} 个向量")
        return all_vectors

    def _embed_batch(
        self,
        batch: List[str],
        url: str,
        headers: Dict[str, str],
        embed_model: str,
    ) -> List[List[float]]:
        """单批向量化, 遇到 batch size 超限错误时自动减半重试(最多到 1)"""
        payload = {"model": embed_model, "input": batch}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            logger.error(f"Embedding 网络请求异常: {e}")
            raise RuntimeError(f"向量化网络请求异常: {e}")

        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(f"向量化返回非 JSON 响应(HTTP {response.status_code})")

        if response.status_code != 200:
            error = result.get("error", {})
            error_msg = error.get("message", "") or response.text[:300]
            # 批大小超限: 拆成两半递归重试, 兼容不同模型上限
            if "batch size" in error_msg.lower() and len(batch) > 1:
                mid = len(batch) // 2
                logger.warning(
                    f"Embedding 批大小超限(batch={len(batch)}), 减半重试: model={embed_model}"
                )
                return self._embed_batch(batch[:mid], url, headers, embed_model) + self._embed_batch(
                    batch[mid:], url, headers, embed_model
                )
            logger.error(
                f"Embedding 失败: model={embed_model}, code={error.get('code')}, msg={error_msg}"
            )
            raise RuntimeError(f"向量化失败: {error_msg}")

        # DashScope 返回的 data 按 input 顺序排列, 取 embedding
        return [item["embedding"] for item in result.get("data", [])]

    def embed_query(self, text: str) -> List[float]:
        """单条查询向量化"""
        vectors = self.embed([text])
        return vectors[0] if vectors else []


# 单例
dashscope_service = DashScopeService()