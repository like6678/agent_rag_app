"""
文本切分器 - 支持 6 种切片方式
- recursive:  递归字符切片(默认, 通用性强)
- fixed:      固定大小切片(按字符数硬切)
- semantic:   语义感知切片(按段落/空行边界)
- structure:  文档结构切片(按 Markdown 标题/章节)
- sentence:   句子切片(按句子粒度)
- llm:        LLM 智能切片(用大模型按主题段落切分)
"""
import re
import json
from typing import List, Optional, Callable
from loguru import logger

from app.services.config_store import get_rag_config


class TextSplitter:
    """多策略文本切分器"""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        # 不在初始化时读 MySQL(避免启动时连接失败导致崩溃), 运行时在 split() 中按需读取
        self.chunk_size = chunk_size or 500
        self.chunk_overlap = chunk_overlap or 50
        self.separators = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]

    def split(
        self,
        text: str,
        method: str = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
        llm_split_fn: Optional[Callable[[str, int], List[str]]] = None,
    ) -> List[str]:
        """
        切分文本

        Args:
            text: 原始文本
            method: 切片方式 (recursive/fixed/semantic/structure/sentence/llm)
            chunk_size: 块大小(覆盖配置)
            chunk_overlap: 重叠(覆盖配置)
            llm_split_fn: LLM 切片的回调函数(method=llm 时使用)
        Returns:
            切分后的文本块列表
        """
        if not text or not text.strip():
            return []

        config = get_rag_config()
        method = method or config.get("split_method", "recursive")
        cs = chunk_size or self.chunk_size
        co = chunk_overlap or self.chunk_overlap

        dispatch = {
            "recursive": self._split_recursive,
            "fixed": self._split_fixed,
            "semantic": self._split_semantic,
            "structure": self._split_structure,
            "sentence": self._split_sentence,
            "llm": self._split_llm,
        }

        handler = dispatch.get(method, self._split_recursive)
        try:
            if method == "llm":
                chunks = handler(text, cs, llm_split_fn)
            else:
                chunks = handler(text, cs)
            # 统一后处理: 过滤空块 + 合并过小块 + 添加 overlap
            chunks = self._post_process(chunks, cs, co)
        except Exception as e:
            logger.warning(f"切片方式 {method} 失败,降级为递归字符切片: {e}")
            chunks = self._post_process(self._split_recursive(text, cs), cs, co)
            method = "recursive(fallback)"

        logger.info(f"文本切分[{method}]: {len(text)} 字符 -> {len(chunks)} 块 (size={cs}, overlap={co})")
        return chunks

    # ==================== 1. 递归字符切片(默认) ====================

    def _split_recursive(self, text: str, chunk_size: int) -> List[str]:
        """按分隔符递归切分"""
        if len(text) <= chunk_size:
            return [text]

        for sep in self.separators:
            if sep == "":
                continue
            if sep in text:
                parts = text.split(sep)
                chunks = []
                current = ""
                for part in parts:
                    candidate = current + sep + part if current else part
                    if len(candidate) <= chunk_size:
                        current = candidate
                    else:
                        if current:
                            chunks.append(current)
                        if len(part) > chunk_size:
                            chunks.extend(self._split_recursive(part, chunk_size))
                        else:
                            current = part
                if current:
                    chunks.append(current)
                return chunks
        # 无分隔符, 硬切
        return self._split_fixed(text, chunk_size)

    # ==================== 2. 固定大小切片 ====================

    def _split_fixed(self, text: str, chunk_size: int) -> List[str]:
        """按固定字符数硬切分"""
        chunks = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i : i + chunk_size])
        return chunks

    # ==================== 3. 语义感知切片 ====================

    def _split_semantic(self, text: str, chunk_size: int) -> List[str]:
        """按段落/空行等语义边界切分, 超长段落再递归切"""
        # 按双换行(段落)切分
        paragraphs = re.split(r"\n\s*\n", text)
        chunks = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(para) <= chunk_size:
                chunks.append(para)
            else:
                # 段落超长, 递归字符切分
                chunks.extend(self._split_recursive(para, chunk_size))
        return chunks

    # ==================== 4. 文档结构切片 ====================

    def _split_structure(self, text: str, chunk_size: int) -> List[str]:
        """按 Markdown 标题(#/##/###)或文档章节切分"""
        # 匹配 Markdown 标题行
        header_pattern = re.compile(r"^(#{1,6})\s+.+$", re.MULTILINE)

        # 如果没有标题, 按段落切分降级
        if not header_pattern.search(text):
            return self._split_semantic(text, chunk_size)

        # 按标题切分
        sections = []
        current_header = ""
        current_content = []

        for line in text.split("\n"):
            if header_pattern.match(line.strip()):
                # 保存前一个 section
                if current_content:
                    section = (current_header + "\n" if current_header else "") + "\n".join(current_content)
                    sections.append(section.strip())
                current_header = line.strip()
                current_content = []
            else:
                current_content.append(line)

        # 最后一个 section
        if current_content:
            section = (current_header + "\n" if current_header else "") + "\n".join(current_content)
            sections.append(section.strip())

        # 超长 section 再递归切
        chunks = []
        for sec in sections:
            if not sec:
                continue
            if len(sec) <= chunk_size:
                chunks.append(sec)
            else:
                chunks.extend(self._split_recursive(sec, chunk_size))
        return chunks

    # ==================== 5. 句子切片 ====================

    def _split_sentence(self, text: str, chunk_size: int) -> List[str]:
        """按句子粒度切分, 多句合并到 chunk_size"""
        # 中英文句子分隔
        sentences = re.split(r"(?<=[。！？.!?])\s*", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current = ""
        for sent in sentences:
            if len(sent) > chunk_size:
                # 单句超长, 递归切
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_recursive(sent, chunk_size))
            else:
                candidate = current + " " + sent if current else sent
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    current = sent
        if current:
            chunks.append(current)
        return chunks

    # ==================== 6. LLM 智能切片 ====================

    def _split_llm(
        self,
        text: str,
        chunk_size: int,
        llm_split_fn: Optional[Callable[[str, int], List[str]]] = None,
    ) -> List[str]:
        """
        用大模型按主题段落切分
        llm_split_fn: 回调(text, chunk_size) -> List[str]
        如果未提供回调, 降级为语义感知切片
        """
        if llm_split_fn is None:
            logger.info("LLM 切片未提供回调,降级为语义感知切片")
            return self._split_semantic(text, chunk_size)

        try:
            chunks = llm_split_fn(text, chunk_size)
            if chunks and isinstance(chunks, list):
                return chunks
            logger.warning("LLM 切片返回空,降级为语义感知切片")
            return self._split_semantic(text, chunk_size)
        except Exception as e:
            logger.warning(f"LLM 切片失败: {e},降级为语义感知切片")
            return self._split_semantic(text, chunk_size)

    # ==================== 后处理 ====================

    def _post_process(self, chunks: List[str], chunk_size: int, overlap: int) -> List[str]:
        """后处理: 过滤空块 + 合并过小块 + 添加重叠"""
        # 过滤空块
        chunks = [c.strip() for c in chunks if c and c.strip()]
        if not chunks:
            return []

        # 合并过小块(小于 chunk_size 的 1/4)
        min_len = max(chunk_size // 4, 50)
        merged = []
        for c in chunks:
            if merged and len(merged[-1]) < min_len and len(merged[-1]) + len(c) <= chunk_size:
                merged[-1] = merged[-1] + "\n" + c
            else:
                merged.append(c)

        # 添加 overlap
        if overlap > 0 and len(merged) > 1:
            result = [merged[0]]
            for i in range(1, len(merged)):
                prev_tail = merged[i - 1][-overlap:]
                result.append(prev_tail + merged[i])
            return result
        return merged


text_splitter = TextSplitter()


def llm_split_callback(text: str, chunk_size: int) -> List[str]:
    """
    LLM 智能切片回调(调用通义千问)
    让大模型按主题将文本切分为不超过 chunk_size 的段落
    """
    from app.services.dashscope import dashscope_service

    prompt = f"""请将以下文本按主题/语义切分为多个段落,每个段落不超过{chunk_size}个字符。
要求:
1. 保持语义完整性,不要在句子中间切断
2. 返回 JSON 数组格式,每个元素是一个切分后的文本段落
3. 不要添加任何额外说明,只返回 JSON 数组

文本:
{text[:8000]}"""

    messages = [
        {"role": "system", "content": "你是一个文本切分助手,只返回JSON数组。"},
        {"role": "user", "content": prompt},
    ]

    result = dashscope_service.chat(messages, tools=None, temperature=0.1)
    content = result.get("content", "").strip()

    # 提取 JSON 数组
    try:
        # 尝试直接解析
        chunks = json.loads(content)
        if isinstance(chunks, list):
            return [str(c) for c in chunks]
    except json.JSONDecodeError:
        # 尝试提取 JSON 数组部分
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            try:
                chunks = json.loads(match.group())
                if isinstance(chunks, list):
                    return [str(c) for c in chunks]
            except json.JSONDecodeError:
                pass

    # 解析失败, 返回按段落切分的降级结果
    logger.warning("LLM 切片 JSON 解析失败,降级段落切分")
    return text.split("\n\n")
