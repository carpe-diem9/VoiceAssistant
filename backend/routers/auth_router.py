"""
认证路由 - 用户注册、登录、获取当前用户信息
"""
from fastapi import APIRouter, HTTPException, Depends, status
from models import UserRegister, UserLogin, UserResponse, TokenResponse
from auth import hash_password, verify_password, create_access_token, get_current_user
from database import get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister):
    """用户注册"""
    db = await get_db()
    try:
        # 检查用户名是否已存在
        cursor = await db.execute("SELECT id FROM users WHERE username = ?", (data.username,))
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="用户名已存在")

        # 创建用户
        hashed = hash_password(data.password)
        cursor = await db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (data.username, hashed)
        )
        user_id = cursor.lastrowid

        # 创建默认用户设置
        await db.execute(
            "INSERT INTO user_settings (user_id) VALUES (?)",
            (user_id,)
        )

        await db.commit()

        # 获取用户信息
        cursor = await db.execute("SELECT id, username, created_at FROM users WHERE id = ?", (user_id,))
        user = await cursor.fetchone()

        # 生成 token
        token = create_access_token(data={"sub": str(user_id)})

        return TokenResponse(
            access_token=token,
            user=UserResponse(id=user[0], username=user[1], created_at=str(user[2]))
        )
    finally:
        await db.close()


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin):
    """用户登录"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (data.username,)
        )
        user = await cursor.fetchone()

        if not user or not verify_password(data.password, user[2]):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        token = create_access_token(data={"sub": str(user[0])})

        return TokenResponse(
            access_token=token,
            user=UserResponse(id=user[0], username=user[1], created_at=str(user[3]))
        )
    finally:
        await db.close()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserResponse(**current_user)
