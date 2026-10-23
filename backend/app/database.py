"""数据库引擎和会话管理

支持两种后端，按 DATABASE_URL 自动选择：
    - SQLite（默认，本地开发/现有测试）：文件库，需要 check_same_thread=False 才能跨线程用连接；
    - PostgreSQL（Render + Neon 生产）：连接可能被服务端（或 Neon 的空闲暂停）单方面断开，
      因此开启 pool_pre_ping 与 pool_recycle，让连接池自己探活/回收，而不是把坏连接交给请求。

两种后端的连接参数**必须分开配置**：把 check_same_thread 传给 PostgreSQL 会直接报错。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, backend_for_url

# 连接被服务端断开后最容易出现的现象是"第一个请求 500、之后恢复"，
# pool_pre_ping 在每次取连接时先探活，pool_recycle 主动回收老连接（Neon 空闲会挂起）。
POSTGRES_ENGINE_KWARGS = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_size": 5,
    "max_overflow": 5,
}
SQLITE_ENGINE_KWARGS = {
    "connect_args": {"check_same_thread": False},
}


def engine_kwargs_for(backend: str) -> dict:
    """按方言返回引擎参数（单独成函数，便于测试直接断言两种配置）"""
    return dict(POSTGRES_ENGINE_KWARGS if backend == "postgresql" else SQLITE_ENGINE_KWARGS)


engine = create_engine(DATABASE_URL, **engine_kwargs_for(backend_for_url(DATABASE_URL)))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping() -> bool:
    """探活：健康检查用。失败不抛异常，交由调用方决定如何展示。"""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 — 任何连接/驱动异常都视为不可用
        return False