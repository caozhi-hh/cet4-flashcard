"""默写闭环测试 — /api/study/dictation

红灯背景（改造前）：
    没有"学完一章立刻默写"的入口与接口。qwerty-learner 的做法是章节练完弹出默写本章，
    这里对应一个"取今天学过的词"的只读接口（前端用它渲染默写页）。

数据安全：全部写入只发生在 backend/tests/.tmp-dictation/ 的临时库里。
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

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-dictation"
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
    engine.dispose()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup)

with TestClient(app) as _boot:
    _boot.get("/api/health")

from testkit import AuthClient  # noqa: E402  引入 Cookie 会话后默认以登录用户运行

client = AuthClient(app)  # 写请求自动带 CSRF 头


def _word_id(offset: int = 0) -> int:
    con = sqlite3.connect(str(config.DB_PATH))
    row = con.execute("select id from words order by id limit 1 offset ?", (offset,)).fetchone()
    con.close()
    assert row, f"词库不足 {offset + 1} 个词"
    return row[0]


def _counts() -> dict:
    con = sqlite3.connect(str(config.DB_PATH))
    cur = con.cursor()
    out = {
        t: cur.execute(f'select count(*) from "{t}"').fetchone()[0]
        for t in ("words", "study_records", "daily_stats", "starred_words")
    }
    con.close()
    return out


def test_dictation_falls_back_to_new_words():
    """当天还没有学习记录时，默写应回落到"今日新词"，而不是返回空白页"""
    res = client.get("/api/study/dictation?limit=10")
    assert res.status_code == 200, res.text[:140]
    body = res.json()
    assert body["type"] == "dictation"
    assert body["total"] > 0, "没有学习记录时应当回落到今日新词"
    assert body["total"] <= 10
    first = body["words"][0]["word"]
    # 默写需要：释义（提示）与单词本身（对答案）
    for key in ("word", "definition"):
        assert first.get(key), f"默写词条缺少 {key}: {first}"


def test_dictation_prefers_words_studied_today():
    """有今日学习记录时，默写应当取这些词（即"刚学完的这一章"）"""
    studied = [_word_id(100), _word_id(101), _word_id(102)]
    for wid in studied:
        assert client.post("/api/study/record", json={"word_id": wid, "rating": 3}).status_code == 200

    body = client.get("/api/study/dictation?limit=20").json()
    ids = [w["word"]["id"] for w in body["words"]]
    for wid in studied:
        assert wid in ids, f"今天学过的词 {wid} 没进默写列表：{ids}"


def test_dictation_respects_limit():
    body = client.get("/api/study/dictation?limit=3").json()
    assert body["total"] <= 3, body["total"]


def test_dictation_is_read_only():
    """默写页取词不能改动任何数据"""
    before = _counts()
    client.get("/api/study/dictation?limit=20")
    after = _counts()
    assert before == after, f"取默写词改动了数据：{before} -> {after}"


def test_dictation_rejects_bad_limit():
    """limit 越界要被拒绝，而不是返回一堆或负数"""
    for bad in (0, -5, 999):
        res = client.get(f"/api/study/dictation?limit={bad}")
        assert res.status_code == 422, f"limit={bad} 期望 422，实际 {res.status_code}"


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