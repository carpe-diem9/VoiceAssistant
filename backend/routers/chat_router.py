"""
对话路由 - 文本对话（SSE流式）、语音对话、WebSocket 完整交互、Deep Research
"""
import json
import base64
import re
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, Response
from typing import Optional
from models import TextChatRequest, DeepResearchRequest
from auth import get_current_user, decode_token
from database import get_db
from services.asr_service import asr_service
from services.tts_service import tts_service
from services.llm_service import llm_service
from services.deep_research import deep_research_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["对话"])


async def _get_or_create_session(db, user_id: int, session_id: Optional[int] = None) -> int:
    """获取或创建会话"""
    if session_id:
        cursor = await db.execute(
            "SELECT id FROM sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
        )
        if await cursor.fetchone():
            return session_id

    # 创建新会话
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor = await db.execute(
        "INSERT INTO sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, "新对话", now, now)
    )
    await db.commit()
    return cursor.lastrowid


async def _save_message(db, session_id: int, role: str, content: str, audio_url: str = None):
    """保存消息到数据库"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    await db.execute(
        "INSERT INTO messages (session_id, role, content, audio_url, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, audio_url, now)
    )
    await db.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
    )
    await db.commit()


async def _get_session_messages(db, session_id: int, limit: int = 20) -> list:
    """获取会话历史消息（用于 LLM 上下文）"""
    cursor = await db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit)
    )
    rows = await cursor.fetchall()
    # 反转顺序使其按时间正序
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


async def _get_user_tts_settings(db, user_id: int) -> dict:
    """获取用户 TTS 设置"""
    cursor = await db.execute(
        "SELECT tts_voice, tts_speed, tts_pitch, tts_volume FROM user_settings WHERE user_id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    if row:
        return {"voice": row[0], "speed": row[1], "pitch": row[2], "volume": row[3]}
    return {"voice": "Cherry", "speed": 1.0, "pitch": 1.0, "volume": 50}


@router.post("/text")
async def text_chat(data: TextChatRequest, current_user: dict = Depends(get_current_user)):
    """
    文本对话 - SSE 流式返回 LLM 回复
    返回格式: text/event-stream
    """
    db = await get_db()
    try:
        session_id = await _get_or_create_session(db, current_user["id"], data.session_id)

        # 保存用户消息
        await _save_message(db, session_id, "user", data.message)

        # 获取会话历史
        history = await _get_session_messages(db, session_id)

        # 如果是会话的第一条消息，自动生成标题
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        )
        msg_count = (await cursor.fetchone())[0]
        if msg_count <= 1:
            title = await llm_service.generate_title(data.message)
            await db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
            await db.commit()

        async def generate():
            full_response = ""
            # 发送 session_id
            yield f"data: {json.dumps({'type': 'session_id', 'session_id': session_id})}\n\n"

            try:
                async for chunk in llm_service.chat_stream(history):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"

                # 保存助手回复
                db2 = await get_db()
                try:
                    await _save_message(db2, session_id, "assistant", full_response)
                finally:
                    await db2.close()

                # 如果启用 TTS，合成语音并返回
                if data.enable_tts and full_response.strip():
                    try:
                        db3 = await get_db()
                        try:
                            tts_settings = await _get_user_tts_settings(db3, current_user["id"])
                        finally:
                            await db3.close()

                        logger.info(f"Text chat TTS: voice={tts_settings['voice']}, text_len={len(full_response)}")
                        tts_result = await tts_service.synthesize(
                            full_response,
                            voice=tts_settings["voice"],
                            speed=tts_settings["speed"],
                            pitch=tts_settings["pitch"],
                            volume=tts_settings["volume"],
                        )
                        if tts_result["audio_data"]:
                            audio_b64 = base64.b64encode(tts_result["audio_data"]).decode()
                            logger.info(f"Text chat TTS success: audio_b64_len={len(audio_b64)}")
                            yield f"data: {json.dumps({'type': 'audio', 'audio_base64': audio_b64, 'format': tts_result['format']})}\n\n"
                        else:
                            logger.warning("Text chat TTS returned empty audio data")
                    except Exception as tts_err:
                        logger.warning(f"Text chat TTS failed: {tts_err}")

                yield f"data: {json.dumps({'type': 'done', 'full_content': full_response})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    finally:
        await db.close()


@router.post("/wake-word")
async def check_wake_word(
    audio: UploadFile = File(...),
    wake_word: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    """
    唤醒词检测 - 接收短音频，ASR 识别后检查是否包含唤醒词
    返回 JSON: {detected: bool, text: str}
    """
    try:
        audio_data = await audio.read()
        is_wav = audio.filename.lower().endswith('.wav') if audio.filename else True
        text = await asr_service.recognize(audio_data, is_wav=is_wav)
        # 去掉空格和所有标点符号后匹配（ASR 可能插入逗号等标点，如"你好，助手"）
        text_clean = re.sub(r'[^\w]', '', text.strip().lower())
        wake_clean = re.sub(r'[^\w]', '', wake_word.strip().lower())
        detected = wake_clean in text_clean
        logger.info(f"WakeWord check: text='{text}', clean='{text_clean}', wake='{wake_clean}', detected={detected}")
        return {"detected": detected, "text": text.strip()}
    except Exception as e:
        logger.warning(f"WakeWord ASR failed: {e}")
        return {"detected": False, "text": ""}


@router.post("/voice")
async def voice_chat(
    audio: UploadFile = File(...),
    session_id: Optional[int] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    语音对话 - 接收音频文件，返回 ASR 文本 + LLM 回复 + TTS 音频
    返回 JSON: {asr_text, reply_text, audio_base64, session_id}
    """
    db = await get_db()
    try:
        session_id = await _get_or_create_session(db, current_user["id"], session_id)

        # 1. 读取音频文件
        audio_data = await audio.read()
        is_wav = audio.filename.lower().endswith('.wav') if audio.filename else True

        # 2. ASR 语音识别
        asr_text = await asr_service.recognize(audio_data, is_wav=is_wav)
        if not asr_text.strip():
            return {"asr_text": "", "reply_text": "未能识别到语音内容，请重新录制。",
                    "audio_base64": "", "session_id": session_id}

        # 保存用户语音消息
        await _save_message(db, session_id, "user", asr_text)

        # 如果是第一条消息，生成标题
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        )
        msg_count = (await cursor.fetchone())[0]
        if msg_count <= 1:
            title = await llm_service.generate_title(asr_text)
            await db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
            await db.commit()

        # 3. 获取历史消息并调用 LLM
        history = await _get_session_messages(db, session_id)
        reply_text = await llm_service.chat(history)

        # 保存助手回复
        await _save_message(db, session_id, "assistant", reply_text)

        # 4. TTS 语音合成
        tts_settings = await _get_user_tts_settings(db, current_user["id"])
        tts_result = await tts_service.synthesize(
            reply_text,
            voice=tts_settings["voice"],
            speed=tts_settings["speed"],
            pitch=tts_settings["pitch"],
            volume=tts_settings["volume"]
        )

        audio_b64 = base64.b64encode(tts_result["audio_data"]).decode() if tts_result["audio_data"] else ""

        return {
            "asr_text": asr_text,
            "reply_text": reply_text,
            "audio_base64": audio_b64,
            "audio_format": tts_result["format"],
            "session_id": session_id
        }
    finally:
        await db.close()


@router.post("/voice/stream")
async def voice_chat_stream(
    audio: UploadFile = File(...),
    session_id: Optional[int] = Form(None),
    enable_tts: bool = Form(False),
    current_user: dict = Depends(get_current_user)
):
    """
    语音对话流式版 - SSE 返回 ASR文本 + LLM流式文本 + TTS音频
    """
    db = await get_db()
    try:
        session_id = await _get_or_create_session(db, current_user["id"], session_id)

        audio_data = await audio.read()
        is_wav = audio.filename.lower().endswith('.wav') if audio.filename else True

        # ASR
        asr_text = await asr_service.recognize(audio_data, is_wav=is_wav)
        await _save_message(db, session_id, "user", asr_text)

        history = await _get_session_messages(db, session_id)

        async def generate():
            # 发送 ASR 结果
            yield f"data: {json.dumps({'type': 'asr', 'content': asr_text, 'session_id': session_id})}\n\n"

            # 流式 LLM
            full_response = ""
            try:
                async for chunk in llm_service.chat_stream(history):
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"

                # 保存回复
                db2 = await get_db()
                try:
                    await _save_message(db2, session_id, "assistant", full_response)
                finally:
                    await db2.close()

                # TTS 合成（仅在启用时）
                if enable_tts and full_response.strip():
                    db3 = await get_db()
                    try:
                        tts_settings = await _get_user_tts_settings(db3, current_user["id"])
                    finally:
                        await db3.close()

                    tts_result = await tts_service.synthesize(
                        full_response,
                        voice=tts_settings["voice"],
                        speed=tts_settings["speed"],
                        pitch=tts_settings["pitch"],
                        volume=tts_settings["volume"],
                    )
                    if tts_result["audio_data"]:
                        audio_b64 = base64.b64encode(tts_result["audio_data"]).decode()
                        yield f"data: {json.dumps({'type': 'audio', 'audio_base64': audio_b64, 'format': tts_result['format']})}\n\n"

                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    finally:
        await db.close()


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket 完整语音交互通道
    客户端发送: {"type": "auth", "token": "..."}  -- 认证
    客户端发送: {"type": "text", "message": "...", "session_id": int|null}  -- 文本消息
    客户端发送: {"type": "voice", "audio_base64": "...", "session_id": int|null}  -- 语音消息
    服务端返回: {"type": "asr", "content": "..."}  -- ASR 结果
    服务端返回: {"type": "text", "content": "..."}  -- LLM 文本片段
    服务端返回: {"type": "audio", "audio_base64": "...", "format": "wav"}  -- TTS 音频
    服务端返回: {"type": "done", "session_id": int}  -- 完成
    """
    await websocket.accept()
    user = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            # 认证
            if msg_type == "auth":
                try:
                    payload = decode_token(data["token"])
                    user_id = int(payload["sub"])
                    db = await get_db()
                    try:
                        cursor = await db.execute(
                            "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
                        )
                        row = await cursor.fetchone()
                        if row:
                            user = {"id": row[0], "username": row[1], "created_at": str(row[2])}
                            await websocket.send_json({"type": "auth_success", "user": user})
                        else:
                            await websocket.send_json({"type": "error", "message": "用户不存在"})
                    finally:
                        await db.close()
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"认证失败: {str(e)}"})
                continue

            if not user:
                await websocket.send_json({"type": "error", "message": "请先认证"})
                continue

            # 文本消息
            if msg_type == "text":
                db = await get_db()
                try:
                    session_id = await _get_or_create_session(db, user["id"], data.get("session_id"))
                    message = data.get("message", "")
                    await _save_message(db, session_id, "user", message)

                    history = await _get_session_messages(db, session_id)

                    # 流式 LLM
                    full_response = ""
                    async for chunk in llm_service.chat_stream(history):
                        full_response += chunk
                        await websocket.send_json({"type": "text", "content": chunk})

                    await _save_message(db, session_id, "assistant", full_response)
                    await websocket.send_json({"type": "done", "session_id": session_id})
                finally:
                    await db.close()

            # 语音消息
            elif msg_type == "voice":
                db = await get_db()
                try:
                    session_id = await _get_or_create_session(db, user["id"], data.get("session_id"))

                    # 解码音频
                    audio_b64 = data.get("audio_base64", "")
                    audio_data = base64.b64decode(audio_b64)

                    # ASR
                    asr_text = await asr_service.recognize(audio_data, is_wav=True)
                    await websocket.send_json({"type": "asr", "content": asr_text})

                    if not asr_text.strip():
                        await websocket.send_json({"type": "done", "session_id": session_id})
                        continue

                    await _save_message(db, session_id, "user", asr_text)

                    # 如果是第一条消息，生成标题
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
                    )
                    msg_count = (await cursor.fetchone())[0]
                    if msg_count <= 1:
                        title = await llm_service.generate_title(asr_text)
                        await db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
                        await db.commit()

                    history = await _get_session_messages(db, session_id)

                    # 流式 LLM
                    full_response = ""
                    async for chunk in llm_service.chat_stream(history):
                        full_response += chunk
                        await websocket.send_json({"type": "text", "content": chunk})

                    await _save_message(db, session_id, "assistant", full_response)

                    # TTS
                    tts_settings = await _get_user_tts_settings(db, user["id"])
                    tts_result = await tts_service.synthesize(
                        full_response,
                        voice=tts_settings["voice"],
                        speed=tts_settings["speed"],
                        pitch=tts_settings["pitch"],
                        volume=tts_settings["volume"],
                    )
                    if tts_result["audio_data"]:
                        tts_b64 = base64.b64encode(tts_result["audio_data"]).decode()
                        await websocket.send_json({
                            "type": "audio",
                            "audio_base64": tts_b64,
                            "format": tts_result["format"]
                        })

                    await websocket.send_json({"type": "done", "session_id": session_id})
                finally:
                    await db.close()

    except WebSocketDisconnect:
        logger.info(f"WebSocket 连接断开: user={user}")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


@router.post("/deep-research")
async def deep_research(data: DeepResearchRequest, current_user: dict = Depends(get_current_user)):
    """
    Deep Research - SSE 流式返回多轮推理步骤和最终结果
    """
    db = await get_db()
    try:
        session_id = await _get_or_create_session(db, current_user["id"], data.session_id)
        await _save_message(db, session_id, "user", f"[Deep Research] {data.question}")

        history = await _get_session_messages(db, session_id)

        async def generate():
            yield f"data: {json.dumps({'type': 'session_id', 'session_id': session_id})}\n\n"

            full_response = ""
            try:
                async for result in deep_research_service.research(data.question, history):
                    if result["type"] == "final":
                        full_response = result["content"]
                    yield f"data: {json.dumps(result)}\n\n"

                # 保存最终结果
                if full_response:
                    db2 = await get_db()
                    try:
                        await _save_message(db2, session_id, "assistant", full_response)
                    finally:
                        await db2.close()

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    finally:
        await db.close()
