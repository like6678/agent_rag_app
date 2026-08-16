"""
Agent 核心
- 基于 Function Call 的工具调用循环
- 多轮对话记忆管理
- RAG 上下文增强
"""
from typing import List, Dict, Any, Optional
from loguru import logger

from app.services.dashscope import dashscope_service
from app.agent.memory import memory_store
from app.agent.tools import TOOLS_SCHEMA, execute_tool
from app.config import settings


def _recall_long_term_memories(user_id: str, query: str, top_k: int = 3) -> str:
    """语义召回用户的相关长期记忆, 拼接为 system 上下文
    失败(如 Milvus/MySQL 未就绪)时静默降级, 不影响主对话流程
    """
    try:
        from app.services.long_term_memory import long_term_memory
        memories = long_term_memory.search_memory(user_id=user_id, query=query, top_k=top_k)
        if not memories:
            return ""
        lines = [f"- {m['content']} (重要度: {m['importance_score']:.2f})" for m in memories]
        return "以下是该用户的长期记忆(偏好/事实/历史决策), 回答时请结合参考:\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"长期记忆召回失败(降级跳过): {e}")
        return ""


SYSTEM_PROMPT = """你是一个智能助手,可以调用工具来回答用户问题。

你可以使用以下能力:
1. knowledge_search - 从知识库检索相关文档
2. list_documents - 列出已上传的文档
3. knowledge_base_stats - 查看知识库统计

工作原则:
- 当用户的问题可能涉及已上传文档时,优先使用 knowledge_search 检索后再回答
- 对于一般性闲聊或常识问题,可以直接回答
- 回答要基于检索到的内容,不要编造;如果知识库中没有相关信息,请如实告知
- 回答使用中文
"""


class Agent:
    """Agent 核心: 管理 Function Call 循环与多轮对话"""

    def __init__(self):
        self.tools = TOOLS_SCHEMA

    def chat(
        self,
        session_id: str,
        user_message: str,
        use_rag: bool = True,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        多轮对话主入口

        Args:
            session_id: 会话ID(用于记忆隔离)
            user_message: 用户消息
            use_rag: 是否启用 RAG + 工具调用
            user_id: 用户ID(可选, 提供后注入相关长期记忆)
        Returns:
            {"answer": str, "tool_calls_made": list, "session_id": str}
        """
        # 1. 获取历史记忆
        history = memory_store.get_messages(session_id)

        # 2. 构建消息列表
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 2.1 注入长期记忆(语义召回与当前问题相关的用户记忆)
        if user_id:
            ltm_context = _recall_long_term_memories(user_id, user_message)
            if ltm_context:
                messages.append({"role": "system", "content": ltm_context})

        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # 3. 记录用户消息
        memory_store.add_message(session_id, "user", user_message)

        tool_calls_made = []

        if not use_rag:
            # 纯对话模式: 不带工具
            result = dashscope_service.chat(messages, tools=None)
            answer = result["content"]
            memory_store.add_message(session_id, "assistant", answer)
            return {"answer": answer, "tool_calls_made": [], "session_id": session_id}

        # 4. Function Call 循环
        answer = ""
        for iteration in range(settings.max_tool_iterations):
            result = dashscope_service.chat(messages, tools=self.tools)

            # 无工具调用,直接返回
            if not result["tool_calls"]:
                answer = result["content"]
                break

            # 处理工具调用
            # 先把 assistant 的工具调用消息加入对话
            assistant_msg = {"role": "assistant", "content": result["content"] or "", "tool_calls": result["tool_calls"]}
            messages.append(assistant_msg)

            for tc in result["tool_calls"]:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                import json
                try:
                    tool_args = json.loads(fn.get("arguments", "{}"))
                except Exception:
                    tool_args = {}

                tool_result = execute_tool(tool_name, tool_args)
                tool_calls_made.append({"name": tool_name, "arguments": tool_args, "result_preview": tool_result[:200]})

                # 将工具结果作为 tool 角色消息加入对话
                # 必须携带 tool_call_id, 与 assistant 消息中的 tool_calls 一一对应,
                # 否则 OpenAI 兼容接口在下一轮请求会报 400 (协议要求)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": tool_result,
                    "name": tool_name,
                })

            # 继续循环,让模型基于工具结果生成回复
        else:
            # 达到最大迭代仍无最终回复,强制生成一次
            logger.warning(f"会话 {session_id} 达到最大工具调用迭代,强制生成回复")
            result = dashscope_service.chat(messages, tools=None)
            answer = result["content"] or "抱歉,处理您的问题时遇到了一些困难。"

        # 5. 记录助手回复
        memory_store.add_message(session_id, "assistant", answer)

        return {"answer": answer, "tool_calls_made": tool_calls_made, "session_id": session_id}

    def reset_session(self, session_id: str):
        """清空会话记忆"""
        memory_store.clear(session_id)
        logger.info(f"已清空会话: {session_id}")

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话历史"""
        return memory_store.get_messages(session_id)


# 单例
agent = Agent()
