"""
无障碍朗读路由 - 任意文本 → LLM 清洗/总结 → TTS 合成音频
供 Android 悬浮球和 Chrome 扩展 content script 调用
"""
import base64
import logging
from fastapi import APIRouter, Depends, HTTPException

from models import ReadTextRequest, ReadTextResponse
from auth import get_current_user
from database import get_db
from services.llm_service import llm_service
from services.tts_service import tts_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/accessibility", tags=["无障碍朗读"])


async def _get_user_tts_settings(db, user_id: int) -> dict:
    """复用 chat_router 中的逻辑，查用户 TTS 设置（含模型选择）"""
    cursor = await db.execute(
        "SELECT tts_voice, tts_speed, tts_pitch, tts_volume, tts_model FROM user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if row:
        return {
            "voice": row[0], "speed": row[1], "pitch": row[2], "volume": row[3],
            "model": row[4],
        }
    return {"voice": "Cherry", "speed": 1.0, "pitch": 1.0, "volume": 50, "model": None}


@router.post("/read-text", response_model=ReadTextResponse)
async def read_text(data: ReadTextRequest, current_user: dict = Depends(get_current_user)):
    """
    将任意文本处理后朗读：
    - style='read'：清洗原文后直接合成
    - style='summary'：LLM 生成口语化总结后合成
    """
    style = data.style if data.style in ("read", "summary") else "summary"

    # 1. 文本处理
    try:
        processed_text = await llm_service.summarize_for_speech(data.text, style=style)
    except Exception as e:
        logger.error(f"文本处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"文本处理失败: {str(e)}")

    if not processed_text:
        raise HTTPException(status_code=400, detail="处理后文本为空，无法朗读")

    # 2. 可选 TTS 合成
    audio_base64 = None
    audio_format = "wav"
    if data.enable_tts:
        db = await get_db()
        try:
            tts_cfg = await _get_user_tts_settings(db, current_user["id"])
        finally:
            await db.close()
        try:
            result = await tts_service.synthesize(
                processed_text,
                voice=tts_cfg["voice"],
                speed=tts_cfg["speed"],
                pitch=tts_cfg["pitch"],
                volume=tts_cfg["volume"],
                model=tts_cfg.get("model"),
            )
            audio_data = result.get("audio_data")
            if audio_data:
                audio_base64 = base64.b64encode(audio_data).decode("ascii")
            audio_format = result.get("format", "wav")
        except Exception as e:
            # TTS 失败不阻断文本返回
            logger.error(f"TTS 合成失败: {e}")

    return ReadTextResponse(
        text=processed_text,
        audio_base64=audio_base64,
        audio_format=audio_format if data.enable_tts else "wav",
    )
