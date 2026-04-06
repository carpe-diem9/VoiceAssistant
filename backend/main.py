"""
FastAPI 主入口 - 智能语音助理后端服务
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import auth_router, session_router, chat_router, settings_router
from config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("正在初始化数据库...")
    await init_db()
    logger.info("数据库初始化完成")
    logger.info(f"服务端启动在 http://{settings.SERVER_HOST}:{settings.SERVER_PORT}")
    yield
    logger.info("服务端正在关闭...")


# 创建 FastAPI 应用
app = FastAPI(
    title="智能语音助理 API",
    description="基于大语言模型的 Android 智能语音助理系统后端",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置 - 允许移动端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth_router.router)
app.include_router(session_router.router)
app.include_router(chat_router.router)
app.include_router(settings_router.router)


@app.get("/")
async def root():
    """健康检查接口"""
    return {
        "service": "智能语音助理 API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api/health")
async def health_check():
    """详细健康检查"""
    return {
        "status": "healthy",
        "asr_model": settings.ASR_MODEL,
        "tts_model": settings.TTS_MODEL,
        "llm_model": settings.LLM_MODEL,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=True,
        log_level="info"
    )
