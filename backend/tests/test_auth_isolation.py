"""用户认证与数据隔离测试

覆盖：
    1) 注册 / 登录 / 取当前用户 / 退出
    2) 重复邮箱、错误密码、无效请求被拒；不泄露"邮箱是否已注册"
    3) 未登录不能访问受保护的个人接口
    4) 两个用户的学习记录、统计、收藏、错题、自定义词书完全隔离
    5) 越权：猜 ID / 换 ID 也读不到、删不掉别人的数据
    6) 公共词库与预设词书仍然可用
    7) 遗留数据（user_id 为 NULL）对任何用户都不可见
    8) 用户隔离迁移可重复执行、不丢原有数据

数据安全：所有写入都在 backend/tests/.tmp-auth/ 的临时库里；
         真实库只在"复制一份"之后用于迁移路径验证。

运行：python tests/test_auth_isolation.py
"""

import atexit
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-auth"
if TMP_DIR.exists():
    shutil.rmtree(TMP_DIR, ignore_errors=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

import app.config as config  # noqa: E402

config.DB_PATH = TMP_DIR / "cet4.db"
config.DATABASE_URL = f"sqlite:///{config.DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from testkit import AuthClient, PASSWORD, csrf_headers, fresh_email, login, register  # noqa: E402

REAL_DB = Path(r"D:\data\cet4.db")

# 受保护的个人接口：(方法, 路径, 请求体)
PROTECTED = [
    ("GET", "/api/study/today", None),
    ("GET", "/api/study/review", None),
    ("GET", "/api/study/dictation", None),
    ("GET", "/api/study/preview?word_id=16", None),
    ("POST", "/api/study/record", {"word_id": 16, "rating": 3}),
    ("GET", "/api/quiz/daily", None),
    ("POST", "/api/quiz/submit", {"answers": []}),
    ("GET", "/api/progress/overview", None),
    ("GET", "/api/progress/calendar", None),
    ("GET", "/api/starred", None),
    ("GET", "/api/starred/ids", None),
    ("POST", "/api/starred", {"word_id": 16, "type": "star"}),
    ("DELETE", "/api/starred/16?type=star", None),
    ("POST", "/api/wordbooks/ai-generate", {"query": "食物"}),
    ("DELETE", "/api/wordbooks/custom_1", None),
    ("POST", "/api/ai/mnemonic", {"word_id": 16}),
]


def _cleanup():
    engine.dispose()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup)

with TestClient(app) as _boot:
    _boot.get("/api/health")


def _db() -> sqlite3.Connection:
    return sqlite3.connect(str(config.DB_PATH))


def _word_id(offset: int = 0) -> int:
    con = _db()
    row = con.execute("select id from words order by id limit 1 offset ?", (offset,)).fetchone()
    con.close()
    assert row, "词库未导入"
    return row[0]


def _insert_custom_book(user_id: int | None, name: str) -> int:
    """直接插一行自定义词书（避免测试依赖 AI 接口）"""
    con = _db()
    cur = con.execute(
        "insert into custom_wordbooks (name, description, icon, query_text, keywords, word_ids, pos, freq_max, user_id) "
        "values (?,?,?,?,?,?,?,?,?)",
        (name, "test", "✨", "测试", json.dumps(["食物"]), json.dumps([1, 2, 3]), "", 4544, user_id),
    )
    con.commit()
    book_id = cur.lastrowid
    con.close()
    return book_id


# === 1. 注册 / 登录 / me / 退出 ===

def test_register_login_me_logout():
    c = TestClient(app)
    email = register(c)
    assert c.get("/api/auth/me").status_code == 200
    assert c.get("/api/auth/me").json()["email"] == email

    # 退出后会话失效
    res = c.post("/api/auth/logout", headers=csrf_headers(c))
    assert res.status_code == 200, res.text[:150]
    assert c.get("/api/auth/me").status_code == 401, "退出后不应再能取到当前用户"

    # 重新登录
    res = login(c, email)
    assert res.status_code == 200, res.text[:150]
    assert c.get("/api/auth/me").status_code == 200


def test_email_is_normalized():
    """大小写与首尾空格要规范化，避免同一邮箱注册出两个账号"""
    c = TestClient(app)
    email = fresh_email("norm")
    # 注册时故意写成大写并带空格；服务端应回传规范化后的邮箱
    assert register(c, email=f"  {email.upper()}  ") == email.lower()
    assert c.get("/api/auth/me").json()["email"] == email.lower()

    # 用同样大小写不同的邮箱再注册，必须冲突
    c2 = TestClient(app)
    res = c2.post(
        "/api/auth/register",
        json={"email": email.upper(), "password": PASSWORD},
        headers=csrf_headers(c2),
    )
    assert res.status_code == 409, res.text[:150]


def test_session_cookie_attributes():
    """会话 Cookie 必须 HttpOnly + Path=/ + SameSite；CSRF Cookie 需可被前端读取"""
    c = TestClient(app)
    c.get("/api/auth/csrf")
    res = c.post(
        "/api/auth/register",
        json={"email": fresh_email("cookie"), "password": PASSWORD},
        headers=csrf_headers(c),
    )
    assert res.status_code == 200
    raw = "; ".join(res.headers.get_list("set-cookie")).lower()
    assert "cet4_session=" in raw
    assert "httponly" in raw, f"会话 Cookie 必须 HttpOnly：{raw[:200]}"
    assert "path=/" in raw
    assert "samesite=lax" in raw
    assert "cet4_csrf=" in raw
    # CSRF 令牌要给前端 JS 读，所以不能 HttpOnly
    csrf_part = [p for p in res.headers.get_list("set-cookie") if p.lower().startswith("cet4_csrf=")]
    assert csrf_part and "httponly" not in csrf_part[0].lower(), "CSRF Cookie 不应是 HttpOnly"


def test_password_stored_as_argon2id():
    """库里只能有 Argon2id 哈希，且接口不返回 password_hash"""
    c = TestClient(app)
    email = register(c)
    con = _db()
    row = con.execute("select password_hash from users where email = ?", (email,)).fetchone()
    con.close()
    assert row, "用户没落库"
    assert row[0].startswith("$argon2id$"), f"不是 Argon2id 哈希：{row[0][:20]}"
    assert PASSWORD not in row[0], "密码明文出现在哈希里"

    me = c.get("/api/auth/me").json()
    assert "password_hash" not in me and "password" not in me


# === 2. 非法请求 ===

def test_duplicate_email_rejected():
    c = TestClient(app)
    email = register(c)
    c2 = TestClient(app)
    res = c2.post("/api/auth/register", json={"email": email, "password": PASSWORD}, headers=csrf_headers(c2))
    assert res.status_code == 409


def test_invalid_payloads_rejected():
    c = TestClient(app)
    headers = csrf_headers(c)
    bad_bodies = [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": fresh_email(), "password": "short"},
        {"email": "", "password": PASSWORD},
    ]
    for body in bad_bodies:
        res = c.post("/api/auth/register", json=body, headers=headers)
        assert res.status_code == 422, f"{body} 期望 422，实际 {res.status_code}"


def test_wrong_password_rejected():
    c = TestClient(app)
    email = register(c)
    c2 = TestClient(app)
    res = login(c2, email, "wrong-password-123")
    assert res.status_code == 401
    assert c2.get("/api/auth/me").status_code == 401, "密码错误不该签发会话"


def test_unknown_email_does_not_leak():
    """不存在的邮箱与密码错误要返回同样的信息（防邮箱枚举）"""
    c = TestClient(app)
    res_unknown = login(c, fresh_email("nobody"), "whatever-123")
    c2 = TestClient(app)
    email = register(c2)
    res_wrong = login(c, email, "whatever-123")
    assert res_unknown.status_code == res_wrong.status_code == 401
    assert res_unknown.json()["detail"] == res_wrong.json()["detail"]


# === 3. 未登录访问受保护接口 ===

def test_unauthenticated_cannot_access_personal_endpoints():
    c = TestClient(app)
    c.get("/api/auth/csrf")  # 只领 CSRF，不登录
    headers = csrf_headers(c)
    for method, path, body in PROTECTED:
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        res = c.request(method, path, **kwargs)
        assert res.status_code == 401, f"{method} {path} 未登录应 401，实际 {res.status_code}"


def test_words_init_is_not_public():
    """/api/words/init 这类写接口不得对公众开放"""
    c = TestClient(app)
    c.get("/api/auth/csrf")
    res = c.post("/api/words/init", headers=csrf_headers(c))
    assert res.status_code == 403, f"未配置 ADMIN_TOKEN 时应 403，实际 {res.status_code}"

    # 登录用户同样不能调用（它不是个人接口，而是管理接口）
    a = AuthClient(app)
    assert a.post("/api/words/init").status_code == 403


def test_csrf_required_for_writes():
    """带会话但缺 CSRF 头的写请求必须被拒"""
    a = AuthClient(app)
    res = a.raw.post("/api/starred", json={"word_id": _word_id(0), "type": "star"})
    assert res.status_code == 403, f"缺 CSRF 应 403，实际 {res.status_code}"


# === 4/5. 两个用户之间的隔离与越权 ===

def test_two_users_fully_isolated():
    a = AuthClient(app)
    b = AuthClient(app)

    # 用"该用户今日新词里的第一个词"，保证它落在后面带 limit 的查询窗口内，结果可确定
    word_studied = a.get("/api/study/today?wordbook=all&limit=1").json()["words"][0]["word"]["id"]
    word_starred = _word_id(301)

    # A 学习 + 收藏
    assert a.post("/api/study/record", json={"word_id": word_studied, "rating": 3}).status_code == 200
    assert a.post("/api/starred", json={"word_id": word_starred, "type": "star"}).status_code == 200

    # B 什么都没做
    a_over = a.get("/api/progress/overview").json()
    b_over = b.get("/api/progress/overview").json()
    assert a_over["learned_words"] >= 1
    assert b_over["learned_words"] == 0, f"B 不该看到 A 的学习记录：{b_over}"
    assert a_over["today_new"] == 1 and b_over["today_new"] == 0, "每日统计没隔离"

    # 收藏隔离
    a_stars = a.get("/api/starred/ids").json()
    b_stars = b.get("/api/starred/ids").json()
    assert word_starred in a_stars["stars"]
    assert b_stars["stars"] == [], f"B 不该看到 A 的收藏：{b_stars}"
    assert b.get("/api/starred").json()["total"] == 0

    # 排除是按人做的：A 学过的不再出现，但 B 依然能看到（不受影响）
    a_new_ids = [w["word"]["id"] for w in a.get("/api/study/today?wordbook=all&limit=200").json()["words"]]
    b_new_ids = [w["word"]["id"] for w in b.get("/api/study/today?wordbook=all&limit=200").json()["words"]]
    assert word_studied not in a_new_ids, "A 不该再看到自己学过的词"
    assert word_studied in b_new_ids, "B 不该因为 A 学过就看不到这个词"

    # 删收藏只影响自己
    assert b.delete(f"/api/starred/{word_starred}?type=star").json()["count"] == 0
    assert word_starred in a.get("/api/starred/ids").json()["stars"], "B 的删除不该动到 A 的收藏"


def test_custom_wordbook_isolation_and_id_guessing():
    a = AuthClient(app)
    b = AuthClient(app)

    a_book = _insert_custom_book(a.get("/api/auth/me").json()["id"], "A 的书")
    b_book = _insert_custom_book(b.get("/api/auth/me").json()["id"], "B 的书")

    a_ids = [w["id"] for w in a.get("/api/wordbooks").json()]
    b_ids = [w["id"] for w in b.get("/api/wordbooks").json()]
    assert f"custom_{a_book}" in a_ids and f"custom_{b_book}" not in a_ids
    assert f"custom_{b_book}" in b_ids and f"custom_{a_book}" not in b_ids

    # 直接猜 ID 读别人的书 → 404
    assert a.get(f"/api/wordbooks/custom_{b_book}").status_code == 404
    # 删别人的书 → 404，且对方数据仍在
    assert a.delete(f"/api/wordbooks/custom_{b_book}").status_code == 404
    con = _db()
    still_there = con.execute("select count(*) from custom_wordbooks where id = ?", (b_book,)).fetchone()[0]
    con.close()
    assert still_there == 1, "越权删除动到了别人的词书"

    # 用自己的书筛选词库时，别人的书 id 不该返回任何词
    foreign = a.get("/api/study/today?wordbook=custom_{}".format(b_book)).json()
    assert foreign["total"] == 0, f"用别人的词书 id 竟然能取到词：{foreign['total']}"


def test_legacy_unowned_rows_are_invisible():
    """user_id 为 NULL 的遗留数据：不属于任何用户，也读不到、不占用学习名额"""
    a = AuthClient(app)
    # 取该用户"今日新词"里的第一个词，保证它一定落在后续查询的返回窗口内（结果确定）
    legacy_word = a.get("/api/study/today?wordbook=all&limit=1").json()["words"][0]["word"]["id"]
    now = datetime.now(timezone.utc)

    con = _db()
    con.execute(
        "insert into study_records (word_id, user_id, status, know_count, review_count, next_review_at, last_studied_at) "
        "values (?, NULL, 'known', 9, 9, ?, ?)",
        (legacy_word, (now - timedelta(days=1)).isoformat(), now.isoformat()),
    )
    con.execute(
        "insert into starred_words (word_id, user_id, type) values (?, NULL, 'star')",
        (legacy_word,),
    )
    con.commit()
    con.close()

    assert legacy_word not in a.get("/api/starred/ids").json()["stars"], "遗留收藏泄露给了用户"
    review_ids = [c["word"]["id"] for c in a.get("/api/study/review").json()["words"]]
    assert legacy_word not in review_ids, "遗留学习记录泄露给了用户"
    # 遗留记录不属于该用户，所以这个词仍应作为"新词"出现在他的列表里（没被别人的进度占用）
    today_ids = [w["word"]["id"] for w in a.get("/api/study/today?wordbook=all&limit=200").json()["words"]]
    assert legacy_word in today_ids, "遗留记录不该占用当前用户的学习名额"


def test_daily_stats_allow_same_day_per_user():
    """同一天不同用户各自一行统计（daily_stats 的唯一约束已改成 (user_id, date)）"""
    a = AuthClient(app)
    b = AuthClient(app)
    assert a.post("/api/study/record", json={"word_id": _word_id(500), "rating": 3}).status_code == 200
    assert b.post("/api/study/record", json={"word_id": _word_id(501), "rating": 3}).status_code == 200

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con = _db()
    rows = con.execute(
        "select user_id, new_words from daily_stats where date = ? order by user_id", (today,)
    ).fetchall()
    con.close()
    assert len(rows) >= 2, f"同一天应当有多个用户各自的统计行：{rows}"
    assert len({r[0] for r in rows}) == len(rows), "统计行没有按用户区分"

    assert a.get("/api/progress/overview").json()["today_new"] >= 1
    assert b.get("/api/progress/calendar?days=7").status_code == 200


# === 6. 公共数据仍然可用 ===

def test_public_data_still_works():
    """未登录也能用公共词库与预设词书（这两个是公共数据）"""
    c = TestClient(app)
    search = c.get("/api/words/search?q=abandon&limit=5")
    assert search.status_code == 200 and search.json(), "公共词库搜索不该需要登录"

    books = c.get("/api/wordbooks")
    assert books.status_code == 200
    ids = [b["id"] for b in books.json()]
    assert "core1000" in ids and "all" in ids, "预设词书应当公开可查"
    assert not any(i.startswith("custom_") for i in ids), "未登录不该看到任何自定义词书"

    assert c.get("/api/wordbooks/core1000").status_code == 200
    assert c.get("/api/wordbooks/custom_1").status_code == 404


# === 8. 迁移 ===

def _make_legacy_db(path: Path, rows: int = 3) -> None:
    """造一个"多用户改造前"的库：没有 user_id 列，daily_stats 的 date 全局唯一"""
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
        con.execute("insert into words (word, definition, frequency) values (?,?,?)", (f"legacy{i}", f"n. 旧词{i}", i))
        con.execute(
            "insert into study_records (word_id, status, know_count, review_count, next_review_at)"
            " values (?, 'learning', 2, 3, '2026-06-16T01:00:00+00:00')",
            (i,),
        )
        con.execute(
            "insert into daily_stats (date, new_words, reviewed_words, quiz_score, quiz_total, streak_days)"
            " values (?, ?, ?, ?, ?, ?)",
            (f"2026-06-{10 + i:02d}", i, i * 2, i * 3, i * 4, i),
        )
        con.execute("insert into starred_words (word_id, type) values (?, 'star')", (i,))
        con.execute(
            "insert into custom_wordbooks (name, query_text, keywords) values (?,?,?)",
            (f"旧书{i}", "旧需求", '["x"]'),
        )
    con.commit()
    con.close()


def _snapshot(db: Path) -> dict:
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    tables = ("words", "study_records", "daily_stats", "custom_wordbooks", "starred_words")
    snap = {t: cur.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
    snap["cols"] = {t: sorted(r[1] for r in cur.execute(f"PRAGMA table_info({t})")) for t in tables}
    # 旧库还没有 user_id 列，用 NULL 占位，这样"迁移前 vs 迁移后"的内容对比仍然等价
    user_col = "user_id" if "user_id" in snap["cols"]["daily_stats"] else "NULL"
    snap["daily_rows"] = cur.execute(
        f"select id, date, new_words, streak_days, {user_col} from daily_stats order by id"
    ).fetchall()
    snap["study_ids"] = [r[0] for r in cur.execute("select id from study_records order by id")]
    con.close()
    return snap


def test_migration_on_legacy_schema_is_lossless_and_idempotent():
    from sqlalchemy import create_engine

    from app.migrations import ensure_user_scope_schema

    legacy = TMP_DIR / "legacy-scope.db"
    _make_legacy_db(legacy, rows=3)
    before = _snapshot(legacy)
    assert "user_id" not in before["cols"]["study_records"], "构造的旧库不该有 user_id"

    eng = create_engine(f"sqlite:///{legacy}", connect_args={"check_same_thread": False})
    try:
        first = ensure_user_scope_schema(eng, backup_dir=TMP_DIR / "backups")
        second = ensure_user_scope_schema(eng, backup_dir=TMP_DIR / "backups")
    finally:
        eng.dispose()

    after = _snapshot(legacy)

    # 加列 + 重建
    for table in ("study_records", "custom_wordbooks", "starred_words"):
        assert "user_id" in after["cols"][table], f"{table} 缺少 user_id"
        assert set(before["cols"][table]) <= set(after["cols"][table]), f"{table} 丢了原有列"
    assert first["daily_stats_rebuilt"] is True
    assert first["backed_up"] and Path(first["backed_up"]).exists(), "迁移前没有备份"
    assert first["daily_stats_rows"] == 3

    # 数据无损：行数、主键、数值都不变；user_id 一律 NULL
    for t in ("words", "study_records", "daily_stats", "custom_wordbooks", "starred_words"):
        assert before[t] == after[t], f"{t} 行数变化：{before[t]} -> {after[t]}"
    assert before["study_ids"] == after["study_ids"], "study_records 主键集合变化"
    assert before["daily_rows"] == after["daily_rows"], "daily_stats 内容变化（应只剩 user_id 从无到 NULL）"

    # 唯一约束已改成 (user_id, date)：同一 date 能被不同用户各写一行
    con = sqlite3.connect(str(legacy))
    con.execute("insert into daily_stats (date, user_id, new_words) values ('2026-06-10', 1, 5)")
    con.execute("insert into daily_stats (date, user_id, new_words) values ('2026-06-10', 2, 6)")
    con.commit()
    n = con.execute("select count(*) from daily_stats where date='2026-06-10'").fetchone()[0]
    assert n == 2, f"同一天应能容纳不同用户各一行，实际 {n}"

    # 但同一用户同一天重复插入必须仍被拒绝（说明唯一约束没有在迁移中被丢掉）
    try:
        con.execute("insert into daily_stats (date, user_id, new_words) values ('2026-06-10', 1, 7)")
        con.commit()
        con.close()
        raise AssertionError("同一用户同一天重复插入竟然成功：唯一约束在迁移中丢失了")
    except sqlite3.IntegrityError:
        con.rollback()
    con.close()

    # 幂等
    assert second["added_columns"] == {} and second["daily_stats_rebuilt"] is False, second


def test_migration_keeps_real_data_intact():
    """对真实库副本跑隔离迁移：结构补全、行数不变、内容不变"""
    assert REAL_DB.exists(), f"找不到真实库 {REAL_DB}"
    from sqlalchemy import create_engine

    from app.migrations import ensure_user_scope_schema

    copy_db = TMP_DIR / "real-copy.db"
    shutil.copy(REAL_DB, copy_db)
    before = _snapshot(copy_db)

    eng = create_engine(f"sqlite:///{copy_db}", connect_args={"check_same_thread": False})
    try:
        first = ensure_user_scope_schema(eng, backup_dir=TMP_DIR / "backups-real")
        second = ensure_user_scope_schema(eng, backup_dir=TMP_DIR / "backups-real")
    finally:
        eng.dispose()

    after = _snapshot(copy_db)
    for t in ("words", "study_records", "daily_stats", "custom_wordbooks", "starred_words"):
        assert before[t] == after[t], f"{t} 行数变化：{before[t]} -> {after[t]}"
    assert before["daily_rows"] == after["daily_rows"], "daily_stats 内容被改动"
    for table in ("study_records", "custom_wordbooks", "starred_words"):
        assert "user_id" in after["cols"][table]
        assert set(before["cols"][table]) <= set(after["cols"][table])
    if first["added_columns"] or first["daily_stats_rebuilt"]:
        assert first["backed_up"], "动了结构却没有备份"
    assert second["added_columns"] == {} and second["daily_stats_rebuilt"] is False, "迁移不幂等"


def test_real_database_untouched_by_tests():
    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    if REAL_DB.exists():
        con = sqlite3.connect(str(REAL_DB))
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