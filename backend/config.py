"""
配置管理模块 - 从环境变量读取所有配置，禁止硬编码
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ASR 配置
    ASR_MODEL: str = os.getenv("ASR_MODEL", "qwen3-asr-flash")
    ASR_API_KEY: str = os.getenv("ASR_API_KEY", "")
    ASR_BASE_URL: str = os.getenv("ASR_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # TTS 配置
    TTS_MODEL: str = os.getenv("TTS_MODEL", "qwen3-tts-instruct-flash")
    TTS_API_KEY: str = os.getenv("TTS_API_KEY", "")
    TTS_BASE_URL: str = os.getenv("TTS_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
    TTS_REALTIME_MODEL: str = os.getenv("TTS_REALTIME_MODEL", "qwen3-tts-flash-realtime")
    TTS_REALTIME_URL: str = os.getenv("TTS_REALTIME_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime")

    # LLM 配置
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3.5-plus")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # JWT 配置
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))

    # 服务端配置
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

    # 数据库路径
    DATABASE_URL: str = os.getenv("DATABASE_URL", "voice_assistant.db")

    # TTS 默认设置
    TTS_DEFAULT_VOICE: str = os.getenv("TTS_DEFAULT_VOICE", "Cherry")
    TTS_DEFAULT_SPEED: float = float(os.getenv("TTS_DEFAULT_SPEED", "1.0"))
    TTS_DEFAULT_PITCH: float = float(os.getenv("TTS_DEFAULT_PITCH", "1.0"))
    TTS_DEFAULT_VOLUME: int = int(os.getenv("TTS_DEFAULT_VOLUME", "50"))


settings = Settings()
