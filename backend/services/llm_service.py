"""
LLM 服务 - 多 provider 路由
- Qwen 通义千问（qwen3.5-plus 等）：通过 DashScope OpenAI 兼容接口
- DeepSeek（deepseek_v4_flash 等）：通过 https://api.deepseek.com 的 OpenAI 兼容接口
- GPT / Gemini 等外部模型：通过 gpt.ge 网关的 OpenAI 兼容接口
根据 model 名称自动选择底层 HTTP 客户端，外部接口保持一致。
"""
import re
import logging
from typing import List, Dict, AsyncGenerator, Optional
from openai import OpenAI
from config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """大语言模型服务（支持 Qwen / DeepSeek / GPT / Gemini 多 provider 路由）"""

    def __init__(self):
        # 默认客户端：通义千问
        self._qwen_client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        # DeepSeek 客户端（仅当 API key 存在时可用）
        self._deepseek_client: Optional[OpenAI] = None
        if settings.DEEPSEEK_API_KEY:
            self._deepseek_client = OpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
            )
        # gpt.ge 客户端（用于 GPT / Gemini）
        self._gptge_client: Optional[OpenAI] = None
        if settings.GPTGE_API_KEY:
            self._gptge_client = OpenAI(
                api_key=settings.GPTGE_API_KEY,
                base_url=settings.GPTGE_BASE_URL,
                timeout=300.0,
            )

        self.default_model = settings.LLM_MODEL
        self.system_prompt = (
            "你是一个智能语音助理，名叫小智。"
            "你能够理解用户的语音和文字输入，提供有帮助、准确、友好的回答。"
            "请用简洁清晰的语言回复，适合语音朗读。"
        )

    # -------- provider 路由 --------

    def _resolve(self, model: Optional[str]) -> tuple:
        """
        根据模型名决定使用哪个客户端及实际调用时的模型 ID。
        :return: (client, real_model_id)
        """
        m = (model or self.default_model or "").strip()
        lower = m.lower()

        # DeepSeek 家族
        if lower.startswith("deepseek"):
            if not self._deepseek_client:
                logger.warning(f"DeepSeek API Key 未配置，回退到 Qwen: {m}")
                return self._qwen_client, self.default_model
            # 将自定义别名 deepseek_v4_flash 映射为 DeepSeek 官方模型 ID
            # 若平台已支持原名则直接透传
            real = {
                "deepseek_v4_flash": "deepseek-chat",
                "deepseek-v4-flash": "deepseek-chat",
                "deepseek_v4": "deepseek-chat",
            }.get(lower, m)
            return self._deepseek_client, real

        # GPT / Gemini 通过 gpt.ge 网关
        if lower.startswith("gpt") or lower.startswith("gemini") or lower.startswith("claude"):
            if not self._gptge_client:
                logger.warning(f"gpt.ge API Key 未配置，回退到 Qwen: {m}")
                return self._qwen_client, self.default_model
            return self._gptge_client, m

        # 默认 Qwen
        return self._qwen_client, m

    # -------- 对外接口 --------

    async def chat(self, messages: List[Dict[str, str]], model: str = None) -> str:
        """
        同步对话（非流式）
        :param messages: 消息历史 [{"role": "user/assistant/system", "content": "..."}]
        :param model: 可选的模型覆盖
        :return: 助手回复文本
        """
        client, real_model = self._resolve(model)
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages

        try:
            response = client.chat.completions.create(
                model=real_model,
                messages=full_messages,
                stream=False,
            )
            content = response.choices[0].message.content
            logger.info(f"LLM 回复 [{real_model}]: {content[:100]}...")
            return content
        except Exception as e:
            logger.error(f"LLM 调用失败 [{real_model}]: {e}")
            raise Exception(f"LLM 调用失败: {str(e)}")

    async def chat_stream(self, messages: List[Dict[str, str]],
                          model: str = None) -> AsyncGenerator[str, None]:
        """
        流式对话
        :param messages: 消息历史
        :param model: 可选的模型覆盖
        :yields: 文本片段
        """
        client, real_model = self._resolve(model)
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages

        try:
            response = client.chat.completions.create(
                model=real_model,
                messages=full_messages,
                stream=True,
            )

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"LLM 流式调用失败 [{real_model}]: {e}")
            raise Exception(f"LLM 调用失败: {str(e)}")

    async def summarize_for_speech(self, text: str, style: str = "summary") -> str:
        """
        将任意文本转换为适合 TTS 朗读的文本。
        :param text: 原始文本（可能来自网页/APP 屏幕，含噪声）
        :param style: 'read' 仅清洗原文；'summary' LLM 口语化总结
        :return: 可直接朗读的纯文本
        """
        if not text or not text.strip():
            return ""

        # 清洗：去除多余空白、不可见字符、样式符号
        cleaned = re.sub(r"[\t\r\f\v]+", " ", text)
        cleaned = re.sub(r" {2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[•●◆■□▪▫★☆►▶◀◄◇○]", "", cleaned)
        cleaned = cleaned.strip()

        if style == "read":
            return cleaned[:2000]

        # 总结朗读：调默认 LLM（Qwen）
        max_input = 4000
        input_text = cleaned[:max_input]
        try:
            response = self._qwen_client.chat.completions.create(
                model=self.default_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是面向视障用户的无障碍朗读助手。"
                            "请将用户提供的屏幕或网页文本，转换为适合语音朗读的简洁总结。"
                            "要求：\n"
                            "1. 200 字以内；\n"
                            "2. 口语化自然流畅，避免列表符号和样式描述；\n"
                            "3. 保留关键信息（标题、核心观点、数据），去除导航/广告/无意义片段；\n"
                            "4. 不要加'以下是总结：'等冗余前缀，直接输出正文。"
                        )
                    },
                    {"role": "user", "content": input_text}
                ],
                stream=False,
                max_tokens=400,
            )
            summary = response.choices[0].message.content.strip()
            logger.info(f"朗读总结生成成功: {summary[:60]}...")
            return summary
        except Exception as e:
            logger.error(f"朗读总结失败，回退原文: {e}")
            return cleaned[:500]

    async def generate_title(self, first_message: str) -> str:
        """
        根据第一条消息自动生成会话标题
        :param first_message: 用户的第一条消息
        :return: 会话标题（6-15字）
        """
        try:
            response = self._qwen_client.chat.completions.create(
                model=self.default_model,
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
            return title[:20]
        except Exception:
            return first_message[:20] if len(first_message) > 20 else first_message


# 全局 LLM 服务实例
llm_service = LLMService()
