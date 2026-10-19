"""数据库结构迁移

目前只有一步：给 study_records 加 FSRS 卡片状态列，并回填历史记录。

安全原则（重要）：
    1. 只做 ADD COLUMN 和 NULL 回填，绝不 DROP 列、绝不删除行、绝不改既有列类型。
    2. 动结构前必须先成功备份数据库；备份失败就拒绝迁移（宁可不动，也不能没备份就改）。
    3. 幂等：列已存在直接返回，不重复加列、不重复回填。
    4. 备份用 sqlite3 的在线备份 API，而不是复制文件——WAL 模式下文件复制可能拿到不一致的快照。

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
    """从引擎 URL 反推 SQLite 文件路径；内存库返回 None"""
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
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return [row[1] for row in rows]


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
    """动结构前备份一次；数据库文件不存在（内存库等）就跳过"""
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
    """
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