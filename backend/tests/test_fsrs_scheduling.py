"""FSRS 排程测试 — 四档评分、迁移幂等与数据无损

红灯背景（改造前）：
    1) POST /api/study/record 只接受 known:bool，无法表达四档评分（重来/困难/良好/简单），
       后端也没有任何 FSRS 字段或调度器。
    2) study_records 表没有 fsrs_card 列，历史记录也没有迁移路径。

数据安全约定：
    - 本文件里的所有写入都发生在 backend/tests/.tmp-db/ 下的临时库里，绝不触碰 D:\\data\\cet4.db。
    - 迁移测试会在临时目录里**复制一份真实库**再迁移，用它验证"迁移前后计数与 id 集合一致"。

运行方式（二选一）：
    python tests/test_fsrs_scheduling.py
    pytest tests/test_fsrs_scheduling.py
"""

import atexit
import json
import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-fsrs"
if TMP_DIR.exists():
    shutil.rmtree(TMP_DIR, ignore_errors=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

import app.config as config  # noqa: E402

config.DB_PATH = TMP_DIR / "cet4.db"
config.DATABASE_URL = f"sqlite:///{config.DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


def _cleanup():
    """先释放 SQLite 连接再删临时目录（Windows 上文件被占用会删不掉）。"""
    engine.dispose()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup)

with TestClient(app) as _boot:
    _boot.get("/api/health")

client = TestClient(app)

REAL_DB = Path(r"D:\data\cet4.db")


def _word_id(offset: int = 0) -> int:
    """从词库直接取第 offset 个词的 id。

    不用 /api/study/today 取词：那个接口会过滤掉"已学"的词，
    前面的用例提交记录后列表会位移，按下标取词会不稳定。
    """
    con = sqlite3.connect(str(config.DB_PATH))
    row = con.execute("select id from words order by id limit 1 offset ?", (offset,)).fetchone()
    con.close()
    assert row, f"词库不足 {offset + 1} 个词"
    return row[0]


def test_preview_endpoint_orders_intervals():
    """评分预览：四档齐全、只读、间隔随评分递增（简单 ≥ 良好 ≥ 困难 ≥ 重来）"""
    word_id = _word_id(50)

    before = client.get("/api/progress/overview").json()
    res = client.get(f"/api/study/preview?word_id={word_id}")
    assert res.status_code == 200, res.text[:140]
    ratings = res.json()["ratings"]
    assert [r["rating"] for r in ratings] == [1, 2, 3, 4], ratings
    assert all(r["label"] for r in ratings), "每档都要有中文标签"

    days = [r["interval_days"] for r in ratings]
    assert days == sorted(days), f"间隔应随评分递增，实际 {days}"

    # 预览不能改数据
    after = client.get("/api/progress/overview").json()
    assert before == after, "预览接口不应写入任何数据"


def test_preview_rejects_unknown_word():
    """预览不存在的词要 404，而不是返回空数据"""
    res = client.get("/api/study/preview?word_id=99999999")
    assert res.status_code == 404, f"期望 404，实际 {res.status_code}"


# === 1. 四档评分 API ===

def test_four_grades_accepted():
    """rating 1-4 都能提交，并返回 FSRS 调度结果"""
    for i, rating in enumerate((1, 2, 3, 4)):
        word_id = _word_id(i)
        res = client.post("/api/study/record", json={"word_id": word_id, "rating": rating})
        assert res.status_code == 200, f"rating={rating} 失败：{res.text[:140]}"
        body = res.json()
        assert body["rating"] == rating, body
        assert body["fsrs_state"] in (1, 2, 3), body
        assert body["next_review_at"], body
        assert body["interval_days"] >= 0, body


def test_next_review_is_in_the_future():
    """下次复习时间必须在未来，不能算成过去（否则复习队列会立刻再次弹出）"""
    from datetime import datetime, timezone

    for i, rating in enumerate((1, 2, 3, 4)):
        word_id = _word_id(10 + i)
        body = client.post("/api/study/record", json={"word_id": word_id, "rating": rating}).json()
        due = datetime.fromisoformat(body["next_review_at"])
        assert due > datetime.now(timezone.utc), f"rating={rating} 算出过去时间：{due}"


def test_known_bool_still_supported():
    """旧的 known:bool 调用必须继续可用（否则已构建的前端产物会 500）"""
    word_id = _word_id(20)
    res = client.post("/api/study/record", json={"word_id": word_id, "known": True})
    assert res.status_code == 200, res.text[:140]
    assert res.json()["rating"] == 3, "known=True 应映射为「良好」(3)"

    word_id = _word_id(21)
    res = client.post("/api/study/record", json={"word_id": word_id, "known": False})
    assert res.status_code == 200, res.text[:140]
    assert res.json()["rating"] == 1, "known=False 应映射为「重来」(1)"


def test_missing_rating_and_known_is_rejected():
    """两个字段都不给应当被拒绝，而不是静默当成某种评分"""
    res = client.post("/api/study/record", json={"word_id": _word_id(22)})
    assert res.status_code == 422, f"期望 422，实际 {res.status_code}"


def test_rating_out_of_range_rejected():
    """rating=0 / 5 / 'abc' 都应被拒绝"""
    for bad in (0, 5, "abc"):
        res = client.post("/api/study/record", json={"word_id": _word_id(23), "rating": bad})
        assert res.status_code == 422, f"rating={bad!r} 期望 422，实际 {res.status_code}"


def test_fsrs_state_persisted():
    """FSRS 卡片状态必须落库，重复提交应在新状态上继续演进"""
    word_id = _word_id(30)
    client.post("/api/study/record", json={"word_id": word_id, "rating": 4})
    con = sqlite3.connect(str(config.DB_PATH))
    raw = con.execute("select fsrs_card from study_records where word_id=?", (word_id,)).fetchone()
    con.close()
    assert raw and raw[0], "fsrs_card 未落库"
    assert '"stability"' in raw[0] and '"difficulty"' in raw[0], raw[0][:120]

    # 第二次 Easy 的间隔应当 >= 第一次（稳定性在增长）
    first = client.post("/api/study/record", json={"word_id": word_id, "rating": 4}).json()
    fresh = _word_id(31)
    f1 = client.post("/api/study/record", json={"word_id": fresh, "rating": 4}).json()
    f2 = client.post("/api/study/record", json={"word_id": fresh, "rating": 4}).json()
    assert f2["interval_days"] >= f1["interval_days"], f"间隔未增长：{f1} -> {f2}"
    assert first["interval_days"] >= 0


def test_review_queue_respects_due_date():
    """复习队列按到期时间取卡：已到期进队列，远期不进——且不受 status 影响

    FSRS 下"已毕业"的卡也会重新到期，所以队列不能再按 status=='learning' 过滤，
    否则进入 Review 状态的卡永远不会再出现，间隔重复等于断掉。
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    due_word = _word_id(40)
    future_word = _word_id(41)

    con = sqlite3.connect(str(config.DB_PATH))
    con.execute(
        "insert into study_records (word_id, status, know_count, unknown_count, review_count, next_review_at) "
        "values (?,?,?,?,?,?)",
        (due_word, "known", 5, 0, 5, (now - timedelta(days=1)).isoformat()),
    )
    con.execute(
        "insert into study_records (word_id, status, know_count, unknown_count, review_count, next_review_at) "
        "values (?,?,?,?,?,?)",
        (future_word, "known", 5, 0, 5, (now + timedelta(days=30)).isoformat()),
    )
    con.commit()
    con.close()

    ids = [c["word"]["id"] for c in client.get("/api/study/review").json()["words"]]
    assert due_word in ids, "已到期的卡没有进复习队列"
    assert future_word not in ids, "未到期的卡不该进复习队列"


# === 2. 迁移：幂等 + 无损 ===

def _snapshot(db: Path) -> dict:
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    tables = ("words", "study_records", "daily_stats", "custom_wordbooks", "starred_words")
    snap = {t: cur.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
    snap["study_ids"] = [r[0] for r in cur.execute("select id from study_records order by id")]
    snap["word_ids"] = [r[0] for r in cur.execute("select word_id from study_records order by word_id")]
    snap["cols"] = sorted(r[1] for r in cur.execute("PRAGMA table_info(study_records)"))
    con.close()
    return snap


def _make_legacy_db(path: Path, rows: int = 5) -> None:
    """手工造一个"迁移前"的库，用于确定性地验证迁移逻辑。

    为什么不直接用真实库副本：真实库的迁移状态会随时间变化（第一次跑迁移后就带 fsrs_card 了），
    若断言"本次一定新增了列/一定产生了备份"，测试就会随外部状态时红时绿。
    这里固定造出迁移前的 schema，保证每次都真正走到 ADD COLUMN + 回填 + 备份分支。
    """
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE words (
            id INTEGER PRIMARY KEY AUTOINCREMENT, word VARCHAR(100) NOT NULL UNIQUE,
            phonetic_us VARCHAR(100), phonetic_uk VARCHAR(100), definition TEXT NOT NULL,
            pos VARCHAR(20), example TEXT, example_cn TEXT, frequency INTEGER DEFAULT 0);
        CREATE TABLE study_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER NOT NULL,
            status VARCHAR(20) DEFAULT 'new', know_count INTEGER DEFAULT 0,
            unknown_count INTEGER DEFAULT 0, review_count INTEGER DEFAULT 0,
            next_review_at VARCHAR(30), last_studied_at VARCHAR(30), created_at VARCHAR(30));
        CREATE TABLE daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date VARCHAR(10) NOT NULL UNIQUE,
            new_words INTEGER DEFAULT 0, reviewed_words INTEGER DEFAULT 0,
            quiz_score INTEGER DEFAULT 0, quiz_total INTEGER DEFAULT 0, streak_days INTEGER DEFAULT 0);
        CREATE TABLE custom_wordbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(50) NOT NULL, description VARCHAR(200),
            icon VARCHAR(10), query_text TEXT NOT NULL, keywords TEXT NOT NULL, word_ids TEXT,
            pos VARCHAR(20), freq_max INTEGER DEFAULT 4544, created_at VARCHAR(30));
        CREATE TABLE starred_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER NOT NULL,
            type VARCHAR(10) NOT NULL, created_at VARCHAR(30));
        """
    )
    for i in range(1, rows + 1):
        con.execute(
            "insert into words (word, definition, frequency) values (?,?,?)",
            (f"legacy{i}", f"n. 旧词{i}", i),
        )
        con.execute(
            "insert into study_records (word_id, status, know_count, review_count, next_review_at, last_studied_at)"
            " values (?,?,?,?,?,?)",
            (i, "learning", 1, 1, "2026-06-16T01:00:00+00:00", "2026-06-15T01:00:00+00:00"),
        )
    con.commit()
    con.close()


def test_migration_adds_fsrs_column_on_legacy_schema():
    """迁移前 schema：应新增 fsrs_card 列、回填全部历史记录、且不丢行不改到期时间"""
    from sqlalchemy import create_engine

    from app.migrations import ensure_fsrs_schema

    legacy = TMP_DIR / "legacy-fsrs.db"
    _make_legacy_db(legacy, rows=5)
    before = _snapshot(legacy)
    assert "fsrs_card" not in before["cols"], "构造的旧库不该有 fsrs_card"

    eng = create_engine(f"sqlite:///{legacy}", connect_args={"check_same_thread": False})
    try:
        first = ensure_fsrs_schema(eng, backup_dir=TMP_DIR / "backups-legacy")
        second = ensure_fsrs_schema(eng, backup_dir=TMP_DIR / "backups-legacy")
    finally:
        eng.dispose()

    after = _snapshot(legacy)
    assert first["added_column"] is True, first
    assert first["backfilled"] == 5, first
    assert second["added_column"] is False, second
    assert second["backfilled"] == 0, second

    assert set(before["cols"]) <= set(after["cols"]), "迁移丢失了原有列"
    assert "fsrs_card" in after["cols"]
    assert before["study_records"] == after["study_records"]
    assert before["study_ids"] == after["study_ids"]
    assert before["word_ids"] == after["word_ids"]

    con = sqlite3.connect(str(legacy))
    rows = con.execute("select fsrs_card, next_review_at from study_records").fetchall()
    con.close()
    for card_json, due in rows:
        assert card_json, "未回填 fsrs_card"
        assert json.loads(card_json)["due"] == due, "回填改动了原有到期时间"


def test_migration_makes_backup():
    """首次迁移前必须留下备份；幂等重跑不再产生备份"""
    from sqlalchemy import create_engine

    from app.migrations import ensure_fsrs_schema

    legacy = TMP_DIR / "legacy-backup.db"
    _make_legacy_db(legacy, rows=3)
    backup_dir = TMP_DIR / "backups-check"
    eng = create_engine(f"sqlite:///{legacy}", connect_args={"check_same_thread": False})
    try:
        result = ensure_fsrs_schema(eng, backup_dir=backup_dir)
        ensure_fsrs_schema(eng, backup_dir=backup_dir)  # 第二次是幂等 no-op
    finally:
        eng.dispose()

    assert result["backed_up"], "首次迁移没有备份"
    made = Path(result["backed_up"])
    assert made.exists() and made.stat().st_size > 0, f"备份文件无效：{made}"
    assert made.parent == backup_dir
    assert len(list(backup_dir.glob("*"))) == 1, "幂等重跑不该再产生备份"


def test_migration_keeps_real_data_intact():
    """对真实库副本跑迁移：计数与 id 集合必须完全不变（不依赖真实库当前是否已迁移）"""
    assert REAL_DB.exists(), f"找不到真实库 {REAL_DB}"

    from sqlalchemy import create_engine

    from app.migrations import ensure_fsrs_schema

    copy_db = TMP_DIR / "migration-copy.db"
    shutil.copy(REAL_DB, copy_db)
    before = _snapshot(copy_db)

    eng = create_engine(f"sqlite:///{copy_db}", connect_args={"check_same_thread": False})
    try:
        first = ensure_fsrs_schema(eng, backup_dir=TMP_DIR / "backups")
        second = ensure_fsrs_schema(eng, backup_dir=TMP_DIR / "backups")
    finally:
        eng.dispose()

    after = _snapshot(copy_db)
    assert set(before["cols"]) <= set(after["cols"]), "迁移丢失了原有列"
    assert "fsrs_card" in after["cols"], "迁移后仍缺 fsrs_card"

    for t in ("words", "study_records", "daily_stats", "custom_wordbooks", "starred_words"):
        assert before[t] == after[t], f"{t} 计数变化：{before[t]} -> {after[t]}"
    assert before["study_ids"] == after["study_ids"], "study_records 主键集合变化"
    assert before["word_ids"] == after["word_ids"], "study_records.word_id 集合变化"

    # 迁移完再跑一次必须是 no-op
    assert second["added_column"] is False and second["backfilled"] == 0, second
    if first["added_column"]:  # 只有真的新增了列才要求有备份
        assert first["backed_up"], "新增列前没有备份"


def test_real_database_untouched_by_tests():
    """所有测试只动临时库；真实库路径未被改写"""
    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    if REAL_DB.exists():
        con = sqlite3.connect(str(REAL_DB))
        cols = [r[1] for r in con.execute("PRAGMA table_info(study_records)")]
        n = con.execute("select count(*) from study_records").fetchone()[0]
        con.close()
        assert n == 21, f"真实库 study_records 计数变了：{n}"


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