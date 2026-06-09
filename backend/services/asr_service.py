"""
ASR 服务 - 多 provider 路由
- DashScope (qwen3-asr-flash 等)：通过 OpenAI chat.completions + input_audio
- gpt.ge 网关 (whisper-large-v3 / SenseVoiceSmall 等)：通过 OpenAI 标准 audio.transcriptions
根据 model 名称自动路由。
"""
import io
import re
import json
import base64
import logging
from typing import Optional
from openai import OpenAI
from config import settings
from services.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)

# 匹配字面量形式的 \uXXXX 转义（某些网关返回中文时会错将其编码为字面量）
_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _decode_unicode_escapes(text: str) -> str:
    """
    将形如 '\\u4f60\\u597d' 的字面量转义还原为真实 Unicode 字符。
    对于 SenseVoiceSmall 等通过 gpt.ge 网关返回的结果有时是
    字面量编码形式而非 UTF-8 中文（如 "\\ueca\\u5929"）。
    纯中文 / 英文文本不受影响，只替换包含 \\u 的片段。
    """
    if not text or "\\u" not in text:
        return text
    try:
        return _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
    except Exception:
        return text



class ASRService:
    """语音识别服务（DashScope / gpt.ge 多 provider）"""

    def __init__(self):
        # DashScope 客户端（默认）
        self._dashscope_client = OpenAI(
            api_key=settings.ASR_API_KEY,
            base_url=settings.ASR_BASE_URL,
        )
        # gpt.ge 客户端（whisper / SenseVoice 等）
        self._gptge_client: Optional[OpenAI] = None
        if settings.GPTGE_API_KEY:
            self._gptge_client = OpenAI(
                api_key=settings.GPTGE_API_KEY,
                base_url=settings.GPTGE_BASE_URL,
                timeout=120.0,
            )
        self.default_model = settings.ASR_MODEL

    # -------- provider 路由 --------

    def _is_gptge_model(self, model: str) -> bool:
        lower = (model or "").lower()
        # whisper-* / sensevoice* / paraformer* 等通过 gpt.ge OpenAI 兼容音频接口
        return (
            lower.startswith("whisper")
            or "sensevoice" in lower
            or lower.startswith("openai/")
        )

    # -------- 对外接口 --------

    async def recognize(self, audio_data: bytes, is_wav: bool = True,
                        language: str = "auto", model: Optional[str] = None) -> str:
        """
        将音频数据转换为文本
        :param audio_data: 音频字节流（WAV 或 PCM）
        :param is_wav: 是否为 WAV 格式
        :param language: 语言代码
        :param model: 模型名（None 则用默认）
        """
        m = (model or self.default_model or "").strip() or self.default_model
        try:
            # 音频预处理 -> WAV
            pcm_data, sample_rate = AudioProcessor.process_audio(audio_data, is_wav)
            wav_data = AudioProcessor.pcm_to_wav(pcm_data, sample_rate)

            if self._is_gptge_model(m):
                if not self._gptge_client:
                    logger.warning(f"gpt.ge ASR 不可用，回退默认 dashscope ASR ({self.default_model})")
                    return await self._dashscope_recognize(wav_data, self.default_model, language)
                return await self._gptge_recognize(wav_data, m, language)
            else:
                return await self._dashscope_recognize(wav_data, m, language)
        except Exception as e:
            logger.error(f"ASR 识别失败 [{m}]: {e}")
            raise Exception(f"语音识别失败: {str(e)}")

    # -------- DashScope --------

    async def _dashscope_recognize(self, wav_data: bytes, model: str, language: str) -> str:
        base64_str = base64.b64encode(wav_data).decode()
        data_uri = f"data:audio/wav;base64,{base64_str}"

        completion = self._dashscope_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}],
                    "role": "user",
                }
            ],
            stream=False,
            extra_body={
                "asr_options": {
                    "language": language if language != "auto" else None,
                    "enable_itn": True,
                }
            },
        )
        text = completion.choices[0].message.content or ""
        logger.info(f"ASR [{model}] 识别结果: {text[:100]}")
        return text.strip()

    # -------- gpt.ge OpenAI 标准 audio/transcriptions --------

    async def _gptge_recognize(self, wav_data: bytes, model: str, language: str) -> str:
        # OpenAI SDK 要求传文件对象（带 .name）
        bio = io.BytesIO(wav_data)
        bio.name = "audio.wav"
        kwargs = {"model": model, "file": bio, "response_format": "text"}
        if language and language != "auto":
            kwargs["language"] = language

        result = self._gptge_client.audio.transcriptions.create(**kwargs)
        # response_format=text 时返回纯字符串；object 时取 .text
        if isinstance(result, str):
            text = result
        else:
            text = getattr(result, "text", "") or ""
        text = text.strip()

        # 部分网关（如 gpt.ge 对 SenseVoiceSmall）在 text 模式下依然返回 JSON 字符串
        # 形如 '{"text":"你好"}' 或 '{\\"text\\":...}'，先尝试 JSON 解析
        if text.startswith("{") and "text" in text:
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    text = str(obj.get("text") or obj.get("result") or "").strip()
            except Exception:
                # 不是合法 JSON，回退到正则抽取
                m = re.search(r'"text"\s*:\s*"([^"]*)"', text)
                if m:
                    text = m.group(1).strip()

        # SenseVoice 等模型会返回字面量 \\uXXXX 转义形式，需解码为中文
        decoded = _decode_unicode_escapes(text)
        # 去除 SenseVoice 可能携带的任务标签，如 <|zh|><|NEUTRAL|><|Speech|><|withitn|>
        decoded = re.sub(r"<\|[^|>]*\|>", "", decoded).strip()
        logger.info(f"ASR [{model}] 识别结果: {decoded[:100]}")
        return decoded


# 全局 ASR 服务实例
asr_service = ASRService()
