"""分级阅读测试 — 文章内容、分词查词、服务端判分、用户隔离、迁移安全

覆盖：
    1) 文章列表 / 难度筛选 / 学习目标筛选 / 详情
    2) 详情**不泄露正确答案**
    3) 判分只依据服务端答案，不采信客户端提交的分数
    4) 未登录不能读个人历史或提交记录
    5) A/B 阅读记录完全隔离
    6) 查词精确匹配现有词库；未收录词有明确反馈
    7) 分词状态跟随当前用户自己的学习记录（跨功能一致性）
    8) 迁移幂等、不丢既有数据（含真实库副本）

数据安全：写入只发生在 backend/tests/.tmp-reading/；真实库只在"复制一份"后验证迁移。

运行：python tests/test_reading.py
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
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-reading"
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
ARTICLES_JSON = BACKEND_DIR / "app" / "data" / "reading_articles.json"


def _cleanup():
    engine.dispose()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup)

with TestClient(app) as _boot:
    _boot.get("/api/health")

client = AuthClient(app)  # 默认已登录（公共接口同样可用）


def _db() -> sqlite3.Connection:
    return sqlite3.connect(str(config.DB_PATH))


def _uid(c: AuthClient) -> int:
    return c.get("/api/auth/me").json()["id"]


def _key() -> dict[str, dict]:
    """测试用的答案键（直接读内容文件；线上只在服务端内部使用）"""
    data = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
    return {a["slug"]: a for a in data["articles"]}


def _all_keys(obj, bad=("answer", "correct_choice", "explanation")) -> list[str]:
    """递归找出不该出现在详情响应里的字段名"""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in bad:
                hits.append(k)
            hits.extend(_all_keys(v, bad))
    elif isinstance(obj, list):
        for v in obj:
            hits.extend(_all_keys(v, bad))
    return hits


# === 1. 列表 / 筛选 / 详情 ===

def test_article_list_covers_levels_and_filters():
    res = client.get("/api/reading/articles")
    assert res.status_code == 200, res.text[:200]
    data = res.json()
    assert data["total"] >= 6, f"至少 6 篇：{data['total']}"
    assert data["levels"] == ["A1", "A2", "B1"]

    for level in ("A1", "A2", "B1"):
        filtered = client.get(f"/api/reading/articles?level={level}").json()
        assert filtered["total"] >= 2, f"{level} 至少 2 篇：{filtered['total']}"
        assert all(a["level"] == level for a in filtered["articles"])

    # 小写也认
    assert client.get("/api/reading/articles?level=a2").json()["total"] >= 2
    # 非法难度 → 404（而不是静默返回全部）
    assert client.get("/api/reading/articles?level=C2").status_code == 404

    # 按学习目标筛选
    for goal in ("cet4", "cet6", "kaoyan", "ielts", "toefl", "general"):
        got = client.get(f"/api/reading/articles?goal={goal}").json()
        assert got["total"] >= 1, f"目标 {goal} 至少 1 篇"
        assert all(goal in a["goals"] for a in got["articles"])

    # 列表不返回正文（列表页不需要整篇正文）
    assert "paragraphs" not in data["articles"][0]
    assert data["articles"][0]["word_count"] > 50
    assert data["articles"][0]["source"], "应标明是原创示例"


def test_article_detail_shape_and_no_answer_leak():
    slug = next(iter(_key()))
    res = client.get(f"/api/reading/articles/{slug}")
    assert res.status_code == 200, res.text[:200]
    data = res.json()

    article = data["article"]
    assert article["slug"] == slug
    assert len(article["paragraphs"]) >= 3
    assert article["paragraphs"][0]["en"] and article["paragraphs"][0]["zh"], "应有中英对照"
    assert len(article["questions"]) >= 3
    assert article["questions"][0]["options"], "应有选项"

    # 关键：详情里绝不能出现答案与解析
    leaks = _all_keys(data)
    assert not leaks, f"详情泄露了答案字段：{set(leaks)}"
    assert '"answer"' not in res.text and "correct_choice" not in res.text

    # 分词渲染项
    tokens = data["tokens"]
    assert len(tokens) >= 3, "应至少分出 3 段"
    flat = [t for para in tokens for t in para]
    words = [t for t in flat if t["is_word"]]
    assert len(words) >= 50, f"词项太少：{len(words)}"
    assert all("span_id" in t and "status" in t for t in flat)
    # 词项带词库释义（能被查询到）
    defined = [t for t in words if t["term"] and t["term"].get("definition")]
    assert len(defined) >= 10, f"应有不少词能在词库里查到：{len(defined)}"
    # 标点/空白项不带 term
    assert all(t["term"] is None for t in flat if not t["is_word"])

    # 分段号连续
    paras = sorted({t["paragraph"] for t in flat})
    assert paras == list(range(len(article["paragraphs"]))), paras


def test_unknown_article_404():
    assert client.get("/api/reading/articles/no-such-article").status_code == 404


# === 2. 查词（精确匹配） ===

def test_lookup_exact_match_only():
    hit = client.get("/api/reading/lookup?word=abandon")
    assert hit.status_code == 200
    body = hit.json()
    assert body["found"] is True, body
    assert body["definition"], body
    assert body["headword"].lower() == "abandon"

    # 大小写不敏感
    assert client.get("/api/reading/lookup?word=Abandon").json()["found"] is True

    # 未收录 → 明确反馈（不是给一个不相关的近似词）
    miss = client.get("/api/reading/lookup?word=zzzznotaword").json()
    assert miss["found"] is False
    assert miss["message"], "未收录时必须给出可读提示"
    assert "definition" not in miss

    # 不做模糊匹配：多一个字母就不是同一个词
    near = client.get("/api/reading/lookup?word=abandonn").json()
    assert near["found"] is False, "不该模糊匹配到 abandon"

    # 非单词输入被拒
    assert client.get("/api/reading/lookup?word=hello%20world").json()["found"] is False


def test_token_status_follows_current_user_records():
    """分词状态必须跟随**当前用户自己**的学习记录"""
    a = AuthClient(app)
    b = AuthClient(app)

    slug = next(iter(_key()))
    detail = a.get(f"/api/reading/articles/{slug}").json()
    token = next(
        t for para in detail["tokens"] for t in para if t["is_word"] and t["term"]
    )
    word_id = token["term"]["word_id"]
    assert token["status"] == "new", token

    # 给 A（不是 B）写一条"已掌握"记录
    con = _db()
    con.execute(
        "insert into study_records (word_id, user_id, status, know_count, review_count)"
        " values (?,?,'known',5,5)",
        (word_id, _uid(a)),
    )
    con.commit()
    con.close()

    a_detail = a.get(f"/api/reading/articles/{slug}").json()
    a_token = next(
        (t for para in a_detail["tokens"] for t in para if t["is_word"] and t["term"] and t["term"]["word_id"] == word_id),
        None,
    )
    assert a_token and a_token["status"] == "known", a_token

    b_detail = b.get(f"/api/reading/articles/{slug}").json()
    b_token = next(
        (t for para in b_detail["tokens"] for t in para if t["is_word"] and t["term"] and t["term"]["word_id"] == word_id),
        None,
    )
    assert b_token and b_token["status"] == "new", f"B 不该看到 A 的掌握状态：{b_token}"


def test_token_status_for_anonymous():
    """未登录也能读文章，但状态一律按未学展示"""
    anon = TestClient(app)
    slug = next(iter(_key()))
    res = anon.get(f"/api/reading/articles/{slug}")
    assert res.status_code == 200
    statuses = {t["status"] for para in res.json()["tokens"] for t in para if t["is_word"]}
    assert statuses <= {"new", "unknown"}, statuses


# === 3. 判分 ===

def _answers_for(slug: str, correct: bool) -> list[dict]:
    article = _key()[slug]
    out = []
    for q in article["questions"]:
        choice = q["answer"] if correct else (q["answer"] + 1) % len(q["options"])
        out.append({"question_id": q["id"], "choice": choice})
    return out


def test_grade_uses_server_answer_key():
    a = AuthClient(app)
    slug = next(iter(_key()))

    full = a.post("/api/reading/attempts", json={"slug": slug, "answers": _answers_for(slug, True), "duration_seconds": 95})
    assert full.status_code == 200, full.text[:200]
    body = full.json()
    assert body["score"] == body["total"] >= 3, body
    assert body["passed"] is True
    assert body["duration_seconds"] == 95
    assert all(d["correct"] for d in body["details"])
    assert all(d["explanation"] for d in body["details"]), "提交后应给解析"

    zero = a.post("/api/reading/attempts", json={"slug": slug, "answers": _answers_for(slug, False)}).json()
    assert zero["score"] == 0, zero

    # 部分作答：只算答对的，未作答不给分但计入总题数
    partial = a.post(
        "/api/reading/attempts",
        json={"slug": slug, "answers": [{"question_id": _key()[slug]["questions"][0]["id"], "choice": _key()[slug]["questions"][0]["answer"]}]},
    ).json()
    assert partial["score"] == 1 and partial["answered"] == 1
    assert partial["total"] == len(_key()[slug]["questions"]), "总题数由服务端决定"


def test_client_cannot_forge_score():
    a = AuthClient(app)
    slug = next(iter(_key()))
    # 全错，但伪造满分 + passed + user_id
    forged = a.post(
        "/api/reading/attempts",
        json={
            "slug": slug,
            "answers": _answers_for(slug, False),
            "score": 999,
            "total": 999,
            "passed": True,
            "user_id": 1,
        },
    )
    assert forged.status_code == 200
    body = forged.json()
    assert body["score"] == 0, f"客户端伪造的分数被采信了：{body}"
    assert body["total"] == len(_key()[slug]["questions"])
    assert body["passed"] is False

    # 未知题号/越界选项都不给分
    weird = a.post(
        "/api/reading/attempts",
        json={"slug": slug, "answers": [{"question_id": "nope", "choice": 0}, {"question_id": _key()[slug]["questions"][0]["id"], "choice": 99}]},
    ).json()
    assert weird["score"] == 0 and weird["answered"] == 1, weird


def test_duplicate_question_cannot_inflate_score():
    a = AuthClient(app)
    slug = next(iter(_key()))
    q = _key()[slug]["questions"][0]
    res = a.post(
        "/api/reading/attempts",
        json={"slug": slug, "answers": [{"question_id": q["id"], "choice": q["answer"]} for _ in range(5)]},
    ).json()
    assert res["score"] == 1, f"重复提交同一题不该重复得分：{res}"


def test_attempt_requires_login():
    anon = TestClient(app)
    anon.get("/api/auth/csrf")
    headers = csrf_headers(anon)
    slug = next(iter(_key()))
    assert anon.get("/api/reading/progress").status_code == 401
    res = anon.post(
        "/api/reading/attempts",
        json={"slug": slug, "answers": []},
        headers=headers,
    )
    assert res.status_code == 401, res.text[:120]


def test_unknown_slug_attempt_404():
    a = AuthClient(app)
    assert a.post("/api/reading/attempts", json={"slug": "nope", "answers": []}).status_code == 404


# === 4/5. 进度与隔离 ===

def test_progress_and_history_isolated():
    a = AuthClient(app)
    b = AuthClient(app)
    slug = next(iter(_key()))
    other = list(_key())[1]

    a.post("/api/reading/attempts", json={"slug": slug, "answers": _answers_for(slug, True), "duration_seconds": 60})
    a.post("/api/reading/attempts", json={"slug": other, "answers": _answers_for(other, False), "duration_seconds": 30})

    pa = a.get("/api/reading/progress").json()
    pb = b.get("/api/reading/progress").json()

    assert pa["completed_articles"] == 2, pa["completed_articles"]
    assert pa["passed_articles"] == 1, pa["passed_articles"]
    assert set(pa["completed_slugs"]) == {slug, other}
    assert len(pa["history"]) == 2
    assert pa["history"][0]["slug"] == other, "历史应按完成时间倒序"
    assert sum(x["completed"] for x in pa["by_level"]) == 2

    assert pb["completed_articles"] == 0, f"B 不该看到 A 的记录：{pb['completed_articles']}"
    assert pb["history"] == []
    assert pb["completed_slugs"] == []
    assert all(x["attempts"] == 0 for x in pb["articles"])

    # A 的最佳成绩被保留（同篇第二次更好的分数）
    a.post("/api/reading/attempts", json={"slug": other, "answers": _answers_for(other, True)})
    pa2 = a.get("/api/reading/progress").json()
    row = next(x for x in pa2["articles"] if x["slug"] == other)
    assert row["attempts"] == 2 and row["best_score"] == row["best_total"], row


# === 8. 迁移 ===

def _snapshot(db: Path) -> dict:
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table'")]
    counts = {
        t: cur.execute(f'select count(*) from "{t}"').fetchone()[0]
        for t in ("words", "study_records", "daily_stats", "custom_wordbooks", "starred_words")
        if t in tables
    }
    cols = sorted(r[1] for r in cur.execute("PRAGMA table_info(reading_attempts)")) if "reading_attempts" in tables else []
    con.close()
    return {"counts": counts, "has_table": "reading_attempts" in tables, "cols": cols}


def test_migration_creates_table_idempotently_with_backup():
    from sqlalchemy import create_engine

    from app.migrations import ensure_reading_schema

    legacy = TMP_DIR / "legacy-reading.db"
    if legacy.exists():
        legacy.unlink()
    con = sqlite3.connect(str(legacy))
    con.executescript(
        """
        CREATE TABLE words (id INTEGER PRIMARY KEY AUTOINCREMENT, word VARCHAR(100) NOT NULL UNIQUE,
            definition TEXT NOT NULL, frequency INTEGER DEFAULT 0);
        CREATE TABLE study_records (id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER NOT NULL,
            user_id INTEGER, status VARCHAR(20), know_count INTEGER DEFAULT 0, unknown_count INTEGER DEFAULT 0,
            review_count INTEGER DEFAULT 0, next_review_at VARCHAR(30), last_studied_at VARCHAR(30), created_at VARCHAR(30));
        """
    )
    con.execute("insert into words (word, definition, frequency) values ('legacy','n. 旧词',1)")
    con.execute("insert into study_records (word_id, user_id, status) values (1, NULL, 'learning')")
    con.commit()
    con.close()

    before = _snapshot(legacy)
    assert before["has_table"] is False

    eng = create_engine(f"sqlite:///{legacy}", connect_args={"check_same_thread": False})
    try:
        first = ensure_reading_schema(eng, backup_dir=TMP_DIR / "backups")
        second = ensure_reading_schema(eng, backup_dir=TMP_DIR / "backups")
    finally:
        eng.dispose()

    after = _snapshot(legacy)
    assert first["created_table"] is True and second["created_table"] is False, (first, second)
    assert after["has_table"] is True
    assert set(after["cols"]) == {
        "id", "user_id", "slug", "level", "score", "total",
        "duration_seconds", "completed_at", "created_at",
    }, after["cols"]
    assert before["counts"] == after["counts"], "迁移不该改动既有数据"
    assert first["backed_up"] and Path(first["backed_up"]).exists(), "建表前应有备份"
    assert len(list((TMP_DIR / "backups").glob("*"))) == 1, "幂等重跑不该再产生备份"


def test_migration_on_real_copy_keeps_data():
    """对真实库副本建表：结构就位、既有行数不变（本轮不动真实库本身）"""
    assert REAL_DB.exists(), f"找不到真实库 {REAL_DB}"
    from sqlalchemy import create_engine

    from app.migrations import ensure_reading_schema

    copy_db = TMP_DIR / "real-copy.db"
    shutil.copy(REAL_DB, copy_db)
    before = _snapshot(copy_db)

    eng = create_engine(f"sqlite:///{copy_db}", connect_args={"check_same_thread": False})
    try:
        result = ensure_reading_schema(eng, backup_dir=TMP_DIR / "backups-real")
    finally:
        eng.dispose()

    after = _snapshot(copy_db)
    assert after["has_table"] is True
    assert before["counts"] == after["counts"], f"行数变化：{before['counts']} -> {after['counts']}"
    assert result["backed_up"] and Path(result["backed_up"]).exists(), "应产出备份便于回退"


def test_real_database_untouched_by_tests():
    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    if REAL_DB.exists():
        con = sqlite3.connect(str(REAL_DB))
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        n = con.execute("select count(*) from study_records").fetchone()[0]
        con.close()
        assert "reading_attempts" not in tables, "测试不该在真实库里建表"
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