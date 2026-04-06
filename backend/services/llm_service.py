"""
LLM 服务 - 使用 Qwen LLM (qwen3.5-plus) 进行对话推理
通过 OpenAI 兼容接口调用，支持流式输出
"""
import logging
from typing import List, Dict, AsyncGenerator
from openai import OpenAI
from config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """大语言模型服务"""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        self.model = settings.LLM_MODEL
        self.system_prompt = (
            "你是一个智能语音助理，名叫小智。"
            "你能够理解用户的语音和文字输入，提供有帮助、准确、友好的回答。"
            "请用简洁清晰的语言回复，适合语音朗读。"
        )

    async def chat(self, messages: List[Dict[str, str]], model: str = None) -> str:
        """
        同步对话（非流式）
        :param messages: 消息历史 [{"role": "user/assistant/system", "content": "..."}]
        :param model: 可选的模型覆盖
        :return: 助手回复文本
        """
        model = model or self.model
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=full_messages,
                stream=False,
            )
            content = response.choices[0].message.content
            logger.info(f"LLM 回复: {content[:100]}...")
            return content
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise Exception(f"LLM 调用失败: {str(e)}")

    async def chat_stream(self, messages: List[Dict[str, str]],
                          model: str = None) -> AsyncGenerator[str, None]:
        """
        流式对话
        :param messages: 消息历史
        :param model: 可选的模型覆盖
        :yields: 文本片段
        """
        model = model or self.model
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=full_messages,
                stream=True,
            )

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"LLM 流式调用失败: {e}")
            raise Exception(f"LLM 调用失败: {str(e)}")

    async def generate_title(self, first_message: str) -> str:
        """
        根据第一条消息自动生成会话标题
        :param first_message: 用户的第一条消息
        :return: 会话标题（6-15字）
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "请根据用户的消息生成一个简短的对话标题，不超过15个字，不要加引号和标点。"
                    },
                    {"role": "user", "content": first_message}
                ],
                stream=False,
                max_tokens=30,
            )
            title = response.choices[0].message.content.strip().strip('"').strip("'")
            return title[:20]  # 限制长度
        except Exception:
            return first_message[:20] if len(first_message) > 20 else first_message


# 全局 LLM 服务实例
llm_service = LLMService()
