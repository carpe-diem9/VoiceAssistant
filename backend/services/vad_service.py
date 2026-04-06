"""
VAD 服务 - 基于能量检测的语音活动检测
使用简单的能量阈值和过零率方法，避免对 webrtcvad C 扩展的依赖
"""
import numpy as np
import struct
from typing import List, Tuple


class VADService:
    """语音活动检测服务"""

    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 30,
                 energy_threshold: float = 0.01, min_speech_duration_ms: int = 250,
                 min_silence_duration_ms: int = 300):
        """
        初始化 VAD 服务
        :param sample_rate: 采样率
        :param frame_duration_ms: 每帧时长（毫秒）
        :param energy_threshold: 能量阈值（相对于最大能量的比例）
        :param min_speech_duration_ms: 最短语音段时长（毫秒）
        :param min_silence_duration_ms: 最短静音段时长（毫秒）
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.energy_threshold = energy_threshold
        self.min_speech_frames = int(min_speech_duration_ms / frame_duration_ms)
        self.min_silence_frames = int(min_silence_duration_ms / frame_duration_ms)

    def _pcm_to_numpy(self, pcm_data: bytes) -> np.ndarray:
        """将 PCM 16bit 数据转换为 numpy 数组"""
        num_samples = len(pcm_data) // 2
        samples = struct.unpack(f'<{num_samples}h', pcm_data[:num_samples * 2])
        return np.array(samples, dtype=np.float32) / 32768.0

    def _compute_frame_energy(self, frame: np.ndarray) -> float:
        """计算帧能量（均方根）"""
        return float(np.sqrt(np.mean(frame ** 2)))

    def _compute_zero_crossing_rate(self, frame: np.ndarray) -> float:
        """计算过零率"""
        signs = np.sign(frame)
        crossings = np.sum(np.abs(np.diff(signs)) > 0)
        return float(crossings / len(frame))

    def detect_speech_frames(self, pcm_data: bytes) -> List[bool]:
        """
        检测每帧是否为语音帧
        :param pcm_data: PCM 16bit 单声道音频数据
        :return: 每帧的语音标记列表
        """
        samples = self._pcm_to_numpy(pcm_data)
        num_frames = len(samples) // self.frame_size
        if num_frames == 0:
            return []

        # 计算每帧能量
        energies = []
        for i in range(num_frames):
            frame = samples[i * self.frame_size: (i + 1) * self.frame_size]
            energies.append(self._compute_frame_energy(frame))

        # 动态阈值：使用中位数能量的倍数作为阈值
        max_energy = max(energies) if energies else 0
        if max_energy < 1e-6:
            return [False] * num_frames

        threshold = max(self.energy_threshold, np.median(energies) * 2)

        # 标记每帧是否为语音
        speech_flags = [e > threshold for e in energies]

        # 平滑处理：应用最短语音段和最短静音段约束
        speech_flags = self._smooth_flags(speech_flags)

        return speech_flags

    def _smooth_flags(self, flags: List[bool]) -> List[bool]:
        """平滑语音帧标记，去除过短的语音段和静音段"""
        if not flags:
            return flags

        result = flags.copy()

        # 去除过短的语音段
        i = 0
        while i < len(result):
            if result[i]:
                start = i
                while i < len(result) and result[i]:
                    i += 1
                if (i - start) < self.min_speech_frames:
                    for j in range(start, i):
                        result[j] = False
            else:
                i += 1

        # 去除过短的静音段（合并相邻语音段）
        i = 0
        while i < len(result):
            if not result[i]:
                start = i
                while i < len(result) and not result[i]:
                    i += 1
                if (i - start) < self.min_silence_frames and start > 0 and i < len(result):
                    for j in range(start, i):
                        result[j] = True
            else:
                i += 1

        return result

    def extract_speech_segments(self, pcm_data: bytes) -> bytes:
        """
        从音频中提取有效语音段，移除静音部分
        :param pcm_data: PCM 16bit 单声道音频数据
        :return: 提取后的 PCM 数据
        """
        speech_flags = self.detect_speech_frames(pcm_data)
        if not speech_flags:
            return pcm_data  # 如果没有检测到帧，返回原数据

        frame_bytes = self.frame_size * 2  # 16bit = 2 bytes per sample
        output = bytearray()

        for i, is_speech in enumerate(speech_flags):
            if is_speech:
                start = i * frame_bytes
                end = start + frame_bytes
                output.extend(pcm_data[start:end])

        return bytes(output) if output else pcm_data

    def has_speech(self, pcm_data: bytes) -> bool:
        """
        检测音频中是否包含语音
        :param pcm_data: PCM 16bit 单声道音频数据
        :return: 是否包含语音
        """
        speech_flags = self.detect_speech_frames(pcm_data)
        speech_count = sum(speech_flags)
        return speech_count >= self.min_speech_frames


# 全局 VAD 服务实例
vad_service = VADService()
