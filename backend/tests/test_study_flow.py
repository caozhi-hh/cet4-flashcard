"""学习流程写入路径测试 — 全程在临时数据库上跑，绝不触碰真实学习数据

红灯背景（修前实测）：
    1) POST /api/study/record 传不存在的 word_id（如 99999999）会返回 200 并"记录成功"，
       往 study_records 写入孤儿记录（SQLite 默认不强制外键），污染 learned_words 统计。
    2) study_service / progress 里的 Subquery 被 SQLAlchemy 隐式强制转换为 select() 用于 IN()，
       产生 SAWarning；该隐式行为在后续版本会移除。

隔离方式：
    测试库建在 backend/tests/.tmp-db/cet4.db，导入的是 cet4_words.json（空库自建），
    与 D:\\data\\cet4.db 里的真实进度完全无关；运行结束自动删除。

运行方式（二选一）：
    python tests/test_study_flow.py
    pytest tests/test_study_flow.py
"""

import atexit
import shutil
import sys
import warnings
from pathlib import Path

from sqlalchemy.exc import SAWarning

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# === 关键：必须在导入 app.database 之前改写配置，引擎才会指向临时库 ===
TMP_DIR = BACKEND_DIR / "tests" / ".tmp-db"
if TMP_DIR.exists():
    shutil.rmtree(TMP_DIR, ignore_errors=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

import app.config as config  # noqa: E402

config.DB_PATH = TMP_DIR / "cet4.db"
config.DATABASE_URL = f"sqlite:///{config.DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


def _cleanup_tmp_db():
    """先释放 SQLite 连接再删临时库。

    Windows 上文件被打开时无法删除，而 rmtree(ignore_errors=True) 会把这个失败
    静默吞掉，结果每跑一次就留下一个删不掉的 .tmp-db 目录。
    """
    engine.dispose()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


atexit.register(_cleanup_tmp_db)

# 进入 with 才会执行 lifespan：建表 + 导入 4544 词到临时库
with TestClient(app) as _boot:
    _boot.get("/api/health")

client = TestClient(app)


def _word_id() -> int:
    """取一个真实存在的 word_id"""
    res = client.get("/api/study/today")
    assert res.status_code == 200
    words = res.json()["words"]
    assert words, "临时库未导入词库"
    return words[0]["word"]["id"]


def test_no_sqlalchemy_coercion_warning():
    """相关查询不得触发 SQLAlchemy 的 Subquery 强制转换告警"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SAWarning)
        assert client.get("/api/study/today").status_code == 200
        assert client.get("/api/progress/overview").status_code == 200
    msgs = [str(w.message) for w in caught if issubclass(w.category, SAWarning)]
    assert not msgs, f"出现 SAWarning：{msgs[:2]}"


def test_rejects_unknown_word_id():
    """不存在的 word_id 必须被拒绝，且不得写入孤儿学习记录"""
    before = client.get("/api/progress/overview").json()["learned_words"]
    res = client.post("/api/study/record", json={"word_id": 99999999, "known": True})
    assert res.status_code == 404, f"期望 404，实际 {res.status_code}：{res.text[:120]}"
    after = client.get("/api/progress/overview").json()["learned_words"]
    assert after == before, f"孤儿记录被写入：learned {before} -> {after}"


def test_study_record_flow():
    """提交学习结果 → 落库 → 统计随之变化"""
    word_id = _word_id()
    before = client.get("/api/progress/overview").json()["learned_words"]

    res = client.post("/api/study/record", json={"word_id": word_id, "known": True})
    assert res.status_code == 200, res.text[:120]
    body = res.json()
    assert body["word_id"] == word_id
    assert body["know_count"] == 1
    assert body["status"] == "learning"

    after = client.get("/api/progress/overview").json()["learned_words"]
    assert after > before, f"learned_words 未更新：{before} -> {after}"

    # 连续认识达到阈值后应标记为 known
    for _ in range(4):
        client.post("/api/study/record", json={"word_id": word_id, "known": True})
    status = client.post("/api/study/record", json={"word_id": word_id, "known": True}).json()["status"]
    assert status == "known", f"达到阈值后状态应为 known，实际 {status}"

    # "不认识"应把 know_count 归零并回到 learning
    res = client.post("/api/study/record", json={"word_id": word_id, "known": False}).json()
    assert res["status"] == "learning" and res["know_count"] == 0, res


def test_quiz_unanswered_does_not_clear_progress():
    """交卷时"未作答"的题不得清零该词的连续认识次数

    红灯背景：
        前端把未作答的题以空串提交（quiz/page.tsx: `answers[q.word_id] || ""`），
        后端 check_answers 把空串判为错，并调用 submit_study(known=False)，
        而 known=False 会把 record.know_count 清零、状态退回 learning
        —— 只答 3 题就交卷，另外 7 个已连续认对的词进度被不可逆清掉。
    """
    today = client.get("/api/study/today").json()["words"]
    word_id = today[4]["word"]["id"]  # 取一个与其它用例不冲突的词

    # 先把它连续认对 KNOW_THRESHOLD(3) 次 → known
    for _ in range(3):
        client.post("/api/study/record", json={"word_id": word_id, "known": True})
    known_before = client.get("/api/progress/overview").json()["known_words"]
    assert known_before >= 1, "前置条件失败：该词未被标记为 known"

    res = client.post(
        "/api/quiz/submit",
        json={"answers": [{"word_id": word_id, "answer": "", "correct_answer": "任意值"}]},
    )
    assert res.status_code == 200, res.text[:120]

    # 先断言真正的危害：进度不得被清掉
    known_after = client.get("/api/progress/overview").json()["known_words"]
    assert known_after == known_before, f"未作答却清掉了进度：known {known_before} -> {known_after}"

    body = res.json()
    assert body["unanswered"] == 1, f"未作答数量应为 1，实际 {body.get('unanswered')}"
    assert body["score"] == 0, f"未作答不应得分，实际 {body['score']}"
    assert body["wrong_words"] == [], "未作答不应被计入错题"


def test_starred_add_and_remove():
    """生词本：加入、幂等、移除"""
    word_id = _word_id()
    assert client.post("/api/starred", json={"word_id": word_id, "type": "star"}).status_code == 200
    assert word_id in client.get("/api/starred/ids").json()["stars"]
    assert client.post("/api/starred", json={"word_id": word_id, "type": "star"}).json()["exists"] is True
    assert client.delete(f"/api/starred/{word_id}?type=star").status_code == 200
    assert word_id not in client.get("/api/starred/ids").json()["stars"]


def test_quiz_daily_and_submit():
    """测验出题与交卷"""
    quiz = client.get("/api/quiz/daily").json()
    questions = quiz["questions"]
    assert questions, "测验未出题"
    answers = [
        {"word_id": q["word_id"], "answer": q["correct_answer"], "correct_answer": q["correct_answer"]}
        for q in questions
    ]
    res = client.post("/api/quiz/submit", json={"answers": answers})
    assert res.status_code == 200, res.text[:120]
    body = res.json()
    assert body["total"] == len(questions)
    assert body["score"] == len(questions), f"全对提交却得分 {body['score']}/{body['total']}"


def test_real_database_not_touched():
    """确认测试用的是临时库，真实库路径没有被本测试改写"""
    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    assert (TMP_DIR / "cet4.db").exists()


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