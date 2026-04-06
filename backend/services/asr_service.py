"""
ASR 服务 - 使用 Qwen ASR (qwen3-asr-flash) 进行语音识别
通过 OpenAI 兼容接口调用，支持 base64 音频输入
"""
import base64
import logging
from openai import OpenAI
from config import settings
from services.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)


class ASRService:
    """语音识别服务"""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.ASR_API_KEY,
            base_url=settings.ASR_BASE_URL,
        )
        self.model = settings.ASR_MODEL

    async def recognize(self, audio_data: bytes, is_wav: bool = True, language: str = "auto") -> str:
        """
        将音频数据转换为文本
        :param audio_data: 音频数据（WAV 或 PCM 格式）
        :param is_wav: 是否为 WAV 格式
        :param language: 语言代码，默认自动检测
        :return: 识别出的文本
        """
        try:
            # 音频预处理
            pcm_data, sample_rate = AudioProcessor.process_audio(audio_data, is_wav)

            # 将处理后的 PCM 转为 WAV 格式用于 base64 编码
            wav_data = AudioProcessor.pcm_to_wav(pcm_data, sample_rate)

            # Base64 编码
            base64_str = base64.b64encode(wav_data).decode()
            data_uri = f"data:audio/wav;base64,{base64_str}"

            # 调用 Qwen ASR API（使用 OpenAI 兼容接口）
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": data_uri
                                }
                            }
                        ],
                        "role": "user"
                    }
                ],
                stream=False,
                extra_body={
                    "asr_options": {
                        "language": language if language != "auto" else None,
                        "enable_itn": True  # 启用反标准化（数字、日期等格式化）
                    }
                }
            )

            text = completion.choices[0].message.content
            logger.info(f"ASR 识别结果: {text[:100]}...")
            return text.strip()

        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            raise Exception(f"语音识别失败: {str(e)}")


# 全局 ASR 服务实例
asr_service = ASRService()
