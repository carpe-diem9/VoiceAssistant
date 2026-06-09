"""
设置路由 - TTS/ASR 设置、模型管理（LLM/ASR/TTS 三类）
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
    """获取 LLM/ASR/TTS 三类模型的当前选择 + 可用列表"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT llm_model, asr_model, tts_model FROM user_settings WHERE user_id = ?",
            (current_user["id"],)
        )
        row = await cursor.fetchone()
        cur_llm = (row[0] if row and row[0] else settings.LLM_MODEL)
        cur_asr = (row[1] if row and row[1] else settings.ASR_MODEL)
        cur_tts = (row[2] if row and row[2] else settings.TTS_MODEL)

        return AvailableModelsResponse(
            current_model=cur_llm,
            available_models=settings.AVAILABLE_LLM_MODELS,
            llm={"current": cur_llm, "available": settings.AVAILABLE_LLM_MODELS},
            asr={"current": cur_asr, "available": settings.AVAILABLE_ASR_MODELS},
            tts={"current": cur_tts, "available": settings.AVAILABLE_TTS_MODELS},
        )
    finally:
        await db.close()


async def _ensure_settings_row(db, user_id: int):
    cursor = await db.execute(
        "SELECT user_id FROM user_settings WHERE user_id = ?", (user_id,)
    )
    if not await cursor.fetchone():
        await db.execute(
            "INSERT INTO user_settings (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()


@router.put("/models")
async def update_model(data: ModelSettings, current_user: dict = Depends(get_current_user)):
    """切换模型 - 支持 llm_model / asr_model / tts_model 任意组合"""
    db = await get_db()
    try:
        await _ensure_settings_row(db, current_user["id"])
        sets = []
        params = []
        if data.llm_model:
            sets.append("llm_model = ?")
            params.append(data.llm_model)
        if data.asr_model:
            sets.append("asr_model = ?")
            params.append(data.asr_model)
        if data.tts_model:
            sets.append("tts_model = ?")
            params.append(data.tts_model)
        if not sets:
            return {"message": "无需更新", "current": {}}
        params.append(current_user["id"])
        await db.execute(
            f"UPDATE user_settings SET {', '.join(sets)} WHERE user_id = ?", tuple(params)
        )
        await db.commit()
        return {
            "message": "模型已切换",
            "current": {
                "llm_model": data.llm_model,
                "asr_model": data.asr_model,
                "tts_model": data.tts_model,
            },
            # 兼容旧前端
            "current_model": data.llm_model or "",
        }
    finally:
        await db.close()
