"""数据库后端适配测试（SQLite ↔ PostgreSQL）—— 无需 PostgreSQL 服务器

覆盖：
    1) DATABASE_URL 规整与方言判定
    2) 两种后端的引擎参数必须分开配置（check_same_thread 不能给 PG）
    3) PG 的数据库名**不能**被当成本地 SQLite 文件路径
    4) 非 SQLite 后端绝不执行 sqlite3 备份
    5) PostgreSQL 建表的 DDL 正确性（编译级校验：无 AUTOINCREMENT、唯一约束齐全、索引齐全）
    6) PG 上结构落后时**明确失败**（SchemaMigrationRequired），不静默改结构
    7) SQLite 分支行为不变（加列 + 备份优先仍然生效）

注意：本文件不连接任何 PostgreSQL 服务器（DDL 用方言编译校验，连接类断言用引擎对象）。
真实 PostgreSQL 端到端测试见 test_postgres_integration.py（需要 TEST_DATABASE_URL）。

运行：python tests/test_db_backend.py
"""

import atexit
import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-db-backend"
if TMP_DIR.exists():
    shutil.rmtree(TMP_DIR, ignore_errors=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

import app.config as config  # noqa: E402

config.DB_PATH = TMP_DIR / "cet4.db"
config.DATABASE_URL = f"sqlite:///{config.DB_PATH}"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.dialects import postgresql, sqlite as sqlite_dialect  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app import migrations  # noqa: E402
from app.database import engine_kwargs_for  # noqa: E402
from app.models import (  # noqa: E402
    AuthSession,
    DailyStat,
    ReadingAttempt,
    StudyPlan,
    StudyRecord,
    User,
)

PG_URL = "postgresql+psycopg://user:pw@ep-test-123.ap-southeast-1.aws.neon.tech/neondb"


def _cleanup():
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup)


def _pg_engine():
    """构造一个 PostgreSQL 引擎对象（不会真的去连接）"""
    return create_engine(PG_URL)


# === 1. URL 规整与方言判定 ===

def test_normalize_database_url():
    cases = [
        # Render/Neon 面板可能给旧写法 postgres://
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        # 标准写法补上驱动
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        # 已显式指定驱动的原样保留
        ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        # SQLite 不动
        ("sqlite:///D:/data/cet4.db", "sqlite:///D:/data/cet4.db"),
        ("", ""),
        ("  postgres://u:p@h/db  ", "postgresql+psycopg://u:p@h/db"),
    ]
    for raw, expected in cases:
        got = config.normalize_database_url(raw)
        assert got == expected, f"{raw!r} -> {got!r}，期望 {expected!r}"


def test_backend_for_url():
    assert config.backend_for_url("postgresql+psycopg://u:p@h/db") == "postgresql"
    assert config.backend_for_url("postgresql://u:p@h/db") == "postgresql"
    assert config.backend_for_url("sqlite:///x.db") == "sqlite"
    assert config.backend_for_url("") == "sqlite"
    # 未设置 DATABASE_URL 时必须仍是 SQLite（本地开发/现有测试不受影响）
    assert config.DB_BACKEND in ("sqlite", "postgresql")
    if not __import__("os").environ.get("DATABASE_URL"):
        assert config.DB_BACKEND == "sqlite", "未设置 DATABASE_URL 时默认必须是 SQLite"
        assert config.IS_SQLITE is True


# === 2. 引擎参数分开配置 ===

def test_engine_kwargs_are_dialect_specific():
    pg = engine_kwargs_for("postgresql")
    sq = engine_kwargs_for("sqlite")

    assert "check_same_thread" not in str(pg.get("connect_args", {})), "PG 不能收到 check_same_thread"
    assert pg["pool_pre_ping"] is True, "Neon 空闲会挂起，必须探活"
    assert pg["pool_recycle"] == 300
    assert "pool_size" in pg and "max_overflow" in pg

    assert sq["connect_args"] == {"check_same_thread": False}
    assert "pool_pre_ping" not in sq

    # 返回的是副本：改一个不影响另一个
    pg["pool_size"] = 99
    assert engine_kwargs_for("postgresql")["pool_size"] == 5


# === 3/4. 不把 PG 当文件库 ===

def test_pg_database_name_is_not_treated_as_sqlite_file():
    pg = _pg_engine()
    assert pg.url.database == "neondb"  # 这是库名
    assert migrations._db_file(pg) is None, "PG 的库名不能被当成本地文件路径"
    assert migrations.is_sqlite(pg) is False

    # SQLite 仍然能解析出绝对路径
    sq = create_engine(f"sqlite:///{config.DB_PATH}")
    assert migrations._db_file(sq) == config.DB_PATH.resolve()
    assert migrations.is_sqlite(sq) is True


def test_no_sqlite_backup_on_postgres():
    """非 SQLite 后端：备份直接跳过，且绝不调用 sqlite3 备份实现"""
    called = []
    original = migrations._backup_database
    migrations._backup_database = lambda *a, **k: called.append(a)  # type: ignore[assignment]
    try:
        assert migrations._backup_once(_pg_engine(), None) is None
    finally:
        migrations._backup_database = original  # type: ignore[assignment]
    assert called == [], "对 PostgreSQL 执行了 sqlite3 备份"


# === 5. PG DDL 编译级校验 ===

def _ddl(table) -> str:
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_postgres_ddl_has_no_sqlite_specifics():
    """PG 自增主键用 SERIAL；绝不应出现 SQLite 的 AUTOINCREMENT"""
    for table in (User.__table__, AuthSession.__table__, StudyRecord.__table__,
                  DailyStat.__table__, StudyPlan.__table__, ReadingAttempt.__table__):
        ddl = _ddl(table)
        upper = ddl.upper()
        assert "AUTOINCREMENT" not in upper, f"{table.name} 的 PG DDL 里出现了 AUTOINCREMENT：{ddl}"
        assert "PRIMARY KEY" in upper, f"{table.name} 缺少主键：{ddl}"
        assert "SERIAL" in upper, f"{table.name} 的自增主键应为 SERIAL：{ddl}"

    # 对照：同一条模型在 SQLite 方言下用 INTEGER 主键（没有 SERIAL），证明两种 DDL 确有差异
    sq_ddl = str(CreateTable(StudyPlan.__table__).compile(dialect=sqlite_dialect.dialect()))
    assert "SERIAL" not in sq_ddl.upper(), sq_ddl


def test_postgres_ddl_uniques_and_indexes():
    # 复合唯一（daily_stats）是内联约束：多用户同一天各写一行靠它
    daily_ddl = _ddl(DailyStat.__table__)
    assert "CONSTRAINT uq_daily_stats_user_date UNIQUE (user_id, date)" in daily_ddl, daily_ddl

    # unique=True + index=True 的列 → 独立的唯一索引
    def unique_index_table(table) -> set[str]:
        return {i.name for i in table.indexes if i.unique}

    assert "ix_users_email" in unique_index_table(User.__table__), unique_index_table(User.__table__)
    assert "ix_auth_sessions_token_hash" in unique_index_table(AuthSession.__table__)
    assert "ix_study_plans_user_id" in unique_index_table(StudyPlan.__table__), "每个用户只能有一份计划"

    # 唯一索引在 PG 下必须编译成 CREATE UNIQUE INDEX
    for table, name in ((User.__table__, "ix_users_email"),
                        (AuthSession.__table__, "ix_auth_sessions_token_hash"),
                        (StudyPlan.__table__, "ix_study_plans_user_id")):
        index = next(i for i in table.indexes if i.name == name)
        ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect())).upper()
        assert ddl.startswith("CREATE UNIQUE INDEX"), ddl

    # reading_attempts 的三个查询索引
    idx = {i.name for i in ReadingAttempt.__table__.indexes}
    assert {"ix_reading_attempts_user_id", "ix_reading_attempts_slug",
            "ix_reading_attempts_completed_at"} <= idx, idx
    for index in ReadingAttempt.__table__.indexes:
        ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        assert "CREATE INDEX" in ddl.upper(), ddl


# === 6. PG 结构落后 → 明确失败 ===

def test_pg_missing_columns_fail_loudly():
    original = migrations._table_columns
    migrations._table_columns = lambda engine, table: (  # type: ignore[assignment]
        ["id", "word"] if table == "words" else ["id"]
    )
    try:
        try:
            migrations.ensure_columns(_pg_engine(), "words", {"tags": "VARCHAR(100)"})
            raise AssertionError("PG 缺列时应当抛 SchemaMigrationRequired")
        except migrations.SchemaMigrationRequired as exc:
            assert "tags" in str(exc) and "ALTER TABLE words ADD COLUMN" in str(exc), str(exc)
    finally:
        migrations._table_columns = original  # type: ignore[assignment]


def test_pg_daily_stats_rebuild_is_refused():
    try:
        migrations._rebuild_daily_stats(_pg_engine())
        raise AssertionError("PG 上不应允许 SQLite 式重建")
    except migrations.SchemaMigrationRequired as exc:
        assert "SQLite" in str(exc)


def test_verify_schema_is_noop_on_sqlite():
    sq = create_engine(f"sqlite:///{config.DB_PATH}")
    assert migrations.verify_schema(sq) == {"checked_tables": 0}


def test_create_table_via_metadata_rejects_unknown_table():
    try:
        migrations._create_table_via_metadata(_pg_engine(), "no_such_table")
        raise AssertionError("未知表名应当报错")
    except RuntimeError as exc:
        assert "no_such_table" in str(exc)


# === 7. SQLite 分支行为不变 ===

def test_sqlite_branch_still_migrates_with_backup():
    db_path = TMP_DIR / "legacy.db"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE words (id INTEGER PRIMARY KEY AUTOINCREMENT, word VARCHAR(100) NOT NULL)")
    con.execute("INSERT INTO words (word) VALUES ('legacy')")
    con.commit()
    con.close()

    eng = create_engine(f"sqlite:///{db_path}")
    try:
        result = migrations.ensure_columns(eng, "words", {"tags": "VARCHAR(100)"},
                                          backup_dir=TMP_DIR / "backups")
    finally:
        eng.dispose()

    assert result["added_columns"] == ["tags"], result
    assert result["backed_up"] and Path(result["backed_up"]).exists(), "SQLite 分支必须仍然先备份"

    con = sqlite3.connect(str(db_path))
    cols = [r[1] for r in con.execute("PRAGMA table_info(words)")]
    rows = con.execute("select count(*) from words").fetchone()[0]
    con.close()
    assert "tags" in cols and rows == 1, (cols, rows)


def test_real_database_untouched():
    import os

    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    real = Path(r"D:\data\cet4.db")
    if real.exists():
        con = sqlite3.connect(str(real))
        n = con.execute("select count(*) from study_records").fetchone()[0]
        con.close()
        assert n == 21, f"真实库 study_records 计数变了：{n}"
    assert not os.environ.get("DATABASE_URL"), "本测试进程不应带 DATABASE_URL（否则会连到真实 PG）"


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in checks:
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL", fn.__name__, "->", exc)
        except Exception as exc:
            failed += 1
            print("ERROR", fn.__name__, "->", type(exc).__name__, exc)
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)