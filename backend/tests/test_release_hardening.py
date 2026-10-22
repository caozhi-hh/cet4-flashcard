"""发布加固测试 — 测验服务端判分、AI 接口限制、密钥不外泄

红灯背景（修复前实测）：
    1) GET /api/quiz/daily 会把每题的 correct_answer 一起下发；
       POST /api/quiz/submit 直接用客户端回传的 correct_answer 判分 ——
       改一个字段就能满分。
    2) AI 接口只要求登录，没有任何调用频率限制。

覆盖：
    1) 题目里不含正确答案
    2) 伪造 correct_answer 不能影响判分
    3) 服务端依据词库数据正确判分（释义题 / 拼写题）
    4) 未作答不计分、也不回写学习进度
    5) AI 接口未登录被拒
    6) AI 接口超限返回 429（并带 Retry-After）
    7) API 响应里不出现服务端配置的 AI 密钥

数据安全：只写 backend/tests/.tmp-release/。

运行：python tests/test_release_hardening.py
"""

import atexit
import os
import secrets
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

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-release"
if TMP_DIR.exists():
    shutil.rmtree(TMP_DIR, ignore_errors=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

# 必须在导入 app.config 之前设置：config 在导入时读取环境变量
SENTINEL_KEY = "sk-sentinel-" + secrets.token_hex(6)
os.environ["AI_API_KEY"] = SENTINEL_KEY
os.environ["AI_MNEMONIC_LIMIT"] = "3"
os.environ["AI_WORDBOOK_LIMIT"] = "2"

import app.config as config  # noqa: E402

config.DB_PATH = TMP_DIR / "cet4.db"
config.DATABASE_URL = f"sqlite:///{config.DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import ai as ai_router  # noqa: E402
from app.services import rate_limit  # noqa: E402
from testkit import AuthClient, csrf_headers  # noqa: E402


async def _fake_mnemonic(**_kwargs) -> str:
    """替身：不真的调用外部 LLM（测试不打网络）"""
    return "stub-mnemonic"


ai_router.generate_mnemonic = _fake_mnemonic


def _cleanup():
    engine.dispose()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup)

with TestClient(app) as _boot:
    _boot.get("/api/health")

client = AuthClient(app)


def _db() -> sqlite3.Connection:
    return sqlite3.connect(str(config.DB_PATH))


def _word_facts(word_id: int) -> tuple[str, str]:
    """返回 (释义首段, 英文单词) —— 判分只应依据这些数据"""
    con = _db()
    row = con.execute("select word, definition from words where id = ?", (word_id,)).fetchone()
    con.close()
    assert row, f"词库里没有 {word_id}"
    word, definition = row
    return (definition.split("；")[0] if "；" in definition else definition), word


def _daily_questions(c: AuthClient) -> list[dict]:
    res = c.get("/api/quiz/daily")
    assert res.status_code == 200, res.text[:200]
    questions = res.json()["questions"]
    assert questions, "应有题目"
    return questions


# === 1. 题目不含答案 ===

def test_quiz_questions_do_not_leak_answers():
    questions = _daily_questions(client)
    raw = client.get("/api/quiz/daily").text
    for q in questions:
        assert "correct_answer" not in q, f"下发字段里带了答案：{q}"
    assert "correct_answer" not in raw, "响应里出现了 correct_answer"
    # 选项仍在（前端要靠它渲染），但答案不在
    assert any(q.get("options") for q in questions), "选择题应有选项"


# === 2/3. 判分 ===

def test_forged_correct_answer_cannot_inflate_score():
    questions = _daily_questions(client)
    payload = []
    for q in questions:
        definition, word = _word_facts(q["word_id"])
        # 故意答错，同时伪造一个"正确答案"
        payload.append({"word_id": q["word_id"], "answer": "definitely-wrong", "correct_answer": definition})
    res = client.post("/api/quiz/submit", json={"answers": payload})
    assert res.status_code == 200, res.text[:200]
    body = res.json()
    assert body["score"] == 0, f"伪造 correct_answer 竟然得分：{body}"
    assert body["total"] == len(questions)


def test_server_grades_against_word_data():
    questions = _daily_questions(client)

    # 全部按词库数据作答 → 满分
    payload = []
    for q in questions:
        definition, word = _word_facts(q["word_id"])
        answer = word if q["quiz_type"] == "spell" else definition
        payload.append({"word_id": q["word_id"], "answer": answer})
    res = client.post("/api/quiz/submit", json={"answers": payload})
    body = res.json()
    assert body["score"] == body["total"] == len(questions), f"按词库作答应满分：{body}"

    # 拼写题：大小写与多余空格应被容忍
    spell = next((q for q in questions if q["quiz_type"] == "spell"), None)
    if spell:
        _definition, word = _word_facts(spell["word_id"])
        res = client.post(
            "/api/quiz/submit",
            json={"answers": [{"word_id": spell["word_id"], "answer": f"  {word.upper()}  "}]},
        )
        assert res.json()["score"] == 1, f"归一化后应判对：{res.json()}"

    # 释义题：可以用完整释义作答（规范化后一致）
    choice = next((q for q in questions if q["quiz_type"] in {"choice", "listen"}), None)
    if choice:
        definition, _word = _word_facts(choice["word_id"])
        res = client.post(
            "/api/quiz/submit",
            json={"answers": [{"word_id": choice["word_id"], "answer": definition.upper()}]},
        )
        assert res.json()["score"] == 1, f"大小写不该影响判分：{res.json()}"


def test_unanswered_not_scored_and_no_progress_write():
    a = AuthClient(app)
    questions = _daily_questions(a)
    target = questions[0]["word_id"]

    before = a.get("/api/progress/overview").json()
    res = a.post(
        "/api/quiz/submit",
        json={"answers": [{"word_id": q["word_id"], "answer": ""} for q in questions]},
    )
    body = res.json()
    assert body["score"] == 0 and body["unanswered"] == len(questions), body
    assert body["wrong_words"] == [], "未作答不该记成错题"

    after = a.get("/api/progress/overview").json()
    assert after["learned_words"] == before["learned_words"], "未作答不该写入学习记录"

    con = _db()
    n = con.execute(
        "select count(*) from study_records where user_id = ? and word_id = ?",
        (a.get("/api/auth/me").json()["id"], target),
    ).fetchone()[0]
    con.close()
    assert n == 0, "未作答却写了学习记录"


def test_wrong_answers_write_only_current_users_progress():
    """错题：服务端回传 wrong_words 并写**当前用户**的学习记录

    注意契约：错题本（starred/hard）由前端拿到 wrong_words 后调用 starred API 写入，
    服务端不替客户端写；这里验证的是服务端真正负责的部分 + 用户隔离。
    """
    a = AuthClient(app)
    b = AuthClient(app)
    questions = _daily_questions(a)
    wrong_word = questions[0]["word_id"]
    uid_a = a.get("/api/auth/me").json()["id"]

    body = a.post(
        "/api/quiz/submit",
        json={"answers": [{"word_id": q["word_id"], "answer": "xxx"} for q in questions]},
    ).json()
    assert {w["id"] for w in body["wrong_words"]} == {q["word_id"] for q in questions}, body
    assert wrong_word in {w["id"] for w in body["wrong_words"]}

    con = _db()
    n = con.execute(
        "select count(*) from study_records where user_id = ? and word_id = ?", (uid_a, wrong_word)
    ).fetchone()[0]
    con.close()
    assert n == 1, "错题应写入该用户自己的学习记录"

    # 其他用户既没有学习记录，也没有错题
    assert b.get("/api/progress/overview").json()["learned_words"] == 0
    assert b.get("/api/starred/ids").json()["hards"] == []
    assert b.get("/api/quiz/daily").json()["total"] >= 1, "B 自己仍能正常出题"


# === 4. AI 接口 ===

def test_ai_endpoints_require_login():
    anon = TestClient(app)
    anon.get("/api/auth/csrf")
    headers = csrf_headers(anon)
    res = anon.post("/api/ai/mnemonic", json={"word_id": 1}, headers=headers)
    assert res.status_code == 401, res.text[:150]
    res = anon.post("/api/wordbooks/ai-generate", json={"query": "食物"}, headers=headers)
    assert res.status_code == 401, res.text[:150]


def test_ai_mnemonic_is_rate_limited():
    rate_limit.reset_rate_limits()
    c = AuthClient(app)
    word_id = _daily_questions(c)[0]["word_id"]
    limit = config.AI_MNEMONIC_LIMIT
    assert limit == 3, f"本测试依赖 AI_MNEMONIC_LIMIT=3，实际 {limit}"

    for i in range(limit):
        res = c.post("/api/ai/mnemonic", json={"word_id": word_id})
        assert res.status_code == 200, f"第 {i + 1} 次应放行：{res.status_code} {res.text[:120]}"

    blocked = c.post("/api/ai/mnemonic", json={"word_id": word_id})
    assert blocked.status_code == 429, f"超限应 429，实际 {blocked.status_code}"
    assert blocked.headers.get("Retry-After"), "429 应带 Retry-After"
    assert "频繁" in blocked.json()["detail"]

    # 限流按用户隔离：别人不受影响
    other = AuthClient(app)
    assert other.post("/api/ai/mnemonic", json={"word_id": word_id}).status_code == 200


def test_ai_key_never_appears_in_responses():
    """服务端配置的 AI 密钥不得出现在任何 API 响应里"""
    paths = [
        "/api/health",
        "/api/quiz/daily",
        "/api/study/today?limit=3",
        "/api/progress/overview",
        "/api/wordbooks",
        "/api/plan",
        "/api/plan/forecast",
        "/api/reading/articles",
    ]
    for path in paths:
        res = client.get(path)
        assert SENTINEL_KEY not in res.text, f"{path} 的响应里出现了 AI 密钥"
    res = client.post("/api/ai/mnemonic", json={"word_id": _daily_questions(client)[0]["word_id"]})
    assert SENTINEL_KEY not in res.text, "AI 接口响应泄露了密钥"


def test_quiz_has_questions_for_brand_new_user():
    """刚学 1-3 个词的新用户也必须能拿到一张可用试卷（主流程不能空白）"""
    fresh = AuthClient(app)

    # 全新用户（连学习记录都没有）
    first = fresh.get("/api/quiz/daily").json()
    assert first["total"] >= 4, f"全新用户应能出题，实际 {first['total']}"

    # 只学 1 个词：词池不足 4，必须用词库补足而不是返回空卷
    word_id = first["questions"][0]["word_id"]
    assert fresh.post("/api/study/record", json={"word_id": word_id, "rating": 3}).status_code == 200
    after = fresh.get("/api/quiz/daily").json()
    assert after["total"] >= 4, f"只学 1 个词时测验仍应可用，实际 {after['total']}"
    assert all(q.get("word") and q.get("quiz_type") for q in after["questions"])


def test_real_database_untouched_by_tests():
    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    real = Path(r"D:\data\cet4.db")
    if real.exists():
        con = sqlite3.connect(str(real))
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