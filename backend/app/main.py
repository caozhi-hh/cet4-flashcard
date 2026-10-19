"""FastAPI 主入口 — 后端 API + 托管前端静态文件（合并部署）"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import CORS_ORIGINS, DB_PATH
from .database import Base, engine
from .auth import csrf_middleware
from .migrations import (
    FSRS_COLUMN,
    ensure_fsrs_schema,
    ensure_study_plan_schema,
    ensure_user_scope_schema,
    ensure_word_enrichment_schema,
)
from .routers import ai, auth, plan, progress, quiz, starred, study, wordbooks, words
from .services.word_service import backfill_word_enrichment, init_words
from .database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 前端静态文件目录（Docker 里 /app/static，本地 backend/static）
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时：建表 + 初始化词库"""
    # 打印真实使用的数据库文件绝对路径。
    # config.py 里 DATA_DIR 取 "/data"（若存在），而 Windows 上 "/data" 不是绝对路径、
    # 会解析到"当前盘符根目录"。若从 C: 启动就会连到 C:\data\cet4.db 这个空库，
    # 表现为"进度全没了"。把解析结果打出来，一眼可辨。
    logger.info(f"数据库文件: {DB_PATH.resolve()}")
    Base.metadata.create_all(bind=engine)
    # 结构迁移：给历史库补上 FSRS 列（只 ADD COLUMN + 回填；改结构前会先自动备份）
    migration = ensure_fsrs_schema(engine)
    if migration["added_column"]:
        logger.info(
            f"已迁移 study_records：新增 {FSRS_COLUMN} 列，回填 {migration['backfilled']} 条历史记录"
            f"（备份：{migration['backed_up']}）"
        )
    # 词库富化字段：只加列，行内容由下面的 backfill_word_enrichment 回填
    enrich = ensure_word_enrichment_schema(engine)
    if enrich["added_columns"]:
        logger.info(f"已为 words 增加列：{enrich['added_columns']}（备份：{enrich['backed_up']}）")
    # 用户隔离：个人数据表加 user_id，daily_stats 唯一约束改为 (user_id, date)
    scoped = ensure_user_scope_schema(engine)
    if scoped["added_columns"] or scoped["daily_stats_rebuilt"]:
        logger.info(
            f"用户隔离迁移完成：加列 {scoped['added_columns']}，"
            f"daily_stats 重建={scoped['daily_stats_rebuilt']}（保留 {scoped['daily_stats_rows']} 行），"
            f"备份：{scoped['backed_up']}"
        )
    # 学习计划表：只新建一张表，不动任何已有表与数据
    plan_schema = ensure_study_plan_schema(engine)
    if plan_schema["created_table"]:
        logger.info(f"已创建 study_plans 表（备份：{plan_schema['backed_up']}）")
    db = SessionLocal()
    try:
        count = init_words(db)
        if count > 0:
            logger.info(f"词库初始化完成: {count} 个词")
        # 老词库缺 ECDICT 富化字段（tags/frq/…），这里回填，否则按考试标签的词书会是空的
        filled = backfill_word_enrichment(db)
        if filled:
            logger.info(f"词库富化字段回填: {filled} 个词")
    finally:
        db.close()
    yield


app = FastAPI(title="腰子背单词", version="1.0.0", lifespan=lifespan)

# CSRF 中间件先注册：Starlette 的 add_middleware 是"前插"，所以后注册的 CORS 会位于最外层，
# 这样被 CSRF 拦下的 403 响应也能带上 CORS 头，浏览器才读得到真实状态码
app.middleware("http")(csrf_middleware)

# CORS（合并部署同源不需要，保留兼容本地 dev 跨端口）
# allow_credentials=True 是 Cookie 认证的前提；配合白名单而不是 "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由（必须先注册，优先于下面的 SPA 兜底）
app.include_router(auth.router)
app.include_router(plan.router)
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
    """未匹配 API 的 GET 请求 → 返回前端静态文件（兼容 Next.js 静态导出两种路由形态）"""
    # /api 下未命中的请求直接 404
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="Not Found")
    # 去掉尾部斜杠，让 /study 与 /study/ 等价
    clean = full_path.rstrip("/")
    # 1) 精确文件（_next 静态资源、图标等）
    f = STATIC_DIR / full_path
    if f.is_file():
        return FileResponse(f)
    # 2) 页面文件：Next.js output:export 默认生成 study.html（非 trailingSlash 模式）
    #    缺这一步会导致直接访问/刷新 /study 等子页时错误地拿到首页
    if clean:
        page = STATIC_DIR / f"{clean}.html"
        if page.is_file():
            return FileResponse(page)
    # 3) 目录式路由 → index.html（trailingSlash 模式）
    idx = STATIC_DIR / clean / "index.html"
    if idx.is_file():
        return FileResponse(idx)
    # 4) 根路径或未知路由 → 首页
    home = STATIC_DIR / "index.html"
    if home.is_file():
        return FileResponse(home)
    return {"detail": "前端未构建，请先 build"}
