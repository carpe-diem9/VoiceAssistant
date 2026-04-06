"""
设置路由 - TTS/ASR 设置、模型管理
"""
from fastapi import APIRouter, Depends
from models import TTSSettings, TTSSettingsResponse, ModelSettings, AvailableModelsResponse
from auth import get_current_user
from database import get_db
from config import settings

router = APIRouter(prefix="/api/settings", tags=["设置"])


@router.get("/tts", response_model=TTSSettingsResponse)
async def get_tts_settings(current_user: dict = Depends(get_current_user)):
    """获取当前用户的 TTS 设置"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT tts_voice, tts_speed, tts_pitch, tts_volume FROM user_settings WHERE user_id = ?",
            (current_user["id"],)
        )
        row = await cursor.fetchone()
        if row:
            return TTSSettingsResponse(
                voice=row[0], speed=row[1], pitch=row[2], volume=row[3]
            )
        return TTSSettingsResponse()
    finally:
        await db.close()


@router.put("/tts", response_model=TTSSettingsResponse)
async def update_tts_settings(data: TTSSettings, current_user: dict = Depends(get_current_user)):
    """更新用户的 TTS 设置"""
    db = await get_db()
    try:
        # 先检查是否存在设置行
        cursor = await db.execute(
            "SELECT user_id FROM user_settings WHERE user_id = ?", (current_user["id"],)
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                """UPDATE user_settings 
                   SET tts_voice = ?, tts_speed = ?, tts_pitch = ?, tts_volume = ?
                   WHERE user_id = ?""",
                (data.voice, data.speed, data.pitch, data.volume, current_user["id"])
            )
        else:
            await db.execute(
                """INSERT INTO user_settings (user_id, tts_voice, tts_speed, tts_pitch, tts_volume)
                   VALUES (?, ?, ?, ?, ?)""",
                (current_user["id"], data.voice, data.speed, data.pitch, data.volume)
            )
        await db.commit()

        return TTSSettingsResponse(
            voice=data.voice, speed=data.speed, pitch=data.pitch, volume=data.volume
        )
    finally:
        await db.close()


@router.get("/models", response_model=AvailableModelsResponse)
async def get_models(current_user: dict = Depends(get_current_user)):
    """获取可用模型列表"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT llm_model FROM user_settings WHERE user_id = ?",
            (current_user["id"],)
        )
        row = await cursor.fetchone()
        current_model = row[0] if row else settings.LLM_MODEL

        return AvailableModelsResponse(
            current_model=current_model,
            available_models=["qwen3.5-plus"]
        )
    finally:
        await db.close()


@router.put("/models")
async def update_model(data: ModelSettings, current_user: dict = Depends(get_current_user)):
    """切换 LLM 模型"""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE user_settings SET llm_model = ? WHERE user_id = ?",
            (data.llm_model, current_user["id"])
        )
        await db.commit()
        return {"message": "模型已切换", "current_model": data.llm_model}
    finally:
        await db.close()
