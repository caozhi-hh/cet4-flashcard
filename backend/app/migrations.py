"""数据库结构迁移

安全原则（重要）：
    1. 只做 ADD COLUMN 和 NULL 回填，绝不 DROP 列、绝不删除行、绝不改既有列类型。
    2. 动结构前必须先成功备份数据库；备份失败就拒绝迁移（宁可不动，也不能没备份就改）。
    3. 幂等：列已存在直接返回，不重复加列、不重复回填。
    4. 备份用 sqlite3 的在线备份 API，而不是复制文件——WAL 模式下文件复制可能拿到不一致的快照。

方言差异（SQLite / PostgreSQL）：
    - 这些 ensure_* 函数原本是为**已有 SQLite 库**做就地升级而写的（PRAGMA、ALTER TABLE、
      重建表换约束、sqlite3 备份）。
    - PostgreSQL（Render + Neon）是全新库：表结构由 `Base.metadata.create_all` 按模型一次建好，
      因此**不对 PostgreSQL 执行任何 SQLite 专有动作**（不 PRAGMA、不 sqlite3 备份、不重建表）。
    - 若 PostgreSQL 里已存在的表缺少模型要求的列/约束，本模块**明确抛错并停止**，
      不会静默改结构——需要人工审查后执行迁移（见 verify_schema）。

备份位置：默认放在数据库文件同级的 backups/ 目录；可用环境变量 CET4_BACKUP_DIR 覆盖。
"""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

FSRS_COLUMN = "fsrs_card"
BACKUP_ENV = "CET4_BACKUP_DIR"


class SchemaMigrationRequired(RuntimeError):
    """PostgreSQL 上检测到结构落后于模型，需要人工审查后迁移（不自动改）"""


def is_sqlite(engine: Engine) -> bool:
    """是否 SQLite 方言（备份、PRAGMA、重建表等只对 SQLite 有效）"""
    return engine.dialect.name == "sqlite"

# words 表的 ECDICT 富化列：列名 → SQLite 类型
WORD_ENRICHMENT_COLUMNS: dict[str, str] = {
    "tags": "VARCHAR(100)",
    "frq": "INTEGER",
    "bnc": "INTEGER",
    "collins": "INTEGER",
    "oxford": "INTEGER",
}

# 需要按用户隔离的表：列名 → 类型（NULL = 多用户改造前的遗留数据，对任何用户都不可见）
USER_SCOPED_COLUMNS: dict[str, dict[str, str]] = {
    "study_records": {"user_id": "INTEGER"},
    "custom_wordbooks": {"user_id": "INTEGER"},
    "starred_words": {"user_id": "INTEGER"},
}

DAILY_STATS_UNIQUE_NAME = "uq_daily_stats_user_date"


def _db_file(engine: Engine) -> Path | None:
    """从引擎 URL 反推 SQLite 文件路径；**非 SQLite 一律返回 None**

    必须显式判方言：PostgreSQL 的 `engine.url.database` 是数据库名（如 neondb），
    不是文件路径。若照旧解析，会拿数据库名当成本地文件去"备份"。
    内存库同样返回 None。
    """
    if not is_sqlite(engine):
        return None
    database = engine.url.database
    if not database or database == ":memory:":
        return None
    # Windows 上 config 里可能给出 "\data\cet4.db" 这类"当前盘符相对"路径，resolve 后再用
    return Path(database).resolve()


def _backup_database(db_file: Path, backup_dir: Path) -> Path:
    """用 sqlite3 在线备份 API 生成一致性快照，并校验产物非空"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{db_file.name}.bak-{stamp}"

    source = sqlite3.connect(str(db_file))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"数据库备份失败，产物无效：{dest}")
    return dest


def _table_columns(engine: Engine, table: str) -> list[str]:
    """读取表的列名；按方言选查询方式（SQLite: PRAGMA，PG: information_schema）"""
    if is_sqlite(engine):
        with engine.connect() as conn:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return [row[1] for row in rows]

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :t "
                "ORDER BY ordinal_position"
            ),
            {"t": table},
        ).fetchall()
    return [row[0] for row in rows]


def _pg_index_defs(engine: Engine, table: str) -> list[str]:
    """PostgreSQL：读取表的索引定义（用于校验唯一约束是否存在）"""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() AND tablename = :t"
            ),
            {"t": table},
        ).fetchall()
    return [row[0] or "" for row in rows]


def _create_table_via_metadata(engine: Engine, table_name: str) -> None:
    """用 SQLAlchemy 元数据建表（方言正确：PG 用序列/IDENTITY，SQLite 用 AUTOINCREMENT）

    非 SQLite 环境下不用手写 DDL，避免写出 SQLite 专有语法。
    """
    from . import models  # noqa: F401  确保模型已注册到 metadata
    from .database import Base

    table = Base.metadata.tables.get(table_name)
    if table is None:
        raise RuntimeError(f"模型里找不到表 {table_name}，无法建表")
    Base.metadata.create_all(bind=engine, tables=[table])


def verify_schema(engine: Engine) -> dict:
    """校验 PostgreSQL 结构是否与模型一致；不一致则**抛错停止**（不自动改）

    只在非 SQLite 上执行：全新库由 create_all 建好，本函数是个安全网——
    若线上库落后于模型（缺少列或缺少 daily_stats 的唯一约束），
    宁可启动失败也不要静默改结构、更不能带着错结构继续跑。

    返回 {"checked_tables": int}
    """
    if is_sqlite(engine):
        return {"checked_tables": 0}

    from . import models  # noqa: F401
    from .database import Base

    problems: list[str] = []
    checked = 0
    for table_name, table in Base.metadata.tables.items():
        actual = _table_columns(engine, table_name)
        if not actual:
            problems.append(f"缺少表 {table_name}（应先由 create_all 建表）")
            continue
        checked += 1
        expected = {c.name for c in table.columns}
        missing = sorted(expected - set(actual))
        if missing:
            problems.append(
                f"{table_name} 缺少列 {missing}；请人工审查后执行 "
                f"ALTER TABLE {table_name} ADD COLUMN ...（本服务不会自动改结构）"
            )

    # daily_stats 的 UNIQUE(user_id, date) 是并发安全的依据，单列 date 唯一会让第二个用户当天写不进去
    index_defs = _pg_index_defs(engine, "daily_stats")
    if _table_columns(engine, "daily_stats") and not any(
        "unique" in d.lower() and "user_id" in d and "date" in d for d in index_defs
    ):
        problems.append(
            "daily_stats 缺少 UNIQUE(user_id, date) 约束（当前只有 date 唯一会导致多用户冲突）；"
            "请人工审查后重建该约束，本服务不会自动改"
        )

    if problems:
        raise SchemaMigrationRequired(
            "PostgreSQL 结构落后于模型，已停止启动以避免静默改结构：\n  - " + "\n  - ".join(problems)
        )
    logger.info(f"PostgreSQL 结构校验通过（{checked} 张表）")
    return {"checked_tables": checked}


def backfill_fsrs_cards(engine: Engine) -> int:
    """给还没有 fsrs_card 的历史记录补一份卡片状态，返回回填条数"""
    from .fsrs_service import card_from_legacy

    filled = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, status, next_review_at, last_studied_at "
                "FROM study_records WHERE fsrs_card IS NULL"
            )
        ).fetchall()
        for row in rows:
            card_json = card_from_legacy(row.status, row.next_review_at, row.last_studied_at)
            conn.execute(
                text("UPDATE study_records SET fsrs_card = :card WHERE id = :id"),
                {"card": card_json, "id": row.id},
            )
            filled += 1
    return filled


def _backup_once(engine: Engine, backup_dir: Path | None) -> str | None:
    """动结构前备份一次；SQLite 之外一律跳过（PG 不是文件库，也绝不对它跑 sqlite3 备份）"""
    if not is_sqlite(engine):
        logger.info("非 SQLite 后端：跳过文件级备份（PostgreSQL 请用平台自带备份/PITR）")
        return None
    db_file = _db_file(engine)
    if not (db_file and db_file.exists()):
        return None
    resolved = Path(os.getenv(BACKUP_ENV) or backup_dir or (db_file.parent / "backups"))
    path = _backup_database(db_file, resolved)
    logger.info(f"迁移前已备份数据库：{path}")
    return str(path)


def ensure_columns(
    engine: Engine,
    table: str,
    specs: dict[str, str],
    backup_dir: Path | None = None,
    skip_backup: bool = False,
) -> dict:
    """确保 table 具备 specs 里声明的列（缺失的用 ALTER TABLE ADD COLUMN 补上）。

    返回 {"added_columns": [...], "backed_up": str | None}
    只追加列：不改既有列类型、不删列、不动任何行；首次新增前先备份一次。
    幂等：列齐了直接返回，不备份也不改结构。
    skip_backup=True 供"调用方已统一备份过"的场景使用，避免一次迁移产生多个备份文件。
    """
    columns = _table_columns(engine, table)
    if not columns:
        # 表还不存在（全新库）：create_all 会直接按新模型建好，无需迁移
        return {"added_columns": [], "backed_up": None}

    missing = [name for name in specs if name not in columns]
    if not missing:
        return {"added_columns": [], "backed_up": None}

    if not is_sqlite(engine):
        # PostgreSQL：不在这里做就地 ALTER（没有文件级备份可依赖，改动需要人工审查）
        raise SchemaMigrationRequired(
            f"{table} 缺少列 {sorted(missing)}（PostgreSQL 不做自动迁移）。"
            f"请在审查后手工执行："
            + "；".join(f"ALTER TABLE {table} ADD COLUMN {n} {specs[n]}" for n in missing)
        )

    backed_up = None if skip_backup else _backup_once(engine, backup_dir)
    with engine.begin() as conn:
        for name in missing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {specs[name]}"))
    logger.info(f"{table} 新增列：{missing}")
    return {"added_columns": missing, "backed_up": backed_up}


def ensure_fsrs_schema(engine: Engine, backup_dir: Path | None = None) -> dict:
    """确保 study_records 具备 FSRS 所需结构并回填历史记录

    返回 {"added_column": bool, "backfilled": int, "backed_up": str | None}
    """
    result = ensure_columns(engine, "study_records", {FSRS_COLUMN: "TEXT"}, backup_dir)
    if not result["added_columns"]:
        return {"added_column": False, "backfilled": 0, "backed_up": None}

    filled = backfill_fsrs_cards(engine)
    logger.info(f"study_records 新增 {FSRS_COLUMN} 列，回填 {filled} 条历史记录")
    return {"added_column": True, "backfilled": filled, "backed_up": result["backed_up"]}


def ensure_word_enrichment_schema(engine: Engine, backup_dir: Path | None = None) -> dict:
    """确保 words 表具备 ECDICT 富化列

    只加列；行内容回填交给 word_service.backfill_word_enrichment（需要 ORM 会话与 JSON）。
    """
    result = ensure_columns(engine, "words", WORD_ENRICHMENT_COLUMNS, backup_dir)
    return {"added_columns": result["added_columns"], "backed_up": result["backed_up"]}


def _daily_stats_has_user_id(engine: Engine) -> bool:
    return "user_id" in _table_columns(engine, "daily_stats")


def _rebuild_daily_stats(engine: Engine) -> int:
    """重建 daily_stats，把 UNIQUE(date) 换成 UNIQUE(user_id, date)，返回保留的行数

    SQLite 不能直接改约束，只能"建新表 → 完整拷贝 → 换名"。
    - 拷贝时显式写出每一列，主键 id 一并保留（行身份不变）；
    - user_id 一律写 NULL：遗留统计**不归属任何用户**，
      SQLite 中 NULL 互不相等，因此多行 NULL 不会撞唯一约束，也不会被任何用户查询到。
    - id 用 INSERT 显式写入，所以 AUTOINCREMENT 序列会被 SQLite 自动抬到 max(id) 之上。
    """
    if not is_sqlite(engine):
        # PostgreSQL 不能这样换约束；全新库由模型的 UniqueConstraint 直接建好
        raise SchemaMigrationRequired(
            "daily_stats 重建只适用于 SQLite；PostgreSQL 请在审查后手工重建唯一约束"
        )

    with engine.begin() as conn:
        conn.execute(text(
            f"""
            CREATE TABLE daily_stats_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                date VARCHAR(10) NOT NULL,
                user_id INTEGER,
                new_words INTEGER DEFAULT 0,
                reviewed_words INTEGER DEFAULT 0,
                quiz_score INTEGER DEFAULT 0,
                quiz_total INTEGER DEFAULT 0,
                streak_days INTEGER DEFAULT 0,
                CONSTRAINT {DAILY_STATS_UNIQUE_NAME} UNIQUE (user_id, date)
            )
            """
        ))
        before = conn.execute(text("SELECT COUNT(*) FROM daily_stats")).scalar() or 0
        conn.execute(text(
            """
            INSERT INTO daily_stats_new
                (id, date, user_id, new_words, reviewed_words, quiz_score, quiz_total, streak_days)
            SELECT id, date, NULL, new_words, reviewed_words, quiz_score, quiz_total, streak_days
            FROM daily_stats
            """
        ))
        after = conn.execute(text("SELECT COUNT(*) FROM daily_stats_new")).scalar() or 0
        if int(after) != int(before):
            raise RuntimeError(f"daily_stats 重建拷贝行数不一致：{before} -> {after}，已中止")
        conn.execute(text("DROP TABLE daily_stats"))
        conn.execute(text("ALTER TABLE daily_stats_new RENAME TO daily_stats"))
    return int(after)


def ensure_user_scope_schema(engine: Engine, backup_dir: Path | None = None) -> dict:
    """为用户隔离做结构迁移

    返回 {"added_columns": {表: [列]}, "daily_stats_rebuilt": bool,
          "daily_stats_rows": int | None, "backed_up": str | None}

    顺序：先判断是否真的需要改 → 需要则**统一备份一次** → 加列 → 重建 daily_stats。
    幂等：daily_stats 已有 user_id 即整体视为已迁移（其余表同步检查）。
    PostgreSQL：交由 verify_schema 校验，缺列即明确失败，不在这里改结构。
    """
    if not is_sqlite(engine):
        verify_schema(engine)
        return {
            "added_columns": {},
            "daily_stats_rebuilt": False,
            "daily_stats_rows": None,
            "backed_up": None,
            "verified": True,
        }

    needs_columns = any(
        name not in _table_columns(engine, table)
        for table, specs in USER_SCOPED_COLUMNS.items()
        for name in specs
    )
    needs_rebuild = bool(_table_columns(engine, "daily_stats")) and not _daily_stats_has_user_id(engine)

    if not needs_columns and not needs_rebuild:
        return {"added_columns": {}, "daily_stats_rebuilt": False, "daily_stats_rows": None, "backed_up": None}

    backed_up = _backup_once(engine, backup_dir)

    added: dict[str, list[str]] = {}
    for table, specs in USER_SCOPED_COLUMNS.items():
        result = ensure_columns(engine, table, specs, skip_backup=True)
        if result["added_columns"]:
            added[table] = result["added_columns"]

    rows: int | None = None
    if needs_rebuild:
        rows = _rebuild_daily_stats(engine)
        logger.info(f"daily_stats 已重建为 UNIQUE(user_id, date)，保留 {rows} 行（user_id 均为 NULL）")

    return {
        "added_columns": added,
        "daily_stats_rebuilt": needs_rebuild,
        "daily_stats_rows": rows,
        "backed_up": backed_up,
    }


STUDY_PLAN_TABLE = "study_plans"


def ensure_study_plan_schema(engine: Engine, backup_dir: Path | None = None) -> dict:
    """确保 study_plans 表存在（学习计划功能）

    只**新建一张表**：不碰任何已有表、不增删任何行，因此不存在历史数据被改动或
    被分配给其他用户的风险。建表前先备份（沿用备份优先原则）。
    幂等：表已存在（含全新库由 create_all 建好的情况）直接返回。

    返回 {"created_table": bool, "backed_up": str | None}
    """
    if _table_columns(engine, STUDY_PLAN_TABLE):
        return {"created_table": False, "backed_up": None}

    if not is_sqlite(engine):
        # PostgreSQL：按模型建表（方言正确，含唯一索引），不需要也不会做 sqlite 备份
        _create_table_via_metadata(engine, STUDY_PLAN_TABLE)
        logger.info(f"{STUDY_PLAN_TABLE} 表已按模型创建（PostgreSQL）")
        return {"created_table": True, "backed_up": None}

    backed_up = _backup_once(engine, backup_dir)
    with engine.begin() as conn:
        conn.execute(text(
            f"""
            CREATE TABLE {STUDY_PLAN_TABLE} (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                goal_type VARCHAR(32) NOT NULL,
                wordbook_key VARCHAR(64) NOT NULL,
                target_date VARCHAR(10),
                daily_new_words INTEGER NOT NULL DEFAULT 20,
                created_at VARCHAR(40),
                updated_at VARCHAR(40)
            )
            """
        ))
        # 与 ORM（user_id: unique=True, index=True）一致：唯一索引，保证每个用户只有一份生效计划
        conn.execute(text(
            f"CREATE UNIQUE INDEX ix_{STUDY_PLAN_TABLE}_user_id ON {STUDY_PLAN_TABLE} (user_id)"
        ))
    logger.info(f"{STUDY_PLAN_TABLE} 表已创建（备份：{backed_up}）")
    return {"created_table": True, "backed_up": backed_up}


READING_TABLE = "reading_attempts"


def ensure_reading_schema(engine: Engine, backup_dir: Path | None = None) -> dict:
    """确保 reading_attempts 表存在（分级阅读的答题记录）

    同样只**新建一张表**：不动任何已有表与行；建表前先备份；幂等。
    返回 {"created_table": bool, "backed_up": str | None}
    """
    if _table_columns(engine, READING_TABLE):
        return {"created_table": False, "backed_up": None}

    if not is_sqlite(engine):
        _create_table_via_metadata(engine, READING_TABLE)
        logger.info(f"{READING_TABLE} 表已按模型创建（PostgreSQL）")
        return {"created_table": True, "backed_up": None}

    backed_up = _backup_once(engine, backup_dir)
    with engine.begin() as conn:
        conn.execute(text(
            f"""
            CREATE TABLE {READING_TABLE} (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slug VARCHAR(64) NOT NULL,
                level VARCHAR(8),
                score INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                duration_seconds INTEGER DEFAULT 0,
                completed_at VARCHAR(40),
                created_at VARCHAR(40)
            )
            """
        ))
        # 查询都按 (user_id) 与 (slug) 走
        conn.execute(text(f"CREATE INDEX ix_{READING_TABLE}_user_id ON {READING_TABLE} (user_id)"))
        conn.execute(text(f"CREATE INDEX ix_{READING_TABLE}_slug ON {READING_TABLE} (slug)"))
        conn.execute(
            text(f"CREATE INDEX ix_{READING_TABLE}_completed_at ON {READING_TABLE} (completed_at)")
        )
    logger.info(f"{READING_TABLE} 表已创建（备份：{backed_up}）")
    return {"created_table": True, "backed_up": backed_up}
