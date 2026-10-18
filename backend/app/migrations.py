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
) -> dict:
    """确保 table 具备 specs 里声明的列（缺失的用 ALTER TABLE ADD COLUMN 补上）。

    返回 {"added_columns": [...], "backed_up": str | None}
    只追加列：不改既有列类型、不删列、不动任何行；首次新增前先备份一次。
    幂等：列齐了直接返回，不备份也不改结构。
    """
    columns = _table_columns(engine, table)
    if not columns:
        # 表还不存在（全新库）：create_all 会直接按新模型建好，无需迁移
        return {"added_columns": [], "backed_up": None}

    missing = [name for name in specs if name not in columns]
    if not missing:
        return {"added_columns": [], "backed_up": None}

    backed_up = _backup_once(engine, backup_dir)
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