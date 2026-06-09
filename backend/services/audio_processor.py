"""
音频预处理模块 - 噪声过滤、音量归一化、格式转换
"""
import io
import wave
import struct
import numpy as np
from scipy import signal
from typing import Tuple
from services.vad_service import vad_service


class AudioProcessor:
    """音频预处理器"""

    @staticmethod
    def wav_to_pcm(wav_data: bytes) -> Tuple[bytes, int, int]:
        """
        将 WAV 格式转换为原始 PCM 数据
        :return: (pcm_data, sample_rate, channels)
        """
        with io.BytesIO(wav_data) as wav_io:
            with wave.open(wav_io, 'rb') as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                pcm_data = wf.readframes(wf.getnframes())
                sample_width = wf.getsampwidth()

        # 如果是立体声，转为单声道
        if channels == 2:
            pcm_data = AudioProcessor._stereo_to_mono(pcm_data, sample_width)
            channels = 1

        # 如果采样率不是 16000，重采样
        if sample_rate != 16000:
            pcm_data = AudioProcessor._resample(pcm_data, sample_rate, 16000)
            sample_rate = 16000

        return pcm_data, sample_rate, channels

    @staticmethod
    def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1,
                   sample_width: int = 2) -> bytes:
        """将 PCM 数据转换为 WAV 格式"""
        with io.BytesIO() as wav_io:
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_data)
            return wav_io.getvalue()

    @staticmethod
    def _stereo_to_mono(pcm_data: bytes, sample_width: int = 2) -> bytes:
        """立体声转单声道"""
        num_samples = len(pcm_data) // (sample_width * 2)
        if sample_width == 2:
            samples = struct.unpack(f'<{num_samples * 2}h', pcm_data[:num_samples * 2 * 2])
            mono = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)]
            return struct.pack(f'<{len(mono)}h', *mono)
        return pcm_data

    @staticmethod
    def _resample(pcm_data: bytes, orig_rate: int, target_rate: int) -> bytes:
        """重采样音频"""
        num_samples = len(pcm_data) // 2
        samples = np.array(struct.unpack(f'<{num_samples}h', pcm_data[:num_samples * 2]), dtype=np.float64)

        # 计算重采样比例
        num_target = int(len(samples) * target_rate / orig_rate)
        resampled = signal.resample(samples, num_target)

        # 截断到 int16 范围
        resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
        return resampled.tobytes()

    @staticmethod
    def normalize_volume(pcm_data: bytes, target_rms: float = 0.1) -> bytes:
        """
        音量归一化
        :param pcm_data: PCM 16bit 单声道数据
        :param target_rms: 目标 RMS 值（0-1）
        """
        num_samples = len(pcm_data) // 2
        if num_samples == 0:
            return pcm_data

        samples = np.array(
            struct.unpack(f'<{num_samples}h', pcm_data[:num_samples * 2]),
            dtype=np.float32
        ) / 32768.0

        current_rms = np.sqrt(np.mean(samples ** 2))
        if current_rms < 1e-6:
            return pcm_data

        gain = target_rms / current_rms
        # 限制增益防止过度放大
        gain = min(gain, 10.0)

        samples = samples * gain
        samples = np.clip(samples, -1.0, 1.0)

        int_samples = (samples * 32767).astype(np.int16)
        return int_samples.tobytes()

    @staticmethod
    def noise_filter(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
        """
        简单高通滤波降噪 - 去除低频环境噪声
        :param pcm_data: PCM 16bit 单声道数据
        :param sample_rate: 采样率
        """
        num_samples = len(pcm_data) // 2
        if num_samples < 10:
            return pcm_data

        samples = np.array(
            struct.unpack(f'<{num_samples}h', pcm_data[:num_samples * 2]),
            dtype=np.float64
        )

        # 高通滤波：去除 80Hz 以下的低频噪声
        nyquist = sample_rate / 2
        cutoff = 80 / nyquist
        if cutoff < 1.0:
            b, a = signal.butter(4, cutoff, btype='high')
            samples = signal.filtfilt(b, a, samples)

        samples = np.clip(samples, -32768, 32767).astype(np.int16)
        return samples.tobytes()

    @staticmethod
    def process_audio(audio_data: bytes, is_wav: bool = True) -> Tuple[bytes, int]:
        """
        完整音频预处理流水线：格式转换 -> 降噪 -> VAD -> 音量归一化
        :param audio_data: 原始音频数据（WAV 或 PCM）
        :param is_wav: 是否为 WAV 格式
        :return: (处理后的 PCM 数据, 采样率)
        """
        if is_wav:
            pcm_data, sample_rate, _ = AudioProcessor.wav_to_pcm(audio_data)
        else:
            pcm_data = audio_data
            sample_rate = 16000

        # 1. 噪声过滤
        pcm_data = AudioProcessor.noise_filter(pcm_data, sample_rate)

        # 2. VAD - 提取有效语音段
        pcm_data = vad_service.extract_speech_segments(pcm_data)

        # 3. 音量归一化
        pcm_data = AudioProcessor.normalize_volume(pcm_data)

        return pcm_data, sample_rate


# 全局实例
audio_processor = AudioProcessor()
