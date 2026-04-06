"""
会话管理路由 - 会话的 CRUD 操作
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from datetime import datetime
from models import (
    SessionCreate, SessionUpdate, SessionResponse,
    SessionDetailResponse, MessageResponse, SessionListResponse
)
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/sessions", tags=["会话管理"])


@router.get("", response_model=SessionListResponse)
async def get_sessions(current_user: dict = Depends(get_current_user)):
    """获取当前用户的所有会话列表"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, user_id, title, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
            (current_user["id"],)
        )
        rows = await cursor.fetchall()
        sessions = [
            SessionResponse(
                id=r[0], user_id=r[1], title=r[2],
                created_at=str(r[3]), updated_at=str(r[4])
            ) for r in rows
        ]
        return SessionListResponse(sessions=sessions)
    finally:
        await db.close()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(data: SessionCreate, current_user: dict = Depends(get_current_user)):
    """创建新会话"""
    db = await get_db()
    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = await db.execute(
            "INSERT INTO sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (current_user["id"], data.title, now, now)
        )
        session_id = cursor.lastrowid
        await db.commit()

        cursor = await db.execute(
            "SELECT id, user_id, title, created_at, updated_at FROM sessions WHERE id = ?",
            (session_id,)
        )
        row = await cursor.fetchone()
        return SessionResponse(
            id=row[0], user_id=row[1], title=row[2],
            created_at=str(row[3]), updated_at=str(row[4])
        )
    finally:
        await db.close()


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: int, current_user: dict = Depends(get_current_user)):
    """获取会话详情（含消息记录）"""
    db = await get_db()
    try:
        # 获取会话信息
        cursor = await db.execute(
            "SELECT id, user_id, title, created_at, updated_at FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user["id"])
        )
        session = await cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 获取消息列表
        cursor = await db.execute(
            "SELECT id, session_id, role, content, audio_url, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        )
        msg_rows = await cursor.fetchall()
        messages = [
            MessageResponse(
                id=m[0], session_id=m[1], role=m[2],
                content=m[3], audio_url=m[4], created_at=str(m[5])
            ) for m in msg_rows
        ]

        return SessionDetailResponse(
            id=session[0], user_id=session[1], title=session[2],
            created_at=str(session[3]), updated_at=str(session[4]),
            messages=messages
        )
    finally:
        await db.close()


@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(session_id: int, data: SessionUpdate, current_user: dict = Depends(get_current_user)):
    """更新会话标题"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user["id"])
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="会话不存在")

        await db.execute(
            "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (data.title, session_id)
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT id, user_id, title, created_at, updated_at FROM sessions WHERE id = ?",
            (session_id,)
        )
        row = await cursor.fetchone()
        return SessionResponse(
            id=row[0], user_id=row[1], title=row[2],
            created_at=str(row[3]), updated_at=str(row[4])
        )
    finally:
        await db.close()


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: int, current_user: dict = Depends(get_current_user)):
    """删除会话及其所有消息"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user["id"])
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="会话不存在")

        await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
    finally:
        await db.close()
