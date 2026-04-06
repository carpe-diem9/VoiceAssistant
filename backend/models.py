"""
Pydantic 数据模型 - 请求和响应的数据结构定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ===== 用户认证相关模型 =====

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ===== 会话相关模型 =====

class SessionCreate(BaseModel):
    title: Optional[str] = "新对话"


class SessionUpdate(BaseModel):
    title: str


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    audio_url: Optional[str] = None
    created_at: str


class SessionResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: str
    updated_at: str


class SessionDetailResponse(SessionResponse):
    messages: List[MessageResponse] = []


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]


# ===== 对话相关模型 =====

class TextChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1, description="用户消息")
    enable_tts: bool = Field(False, description="是否对回复进行语音合成")


class DeepResearchRequest(BaseModel):
    session_id: Optional[int] = None
    question: str = Field(..., min_length=1, description="研究问题")


# ===== TTS/ASR 设置模型 =====

class TTSSettings(BaseModel):
    voice: Optional[str] = "Cherry"
    speed: Optional[float] = Field(1.0, ge=0.5, le=2.0, description="语速 0.5-2.0")
    pitch: Optional[float] = Field(1.0, ge=0.5, le=2.0, description="音调 0.5-2.0")
    volume: Optional[int] = Field(50, ge=0, le=100, description="音量 0-100")


class TTSSettingsResponse(TTSSettings):
    available_voices: List[str] = [
        "Cherry", "Serena", "Ethan", "Chelsie", "Bella",
    ]


class ModelSettings(BaseModel):
    llm_model: Optional[str] = "qwen3.5-plus"


class AvailableModelsResponse(BaseModel):
    current_model: str
    available_models: List[str] = ["qwen3.5-plus"]
