"""FastAPI 主入口 — 后端 API + 托管前端静态文件（合并部署）"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import CORS_ORIGINS
from .database import Base, engine
from .routers import ai, progress, quiz, starred, study, wordbooks, words
from .services.word_service import init_words
from .database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 前端静态文件目录（Docker 里 /app/static，本地 backend/static）
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时：建表 + 初始化词库"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        count = init_words(db)
        if count > 0:
            logger.info(f"词库初始化完成: {count} 个词")
    finally:
        db.close()
    yield


app = FastAPI(title="腰子背单词", version="1.0.0", lifespan=lifespan)

# CORS（合并部署同源不需要，保留兼容本地 dev 跨端口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由（必须先注册，优先于下面的 SPA 兜底）
app.include_router(words.router)
app.include_router(wordbooks.router)
app.include_router(study.router)
app.include_router(quiz.router)
app.include_router(progress.router)
app.include_router(starred.router)
app.include_router(ai.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# === 前端静态文件托管（SPA 兜底，注册在最后）===
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """未匹配 API 的 GET 请求 → 返回前端静态文件（支持 Next.js 目录式路由）"""
    # /api 下未命中的请求直接 404
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="Not Found")
    # 精确文件（_next 静态资源等）
    f = STATIC_DIR / full_path
    if f.is_file():
        return FileResponse(f)
    # 目录式路由 → index.html（如 /study → static/study/index.html）
    idx = STATIC_DIR / full_path / "index.html"
    if idx.is_file():
        return FileResponse(idx)
    # 根路径或未知路由 → 首页
    home = STATIC_DIR / "index.html"
    if home.is_file():
        return FileResponse(home)
    return {"detail": "前端未构建，请先 build"}
