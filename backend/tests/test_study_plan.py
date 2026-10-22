"""学习计划测试 — 用户级计划、预测口径、迁移安全

覆盖：
    1) 创建 / 读取 / 更新计划
    2) 未登录按现有认证契约被拒（401）
    3) A 不能读或改 B 的计划
    4) 不同目标与词书对应正确的词汇总量（与 /api/wordbooks 口径一致）
    5) 预计完成天数与目标日期边界
    6) 无计划 / 目标日期已过 / 词书已学完
    7) FSRS 到期负担使用**真实用户级**记录，且限定在所选词书
    8) 迁移重复执行安全、不影响既有数据（含真实库副本）

数据安全：写入只发生在 backend/tests/.tmp-plan/；真实库只在"复制一份"后验证迁移。

运行：python tests/test_study_plan.py
"""

import atexit
import json
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-plan"
if TMP_DIR.exists():
    shutil.rmtree(TMP_DIR, ignore_errors=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

import app.config as config  # noqa: E402

config.DB_PATH = TMP_DIR / "cet4.db"
config.DATABASE_URL = f"sqlite:///{config.DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from testkit import AuthClient, csrf_headers  # noqa: E402

REAL_DB = Path(r"D:\data\cet4.db")


def _cleanup():
    engine.dispose()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup)

with TestClient(app) as _boot:
    _boot.get("/api/health")

client = AuthClient(app)  # 默认已登录；写请求自动带 CSRF


def _db() -> sqlite3.Connection:
    return sqlite3.connect(str(config.DB_PATH))


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _uid(c: AuthClient) -> int:
    return c.get("/api/auth/me").json()["id"]


def _word_ids(n: int, start: int = 0) -> list[int]:
    con = _db()
    rows = con.execute("select id from words order by id limit ? offset ?", (n, start)).fetchall()
    con.close()
    return [r[0] for r in rows]


def _insert_custom_book(user_id: int, name: str, word_ids: list[int]) -> str:
    """直接插一本只含指定词的自定义书，便于构造确定性的"已学完"场景"""
    con = _db()
    cur = con.execute(
        "insert into custom_wordbooks (name, description, icon, query_text, keywords, word_ids, pos, freq_max, user_id) "
        "values (?,?,?,?,?,?,?,?,?)",
        (name, "test", "✨", "测试", json.dumps(["x"]), json.dumps(word_ids), "", 4544, user_id),
    )
    con.commit()
    book_id = cur.lastrowid
    con.close()
    return f"custom_{book_id}"


# === 1. 创建 / 读取 / 更新 ===

def test_plan_create_read_update():
    c = AuthClient(app)

    # 尚未设置：稳定空状态
    empty = c.get("/api/plan").json()
    assert empty["has_plan"] is False and empty["plan"] is None, empty

    # 创建
    res = c.put(
        "/api/plan",
        json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 30, "target_date": "2027-06-01"},
    )
    assert res.status_code == 200, res.text[:200]
    created = res.json()["plan"]
    assert created["goal_type"] == "cet4"
    assert created["wordbook_key"] == "exam_cet4"
    assert created["daily_new_words"] == 30
    assert created["target_date"] == "2027-06-01"
    assert created["goal_name"]

    got = c.get("/api/plan").json()
    assert got["has_plan"] is True and got["plan"]["wordbook_key"] == "exam_cet4"

    # 更新（同一用户仍只有一份计划）
    res = c.put(
        "/api/plan",
        json={"goal_type": "ielts", "wordbook_key": "exam_ielts", "daily_new_words": 50, "target_date": None},
    )
    assert res.status_code == 200
    updated = res.json()["plan"]
    assert updated["goal_type"] == "ielts" and updated["target_date"] is None
    assert updated["created_at"] == created["created_at"], "更新不应改变 created_at"

    con = _db()
    rows = con.execute("select count(*) from study_plans where user_id = ?", (_uid(c),)).fetchone()[0]
    con.close()
    assert rows == 1, f"每个用户应只有一份计划，实际 {rows}"


def test_plan_validation():
    c = AuthClient(app)
    bad_payloads = [
        {"goal_type": "not-a-goal", "wordbook_key": "exam_cet4", "daily_new_words": 20},
        {"goal_type": "cet4", "wordbook_key": "no_such_book", "daily_new_words": 20},
        {"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 0},
        {"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 999},
        {"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20, "target_date": "2027/06/01"},
    ]
    for payload in bad_payloads:
        res = c.put("/api/plan", json=payload)
        assert res.status_code == 422, f"{payload} 期望 422，实际 {res.status_code} {res.text[:120]}"


def test_unknown_goal_or_wordbook_does_not_write():
    c = AuthClient(app)
    c.put("/api/plan", json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20})
    before = c.get("/api/plan").json()["plan"]

    c.put("/api/plan", json={"goal_type": "cet4", "wordbook_key": "ghost_book", "daily_new_words": 99})
    after = c.get("/api/plan").json()["plan"]
    assert after == before, "校验失败的请求不该改动已有计划"


# === 2. 未登录 ===

def test_unauthenticated_rejected():
    anon = TestClient(app)
    anon.get("/api/auth/csrf")
    headers = csrf_headers(anon)
    assert anon.get("/api/plan").status_code == 401
    assert anon.get("/api/plan/forecast").status_code == 401
    res = anon.put(
        "/api/plan",
        json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20},
        headers=headers,
    )
    assert res.status_code == 401, res.text[:120]


# === 3. 用户隔离 ===

def test_plan_is_isolated_between_users():
    a = AuthClient(app)
    b = AuthClient(app)

    a.put("/api/plan", json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20})
    assert b.get("/api/plan").json()["has_plan"] is False, "B 不该看到 A 的计划"

    b.put("/api/plan", json={"goal_type": "toefl", "wordbook_key": "exam_toefl", "daily_new_words": 10})
    assert a.get("/api/plan").json()["plan"]["goal_type"] == "cet4", "B 的计划不该覆盖 A 的"
    assert b.get("/api/plan").json()["plan"]["goal_type"] == "toefl"

    # 预测也必须各算各的
    a.put("/api/plan", json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20})
    fa = a.get("/api/plan/forecast").json()
    fb = b.get("/api/plan/forecast").json()
    assert fa["wordbook"]["key"] == "exam_cet4" and fb["wordbook"]["key"] == "exam_toefl"
    assert fa["wordbook"]["total_words"] != fb["wordbook"]["total_words"]


# === 4. 目标与词书 → 词汇总量 ===

def test_goal_defaults_and_totals_match_wordbooks():
    c = AuthClient(app)
    options = c.get("/api/plan/options").json()
    goals = {g["goal_type"]: g for g in options["goals"]}
    for required in ("cet4", "cet6", "kaoyan", "ielts", "toefl", "general"):
        assert required in goals, f"缺少学习目标 {required}"

    # 词书总量的唯一权威来源是 /api/wordbooks（预设书公共可查）
    books = {b["id"]: b["word_count"] for b in c.get("/api/wordbooks").json()}

    for goal, meta in goals.items():
        default_book = meta["default_wordbook"]
        assert default_book in books, f"{goal} 的默认词书 {default_book} 不在词书清单里"

        # 不传 wordbook_key 时应当落到该目标的默认词书
        c.put("/api/plan", json={"goal_type": goal, "daily_new_words": 20})
        forecast = c.get("/api/plan/forecast").json()
        assert forecast["plan"]["wordbook_key"] == default_book, f"{goal} 未落到默认词书"
        assert forecast["wordbook"]["total_words"] == books[default_book], (
            f"{goal}/{default_book} 词数应为 {books[default_book]}，实际 {forecast['wordbook']['total_words']}"
        )

    # 全词库与考纲书应当有明显区分（防止 filter 失效导致都等于 4544）
    assert books["all"] == 4544
    assert books["exam_cet4"] < books["all"]


# === 5/6. 预计完成天数、目标日期边界、边界场景 ===

def test_days_and_target_boundaries():
    c = AuthClient(app)
    c.put("/api/plan", json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20})
    f = c.get("/api/plan/forecast").json()

    remaining = f["remaining_new_words"]
    assert remaining == f["wordbook"]["total_words"] - f["learned_words"] >= 0
    expected_days = -(-remaining // 20)  # ceil
    assert f["days_to_finish"] == expected_days, f"{f['days_to_finish']} != {expected_days}"
    assert f["estimated_finish_date"] == (_today() + timedelta(days=expected_days)).isoformat()
    assert f["target"] is None, "没设目标日期时不该有 target"
    assert "不构成保证" in f["estimate_note"], "估算必须带免责说明"

    # 目标日太近 → 不可行
    c.put(
        "/api/plan",
        json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20,
              "target_date": (_today() + timedelta(days=1)).isoformat()},
    )
    t = c.get("/api/plan/forecast").json()["target"]
    assert t["feasible"] is False and t["days_available"] == 1, t
    assert "剩余" in t["reason"]

    # 目标日很远 → 可行
    c.put(
        "/api/plan",
        json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20,
              "target_date": (_today() + timedelta(days=5000)).isoformat()},
    )
    assert c.get("/api/plan/forecast").json()["target"]["feasible"] is True

    # 目标日已过 → 不可行且原因明确
    c.put(
        "/api/plan",
        json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": 20,
              "target_date": (_today() - timedelta(days=3)).isoformat()},
    )
    t = c.get("/api/plan/forecast").json()["target"]
    assert t["feasible"] is False and t["days_available"] == -3, t
    assert t["reason"] == "目标日期已过", t


def test_forecast_without_plan_is_stable():
    c = AuthClient(app)
    f = c.get("/api/plan/forecast").json()
    assert f["has_plan"] is False
    for key in ("plan", "wordbook", "remaining_new_words", "days_to_finish", "estimated_finish_date", "target", "due"):
        assert f[key] is None, f"{key} 应为 null：{f[key]}"
    assert f["learned_words"] == 0
    assert f["estimate_note"]


def test_wordbook_finished_case():
    """词书学完：剩余 0、预计完成 0 天、目标可行且原因是「已学完」"""
    c = AuthClient(app)
    uid = _uid(c)
    words = _word_ids(3, start=2000)
    book = _insert_custom_book(uid, "三个词的小书", words)

    c.put("/api/plan", json={"goal_type": "general", "wordbook_key": book, "daily_new_words": 10,
                             "target_date": (_today() + timedelta(days=5)).isoformat()})
    f = c.get("/api/plan/forecast").json()
    assert f["wordbook"]["total_words"] == 3, f
    assert f["remaining_new_words"] == 3

    for wid in words:
        assert c.post("/api/study/record", json={"word_id": wid, "rating": 3}).status_code == 200

    f = c.get("/api/plan/forecast").json()
    assert f["learned_words"] == 3 and f["remaining_new_words"] == 0, f
    assert f["days_to_finish"] == 0 and f["estimated_finish_date"] == _today().isoformat()
    assert f["target"]["feasible"] is True and f["target"]["reason"] == "该词书已学完"


# === 7. FSRS 到期负担 ===

def test_due_burden_uses_real_user_records_scoped_to_wordbook():
    a = AuthClient(app)
    b = AuthClient(app)
    uid_a, uid_b = _uid(a), _uid(b)

    words = _word_ids(4, start=3000)
    book = _insert_custom_book(uid_a, "负担测试书", words[:2])  # 只有前两个词在词书范围内
    a.put("/api/plan", json={"goal_type": "cet4", "wordbook_key": book, "daily_new_words": 20})
    b.put("/api/plan", json={"goal_type": "toefl", "wordbook_key": "exam_toefl", "daily_new_words": 20})

    now = datetime.now(timezone.utc)
    today = _today()
    con = _db()
    # A：一个已过期、一个今天到期、一个 2 天后到期；另外插一个"不在词书范围内"的到期词
    rows = [
        (words[0], uid_a, (now - timedelta(days=2)).isoformat()),
        (words[1], uid_a, now.isoformat()),
        (words[2], uid_a, (now + timedelta(days=2)).isoformat()),  # 不在词书里，不该计入
    ]
    for word_id, user_id, due in rows:
        con.execute(
            "insert into study_records (word_id, user_id, status, know_count, review_count, next_review_at, last_studied_at)"
            " values (?,?,?,?,?,?,?)",
            (word_id, user_id, "learning", 1, 1, due, now.isoformat()),
        )
    # B：同样造一个到期记录，验证不会串到 A
    con.execute(
        "insert into study_records (word_id, user_id, status, know_count, review_count, next_review_at, last_studied_at)"
        " values (?,?,?,?,?,?,?)",
        (words[3], uid_b, "learning", 1, 1, (now - timedelta(days=5)).isoformat(), now.isoformat()),
    )
    con.commit()
    con.close()

    fa = a.get("/api/plan/forecast").json()
    due = fa["due"]
    assert due["scope"] == "wordbook"
    assert due["overdue"] == 1, f"A 过期数应为 1（另一个过期词不在词书内）：{due}"
    assert due["today"] == 1, f"A 今日到期应为 1：{due}"
    assert due["total_pending"] == 2, due
    assert len(due["next_7_days"]) == 7
    day2 = (today + timedelta(days=2)).isoformat()
    assert next(d for d in due["next_7_days"] if d["date"] == day2)["count"] == 0, "词书外的到期词不该计入"
    # 首日桶含逾期（今天实际要还的债）；词书外那个 2 天后到期的词不进任何桶
    assert due["next_7_days"][0]["count"] == 2, due["next_7_days"][0]
    assert sum(d["count"] for d in due["next_7_days"]) == 2, due

    fb = b.get("/api/plan/forecast").json()
    assert fb["due"]["overdue"] == 0, f"B 不该看到 A 的到期记录：{fb['due']}"
    assert fb["due"]["total_pending"] == 0, fb["due"]


# === 8. 迁移安全 ===

def _snapshot(db: Path) -> dict:
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
    counts = {
        t: cur.execute(f'select count(*) from "{t}"').fetchone()[0]
        for t in ("words", "study_records", "daily_stats", "custom_wordbooks", "starred_words")
        if t in tables
    }
    cols = (
        sorted(r[1] for r in cur.execute("PRAGMA table_info(study_plans)")) if "study_plans" in tables else []
    )
    con.close()
    return {"counts": counts, "has_table": "study_plans" in tables, "cols": cols}


def test_daily_new_words_range_is_not_narrowed_to_presets():
    """合法范围 1-200 必须真的可用

    防止"为了对齐前端"把后端范围悄悄收窄成 10/20/30/50——那样前端一致了，
    但接口能力被削弱，属于用掩盖代替修复。
    """
    c = AuthClient(app)
    for n in (1, 25, 200):
        res = c.put(
            "/api/plan",
            json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": n},
        )
        assert res.status_code == 200, f"{n} 应被接受：{res.text[:120]}"
        assert res.json()["plan"]["daily_new_words"] == n
        assert c.get("/api/plan").json()["plan"]["daily_new_words"] == n, f"{n} 没有正确往返"

        forecast = c.get("/api/plan/forecast").json()
        assert forecast["days_to_finish"] == -(-forecast["remaining_new_words"] // n), (
            f"每日 {n} 时预计天数应随之变化"
        )

    for n in (0, -1, 201):
        res = c.put(
            "/api/plan",
            json={"goal_type": "cet4", "wordbook_key": "exam_cet4", "daily_new_words": n},
        )
        assert res.status_code == 422, f"{n} 应被拒绝，实际 {res.status_code}"


def test_migration_creates_table_idempotently_with_backup():
    from sqlalchemy import create_engine

    from app.migrations import ensure_study_plan_schema

    legacy = TMP_DIR / "legacy-plan.db"
    if legacy.exists():
        legacy.unlink()
    con = sqlite3.connect(str(legacy))
    con.executescript(
        """
        CREATE TABLE words (id INTEGER PRIMARY KEY AUTOINCREMENT, word VARCHAR(100) NOT NULL UNIQUE,
            phonetic_us VARCHAR(100), phonetic_uk VARCHAR(100), definition TEXT NOT NULL,
            pos VARCHAR(20), example TEXT, example_cn TEXT, frequency INTEGER DEFAULT 0);
        CREATE TABLE study_records (id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER NOT NULL,
            user_id INTEGER, status VARCHAR(20), know_count INTEGER DEFAULT 0, unknown_count INTEGER DEFAULT 0,
            review_count INTEGER DEFAULT 0, next_review_at VARCHAR(30), last_studied_at VARCHAR(30), created_at VARCHAR(30));
        CREATE TABLE daily_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, date VARCHAR(10) NOT NULL,
            user_id INTEGER, new_words INTEGER DEFAULT 0, reviewed_words INTEGER DEFAULT 0,
            quiz_score INTEGER DEFAULT 0, quiz_total INTEGER DEFAULT 0, streak_days INTEGER DEFAULT 0);
        CREATE TABLE custom_wordbooks (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(50) NOT NULL,
            user_id INTEGER, description VARCHAR(200), icon VARCHAR(10), query_text TEXT NOT NULL,
            keywords TEXT NOT NULL, word_ids TEXT, pos VARCHAR(20), freq_max INTEGER DEFAULT 4544, created_at VARCHAR(30));
        CREATE TABLE starred_words (id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER NOT NULL,
            user_id INTEGER, type VARCHAR(10) NOT NULL, created_at VARCHAR(30));
        """
    )
    con.execute("insert into words (word, definition, frequency) values ('legacy1','n. 旧词',1)")
    con.execute("insert into study_records (word_id, user_id, status) values (1, NULL, 'learning')")
    con.commit()
    con.close()

    before = _snapshot(legacy)
    assert before["has_table"] is False

    eng = create_engine(f"sqlite:///{legacy}", connect_args={"check_same_thread": False})
    try:
        first = ensure_study_plan_schema(eng, backup_dir=TMP_DIR / "backups")
        second = ensure_study_plan_schema(eng, backup_dir=TMP_DIR / "backups")
    finally:
        eng.dispose()

    after = _snapshot(legacy)
    assert first["created_table"] is True, first
    assert second["created_table"] is False, "重复执行应当是 no-op"
    assert after["has_table"] is True
    assert set(after["cols"]) == {
        "id", "user_id", "goal_type", "wordbook_key", "target_date", "daily_new_words", "created_at", "updated_at",
    }, after["cols"]
    assert before["counts"] == after["counts"], "迁移不该改动既有数据"
    assert first["backed_up"] and Path(first["backed_up"]).exists(), "建表前应有备份"
    assert len(list((TMP_DIR / "backups").glob("*"))) == 1, "幂等重跑不该再产生备份"

    # user_id 唯一：同一用户插两次应被拒绝
    con = sqlite3.connect(str(legacy))
    con.execute("insert into study_plans (user_id, goal_type, wordbook_key, daily_new_words) values (1,'cet4','exam_cet4',20)")
    con.commit()
    try:
        con.execute("insert into study_plans (user_id, goal_type, wordbook_key, daily_new_words) values (1,'cet6','exam_cet6',20)")
        con.commit()
        con.close()
        raise AssertionError("同一用户插入第二份计划竟然成功：唯一约束没生效")
    except sqlite3.IntegrityError:
        con.rollback()
        con.close()


def test_migration_on_real_copy_keeps_data():
    """对真实库副本建表：表建好、既有行数不变（本轮不动真实库本身）"""
    assert REAL_DB.exists(), f"找不到真实库 {REAL_DB}"
    from sqlalchemy import create_engine

    from app.migrations import ensure_study_plan_schema

    copy_db = TMP_DIR / "real-copy.db"
    shutil.copy(REAL_DB, copy_db)
    before = _snapshot(copy_db)

    eng = create_engine(f"sqlite:///{copy_db}", connect_args={"check_same_thread": False})
    try:
        result = ensure_study_plan_schema(eng, backup_dir=TMP_DIR / "backups-real")
    finally:
        eng.dispose()

    after = _snapshot(copy_db)
    assert after["has_table"] is True, "副本上应建出 study_plans"
    assert before["counts"] == after["counts"], f"行数变化：{before['counts']} -> {after['counts']}"
    assert result["backed_up"] and Path(result["backed_up"]).exists(), "应产出备份，便于回退"


def test_real_database_untouched_by_tests():
    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    if REAL_DB.exists():
        con = sqlite3.connect(str(REAL_DB))
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        n = con.execute("select count(*) from study_records").fetchone()[0]
        con.close()
        assert "study_plans" not in tables, "测试不该在真实库里建表"
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