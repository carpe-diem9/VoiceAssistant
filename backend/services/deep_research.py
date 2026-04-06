"""
Deep Research 引擎 - 针对复杂问题进行多轮推理、信息整合
支持流式返回中间推理步骤和最终结果
"""
import logging
import json
from typing import List, Dict, AsyncGenerator
from services.llm_service import llm_service

logger = logging.getLogger(__name__)


class DeepResearchService:
    """Deep Research 服务 - 多轮推理与信息整合"""

    def __init__(self):
        self.max_rounds = 3  # 最大推理轮数

    async def research(self, question: str,
                       context_messages: List[Dict[str, str]] = None) -> AsyncGenerator[dict, None]:
        """
        执行 Deep Research 流程
        :param question: 用户的研究问题
        :param context_messages: 会话上下文
        :yields: 包含步骤信息的字典
            - {"type": "step", "step": int, "title": str, "content": str}
            - {"type": "thinking", "content": str}
            - {"type": "final", "content": str}
        """
        context = context_messages or []

        # 第1步：分析问题，制定研究计划
        yield {"type": "step", "step": 1, "title": "分析问题", "content": "正在分析您的问题，制定研究计划..."}

        analysis_prompt = [
            *context,
            {
                "role": "user",
                "content": (
                    f"请仔细分析以下问题，将其分解为2-3个需要深入研究的子问题，并为每个子问题制定简短的研究方向。"
                    f"请用JSON格式回复: {{\"sub_questions\": [\"子问题1\", \"子问题2\", ...]}}\n\n"
                    f"问题: {question}"
                )
            }
        ]

        analysis_result = await llm_service.chat(analysis_prompt)
        yield {"type": "thinking", "content": f"问题分析完成:\n{analysis_result}"}

        # 尝试解析子问题
        sub_questions = [question]
        try:
            # 尝试从回复中提取 JSON
            start = analysis_result.find('{')
            end = analysis_result.rfind('}') + 1
            if start >= 0 and end > start:
                parsed = json.loads(analysis_result[start:end])
                sub_questions = parsed.get("sub_questions", [question])
        except (json.JSONDecodeError, KeyError):
            pass

        # 第2步：对每个子问题进行深入研究
        research_results = []
        for i, sub_q in enumerate(sub_questions[:3]):  # 最多3个子问题
            step_num = i + 2
            yield {
                "type": "step", "step": step_num,
                "title": f"研究子问题 {i + 1}",
                "content": f"正在研究: {sub_q}"
            }

            research_prompt = [
                *context,
                {
                    "role": "user",
                    "content": (
                        f"请针对以下问题进行深入分析和研究，提供详细、准确的信息和见解。\n\n"
                        f"原始问题: {question}\n"
                        f"当前研究方向: {sub_q}\n\n"
                        f"请提供详细的分析和发现。"
                    )
                }
            ]

            result = await llm_service.chat(research_prompt)
            research_results.append({"question": sub_q, "result": result})

            # 流式输出中间结果
            yield {"type": "thinking", "content": f"子问题 {i + 1} 研究结果:\n{result[:200]}..."}

        # 第3步：综合整理最终结果
        final_step = len(sub_questions[:3]) + 2
        yield {
            "type": "step", "step": final_step,
            "title": "综合分析",
            "content": "正在整合所有研究结果，生成最终报告..."
        }

        # 构建综合提示
        research_summary = "\n\n".join([
            f"### 研究方向 {i + 1}: {r['question']}\n{r['result']}"
            for i, r in enumerate(research_results)
        ])

        synthesis_prompt = [
            *context,
            {
                "role": "user",
                "content": (
                    f"请基于以下研究结果，为原始问题提供一个全面、结构化的最终回答。\n\n"
                    f"原始问题: {question}\n\n"
                    f"各子问题研究结果:\n{research_summary}\n\n"
                    f"请综合以上所有信息，提供一个结构清晰、逻辑严密的完整回答。"
                )
            }
        ]

        # 流式输出最终结果
        full_response = ""
        async for chunk in llm_service.chat_stream(synthesis_prompt):
            full_response += chunk
            yield {"type": "final_chunk", "content": chunk}

        yield {"type": "final", "content": full_response}


# 全局 Deep Research 服务实例
deep_research_service = DeepResearchService()
