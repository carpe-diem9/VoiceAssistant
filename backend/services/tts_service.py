"""
TTS 服务 - 使用 Qwen TTS (qwen3-tts-flash) 进行语音合成
DashScope MultiModalConversation API 返回音频 URL 或 base64 data
"""
import os
import re
import struct
import base64
import logging
import asyncio
import dashscope
import requests as http_requests
from config import settings

logger = logging.getLogger(__name__)

# 设置 DashScope API URL
dashscope.base_http_api_url = settings.TTS_BASE_URL

# 单次 TTS 合成最大字符数（超过此值会分段合成）
MAX_CHUNK_CHARS = 200


class TTSService:
    """语音合成服务"""

    # qwen3-tts-flash 已确认有效的音色列表
    VALID_VOICES = [
        "Cherry", "Serena", "Ethan", "Chelsie", "Bella",
    ]

    def __init__(self):
        self.model = settings.TTS_MODEL
        self.api_key = settings.TTS_API_KEY
        self.default_voice = settings.TTS_DEFAULT_VOICE
        self.default_speed = settings.TTS_DEFAULT_SPEED
        self.default_pitch = settings.TTS_DEFAULT_PITCH
        self.default_volume = settings.TTS_DEFAULT_VOLUME

    def _validate_voice(self, voice: str) -> str:
        """验证音色名称有效性，无效则回退到默认值"""
        if voice and voice in self.VALID_VOICES:
            return voice
        logger.warning(f"Invalid voice '{voice}', falling back to '{self.default_voice}'")
        return self.default_voice

    def _build_instructions(self, speed: float = None, pitch: float = None,
                            volume: int = None) -> str | None:
        """
        将 speed/pitch/volume 数值转换为 qwen3-tts-instruct-flash 的自然语言 instructions。
        speed: 0.5~2.0 (1.0=正常), pitch: 0.5~2.0 (1.0=正常), volume: 0~100 (50=正常)
        如果所有参数都是默认值，返回 None（不传 instructions 以节省开销）。
        """
        speed = speed or self.default_speed
        pitch = pitch or self.default_pitch
        volume = volume if volume is not None else self.default_volume

        parts = []

        # 语速
        if speed <= 0.6:
            parts.append("语速很慢")
        elif speed <= 0.8:
            parts.append("语速较慢")
        elif speed >= 1.8:
            parts.append("语速很快")
        elif speed >= 1.3:
            parts.append("语速较快")

        # 音调
        if pitch <= 0.6:
            parts.append("音调很低沉")
        elif pitch <= 0.8:
            parts.append("音调偏低")
        elif pitch >= 1.8:
            parts.append("音调很高")
        elif pitch >= 1.3:
            parts.append("音调偏高")

        # 音量
        if volume <= 15:
            parts.append("音量很小，像是在轻声耳语")
        elif volume <= 30:
            parts.append("音量较小")
        elif volume >= 85:
            parts.append("音量很大，像是在大声喊话")
        elif volume >= 70:
            parts.append("音量较大")

        if not parts:
            return None

        instructions = "，".join(parts) + "。"
        logger.info(f"TTS instructions: {instructions} (speed={speed}, pitch={pitch}, volume={volume})")
        return instructions

    @staticmethod
    def _split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
        """
        将长文本按句子边界分段，每段不超过 max_chars 字符。
        优先在句号、问号、感叹号、分号、换行处切分。
        """
        if len(text) <= max_chars:
            return [text]

        # 按中英文标点和换行切分为句子
        sentences = re.split(r'(?<=[。！？；\n.!?;])', text)
        sentences = [s for s in sentences if s.strip()]

        chunks = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) <= max_chars:
                current += sent
            else:
                if current:
                    chunks.append(current)
                # 如果单个句子就超过 max_chars，强制按长度切
                while len(sent) > max_chars:
                    chunks.append(sent[:max_chars])
                    sent = sent[max_chars:]
                current = sent
        if current:
            chunks.append(current)

        return chunks

    @staticmethod
    def _concat_wav(wav_datas: list[bytes]) -> bytes:
        """
        拼接多段 WAV 音频数据（假设格式相同：PCM 16bit, 24000Hz, mono）。
        保留第一段的头部，拼接所有 PCM 数据，更新文件大小字段。
        """
        if len(wav_datas) == 1:
            return wav_datas[0]

        pcm_chunks = []
        header = None
        for i, wav in enumerate(wav_datas):
            if len(wav) < 44:
                continue
            if i == 0:
                header = bytearray(wav[:44])
            # 跳过 44 字节 WAV 头
            pcm_chunks.append(wav[44:])

        if not header or not pcm_chunks:
            return wav_datas[0] if wav_datas else b""

        all_pcm = b"".join(pcm_chunks)
        data_size = len(all_pcm)
        file_size = data_size + 36  # 44 - 8

        # 更新 RIFF chunk size (offset 4, little-endian uint32)
        struct.pack_into('<I', header, 4, file_size)
        # 更新 data sub-chunk size (offset 40, little-endian uint32)
        struct.pack_into('<I', header, 40, data_size)

        return bytes(header) + all_pcm

    def _extract_audio(self, response) -> dict:
        """从 TTS 响应中提取音频数据"""
        if not hasattr(response, 'output') or not response.output:
            return {"audio_data": b"", "format": "wav", "sample_rate": 24000}

        output = response.output

        # 方式1: output.audio 结构 (qwen3-tts-flash 实际返回格式)
        audio_info = output.get("audio", {}) if isinstance(output, dict) else None
        if audio_info:
            # 优先使用 base64 data
            audio_data_str = audio_info.get("data", "")
            if audio_data_str:
                return {
                    "audio_data": base64.b64decode(audio_data_str),
                    "format": "wav", "sample_rate": 24000
                }
            # 其次从 URL 下载
            audio_url = audio_info.get("url", "")
            if audio_url:
                try:
                    r = http_requests.get(audio_url, timeout=30)
                    r.raise_for_status()
                    return {
                        "audio_data": r.content,
                        "format": "wav", "sample_rate": 24000
                    }
                except Exception as e:
                    logger.error(f"下载 TTS 音频失败: {e}")

        # 方式2: output.choices[].message.audio[] 结构
        choices = output.get("choices", []) if isinstance(output, dict) else []
        if choices:
            message = choices[0].get("message", {})
            audio_list = message.get("audio", [])
            if audio_list:
                audio_b64 = audio_list[0]
                return {
                    "audio_data": base64.b64decode(audio_b64),
                    "format": "wav", "sample_rate": 24000
                }

        logger.warning(f"TTS 响应格式无法解析: {response}")
        return {"audio_data": b"", "format": "wav", "sample_rate": 24000}

    async def synthesize(self, text: str, voice: str = None,
                         speed: float = None, pitch: float = None,
                         volume: int = None) -> dict:
        """
        将文本合成为语音。长文本自动分段合成并拼接 WAV。
        内置重试机制，每段最多重试 3 次。
        """
        voice = self._validate_voice(voice or self.default_voice)
        instructions = self._build_instructions(speed, pitch, volume)
        chunks = self._split_text(text.strip())
        logger.info(f"TTS synthesize: total_len={len(text)}, chunks={len(chunks)}, voice={voice}, instructions={instructions}")

        wav_parts = []
        for idx, chunk_text in enumerate(chunks):
            chunk_audio = await self._synthesize_chunk(chunk_text, voice, instructions, idx, len(chunks))
            if chunk_audio:
                wav_parts.append(chunk_audio)

        if not wav_parts:
            logger.error("TTS 所有分段均合成失败")
            raise Exception("语音合成失败: 所有分段均未返回音频")

        # 拼接所有 WAV 片段
        final_audio = self._concat_wav(wav_parts)
        logger.info(f"TTS 合成完成: {len(wav_parts)}/{len(chunks)} 段成功, total={len(final_audio)} bytes")
        return {"audio_data": final_audio, "format": "wav", "sample_rate": 24000}

    async def _synthesize_chunk(self, text: str, voice: str, instructions: str | None,
                                idx: int, total: int) -> bytes | None:
        """合成单段文本，带重试"""
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"TTS chunk {idx+1}/{total} attempt {attempt+1}/{max_retries}, len={len(text)}")
                loop = asyncio.get_event_loop()

                # 构建 API 调用参数
                call_kwargs = dict(
                    model=self.model,
                    api_key=self.api_key,
                    text=text,
                    voice=voice,
                )
                if instructions:
                    call_kwargs["instructions"] = instructions
                    call_kwargs["optimize_instructions"] = True

                response = await loop.run_in_executor(
                    None, lambda: dashscope.MultiModalConversation.call(**call_kwargs)
                )

                if response.status_code == 200:
                    result = self._extract_audio(response)
                    if result["audio_data"]:
                        logger.info(f"TTS chunk {idx+1}/{total} OK: {len(result['audio_data'])} bytes")
                        return result["audio_data"]
                    else:
                        logger.warning(f"TTS chunk {idx+1}/{total} 返回空音频 (attempt {attempt+1})")
                        last_error = "empty audio"
                else:
                    last_error = f"status={response.status_code}, msg={response.message}"
                    logger.warning(f"TTS chunk {idx+1}/{total} 失败 (attempt {attempt+1}): {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"TTS chunk {idx+1}/{total} 异常 (attempt {attempt+1}): {e}")

            if attempt < max_retries - 1:
                await asyncio.sleep((attempt + 1) * 0.5)

        logger.error(f"TTS chunk {idx+1}/{total} 最终失败: {last_error}")
        return None

    async def synthesize_streaming(self, text: str, voice: str = None,
                                   speed: float = None, pitch: float = None,
                                   volume: int = None):
        """
        流式语音合成 - 使用 DashScope HTTP 流式接口
        :yields: 音频数据块 (bytes)
        """
        voice = self._validate_voice(voice or self.default_voice)
        try:
            response = dashscope.MultiModalConversation.call(
                model=self.model,
                api_key=self.api_key,
                text=text,
                voice=voice,
                stream=True,
            )

            for chunk in response:
                if chunk.status_code == 200:
                    result = self._extract_audio(chunk)
                    if result["audio_data"]:
                        yield result["audio_data"]

        except Exception as e:
            logger.error(f"TTS 流式合成异常: {e}")
            raise Exception(f"语音合成失败: {str(e)}")

    def get_available_voices(self) -> list:
        """获取可用的音色列表"""
        return list(self.VALID_VOICES)


# 全局 TTS 服务实例
tts_service = TTSService()
