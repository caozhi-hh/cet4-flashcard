"""PostgreSQL 集成测试（真实数据库）—— 需要 TEST_DATABASE_URL

为什么单独一个文件、且默认跳过：
    PostgreSQL 的真实行为（序列、约束、事务、连接池）只能在真实服务器上验证。
    本机不一定有 PostgreSQL，**有则跑、没有就明确标注"未执行"**，
    绝不用"SQLite 通过"冒充"PostgreSQL 通过"。

用法（务必用**独立测试分支/库**，不要指向生产）：
    Neon 上推荐做法：在同一个 Neon 项目里新建一个分支（例如命名 dev-test），
    用该分支的连接串运行本套件；绝对不要用「生产」分支的连接串。

    Windows PowerShell:
        $env:TEST_DATABASE_URL="postgresql://<user>:<pw>@<test-branch-host>.neon.tech/neondb?sslmode=require"
        $env:TEST_DB_ACK="I_UNDERSTAND_THIS_DROPS_TABLES"
        python tests/test_postgres_integration.py
    bash:
        TEST_DATABASE_URL="postgresql://..." TEST_DB_ACK="I_UNDERSTAND_THIS_DROPS_TABLES" \
            python tests/test_postgres_integration.py

安全护栏（本套件会 drop_all，宁可拒绝执行也不能误删数据）：
    1. 只认 TEST_DATABASE_URL（**不读 DATABASE_URL**，避免顺手拿生产连接串）；
    2. 必须显式设置 TEST_DB_ACK=I_UNDERSTAND_THIS_DROPS_TABLES；
    3. 库名或主机必须能看出是测试环境（含 test/dev/sandbox/staging）；
    4. 若设置了 PROD_DB_HOST，目标主机与它相同则直接拒绝
       —— Neon 的"环境"靠**分支**区分、每个分支库名往往都叫 neondb，
          这条专门挡住"生产分支 + 库名带 test"这种最危险的情况；
    5. 连上后若发现 users/study_records 已有数据，同样拒绝（除非 TEST_DB_ALLOW_EXISTING=1）；
    6. 只读预检：设 TEST_DB_PREFLIGHT=1 只打印目标与既有行数，不删任何东西。
    任何拒绝都以退出码 2 结束，且**不会打印密码**（连接串一律掩码）。

覆盖：建表与结构校验、词库首次导入与词书统计、注册登录、跨用户隔离、
      学习记录、计划、阅读记录、daily_stats 多用户同日、健康检查与重连、事务回滚。
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

RAW_URL = (os.environ.get("TEST_DATABASE_URL") or "").strip()

# 破坏性动作的显式确认口令（缺了它，即使给了 URL 也一律不 drop）
ACK_PHRASE = "I_UNDERSTAND_THIS_DROPS_TABLES"

if not RAW_URL:
    print("=" * 78)
    print("SKIP（未执行）：没有提供 TEST_DATABASE_URL，PostgreSQL 端到端测试本轮未运行。")
    print("  已完成的替代验证：tests/test_db_backend.py（配置/方言/DDL 编译级校验，13 项）")
    print("  待补：准备**独立测试分支/库**后，按下面三道护栏执行本套件。")
    print("  护栏：① TEST_DATABASE_URL 指向独立测试库/Neon 测试分支")
    print(f"        ② TEST_DB_ACK={ACK_PHRASE}")
    print("        ③ 目标库里 users 表若已有数据则拒绝（除非 TEST_DB_ALLOW_EXISTING=1）")
    print(f"  先看目标不删数据：另加 TEST_DB_PREFLIGHT=1")
    print("=" * 78)
    sys.exit(0)


def _split_url(url: str) -> tuple[str, str]:
    """返回 (host, db_name)，纯字符串解析（此时还没导入 SQLAlchemy），不打印凭据"""
    from urllib.parse import urlparse

    raw = url if "://" in url else "postgresql://" + url
    parsed = urlparse(raw)
    return (parsed.hostname or "").lower(), (parsed.path or "").lstrip("/").lower()


TEST_HOST, TEST_DB = _split_url(RAW_URL)

# === 安全护栏：Neon 的"环境"靠**分支**区分，而每个分支的库名往往都叫 neondb ===
# 因此不能只看库名：把"显式确认 + 生产指纹比对 + 名称特征"三者一起判，任一不过就拒绝执行。
_refusals: list[str] = []

if os.environ.get("TEST_DB_ACK", "").strip() != ACK_PHRASE:
    _refusals.append(f"未设置 TEST_DB_ACK={ACK_PHRASE}（本套件会 drop_all，必须有显式确认）")

# 如果用户给了生产分支的主机指纹，目标与它相同就直接拒绝（防呆：拿错连接串最容易发生在这一步）
_prod_host = (os.environ.get("PROD_DB_HOST") or "").strip().lower()
if _prod_host and _prod_host == TEST_HOST:
    _refusals.append("目标主机与 PROD_DB_HOST 相同：这看起来是**生产分支**，拒绝执行")

# 名称特征：库名或主机里要能看出是测试环境（Neon 测试分支可命名为 xxx-test，主机随之变化）
_looks_test = any(k in TEST_DB for k in ("test", "dev", "sandbox", "staging")) or any(
    k in TEST_HOST for k in ("test", "dev", "sandbox", "staging")
)
if not _looks_test and os.environ.get("TEST_DB_FORCE_NAME", "") != "1":
    _refusals.append(
        f"库名/主机看不出测试环境（db={TEST_DB or '?'} host={TEST_HOST or '?'}）；"
        "请把测试库名或 Neon 测试分支命名成含 test 的形式，或显式设置 TEST_DB_FORCE_NAME=1"
    )

if _refusals:
    print("拒绝执行（本套件会 drop_all，宁可不动也不能误删生产数据）：")
    for r in _refusals:
        print(f"  - {r}")
    print(f"  目标：host={TEST_HOST or '?'} db={TEST_DB or '?'}（不打印凭据）")
    sys.exit(2)

# 必须在导入 app.database / app.main 之前把配置指向测试库
import app.config as config  # noqa: E402

PG_URL = config.normalize_database_url(RAW_URL)
config.DATABASE_URL = PG_URL
config.DB_BACKEND = "postgresql"
config.IS_SQLITE = False

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.database import Base, SessionLocal, engine, ping  # noqa: E402
from app.main import app  # noqa: E402
from app.migrations import verify_schema  # noqa: E402
from app.models import DailyStat, User, Word  # noqa: E402
from app.services.word_service import init_words  # noqa: E402
from app.wordbook_config import apply_wordbook  # noqa: E402
from testkit import AuthClient  # noqa: E402

# 打印目标（不含凭据），便于确认连对了分支/库
print(f"PostgreSQL 集成测试目标: {engine.url.render_as_string(hide_password=True)}")
print(f"  host={TEST_HOST}  db={TEST_DB}（已通过三道护栏）")


# === 护栏 ③：目标库里若已有业务数据，拒绝 drop_all ===
def _existing_rows() -> dict[str, int]:
    """统计目标库里 users / study_records 的行数（表不存在计 0）"""
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table in ("users", "study_records", "words"):
            exists = conn.execute(
                text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}
            ).scalar()
            if exists:
                counts[table] = int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
    return counts


# 连不上时给可读的结论，而不是把驱动堆栈甩给使用者（也不回显连接串）
try:
    _existing = _existing_rows()
except Exception as exc:  # noqa: BLE001
    print("拒绝执行：无法连接目标数据库，未做任何改动。")
    print(f"  异常类型：{type(exc).__name__}")
    print(f"  目标：host={TEST_HOST or '?'} db={TEST_DB or '?'}（不打印凭据）")
    print("  排查建议：连接串是否完整（含 ?sslmode=require）、Neon 分支是否已创建完成、")
    print("            数据库名是否就是 cet4_test、本机网络是否可达该主机。")
    sys.exit(3)

_business_rows = _existing.get("users", 0) + _existing.get("study_records", 0)

if os.environ.get("TEST_DB_PREFLIGHT", "") == "1":
    print("\nPREFLIGHT（只检查、不删任何东西）：")
    print(f"  已存在的表行数：{_existing or '（无相关表，目标库是空的）'}")
    print(f"  业务数据行数（users+study_records）：{_business_rows}")
    print("  结论：可以安全用于测试" if _business_rows == 0 else "  结论：**不要**用这个库跑测试，请换独立测试库")
    sys.exit(0)

if _business_rows and os.environ.get("TEST_DB_ALLOW_EXISTING", "") != "1":
    print("拒绝执行：目标库里已有业务数据，drop_all 会删掉它们。")
    print(f"  行数：{_existing}")
    print("  请确认这是独立测试库；确实要清空请显式设置 TEST_DB_ALLOW_EXISTING=1。")
    sys.exit(2)

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {detail}" if detail else ""))


# === 1. 建表 + 结构校验（真实 PG 上执行 DDL）===

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
result = verify_schema(engine)
check("PG 建表 + 结构校验通过", result["checked_tables"] >= 6, f"{result['checked_tables']} 张表")

# 幂等：再建一次不应报错
Base.metadata.create_all(bind=engine)
check("create_all 幂等", True)


# === 2. 词库首次导入与词书统计 ===

db = SessionLocal()
try:
    added = init_words(db)
    total = db.query(Word).count()
    check("首次导入词库 4544 词", total == 4544, f"新增 {added}，共 {total}")

    cet4 = apply_wordbook(db.query(Word), Word, "exam_cet4", db).count()
    ielts = apply_wordbook(db.query(Word), Word, "exam_ielts", db).count()
    oxford = apply_wordbook(db.query(Word), Word, "oxford3000", db).count()
    check("词书统计正确（PG 下 ilike 过滤生效）",
          cet4 > 2000 and ielts > 1000 and oxford > 1000,
          f"exam_cet4={cet4} exam_ielts={ielts} oxford3000={oxford}")

    # 再跑一次必须跳过（幂等）
    check("词库导入幂等", init_words(db) == 0)
finally:
    db.close()


# === 3. HTTP 全链路（TestClient 会走 lifespan：create_all + verify_schema + 词库）===

with TestClient(app) as boot:
    health = boot.get("/api/health").json()
    check("健康检查含数据库状态", health.get("db") == "ok" and health.get("backend") == "postgresql", str(health))

    a = AuthClient(app)
    b = AuthClient(app)
    check("注册并登录（A/B 两个用户）", bool(a.email) and bool(b.email) and a.email != b.email,
          f"{a.email} / {b.email}")

    # 跨用户隔离
    overview_b_before = b.get("/api/progress/overview").json()
    check("新用户起点干净", overview_b_before["learned_words"] == 0, str(overview_b_before["learned_words"]))

    today = a.get("/api/study/today?wordbook=exam_cet4&limit=3").json()
    check("取到今日新词", today["total"] == 3, str(today["total"]))
    word_id = today["words"][0]["word"]["id"]
    rec = a.post("/api/study/record", json={"word_id": word_id, "rating": 3})
    check("写入学习记录（FSRS）", rec.status_code == 200 and rec.json()["rating"] == 3, rec.text[:120])

    ov_a = a.get("/api/progress/overview").json()
    ov_b = b.get("/api/progress/overview").json()
    check("A 学过的词只算 A 的", ov_a["learned_words"] == 1 and ov_b["learned_words"] == 0,
          f"A={ov_a['learned_words']} B={ov_b['learned_words']}")

    check("B 看不到 A 的生词本", b.get("/api/starred/ids").json()["stars"] == [])

    # 学习计划
    saved = a.put("/api/plan", json={"goal_type": "ielts", "wordbook_key": "exam_ielts",
                                     "daily_new_words": 25, "target_date": None})
    check("保存学习计划", saved.status_code == 200 and saved.json()["plan"]["daily_new_words"] == 25,
          saved.text[:120])
    fc = a.get("/api/plan/forecast").json()
    check("计划预测使用真实词书总量", fc["wordbook"]["total_words"] == ielts,
          f"{fc['wordbook']['total_words']} vs {ielts}")
    check("B 看不到 A 的计划", b.get("/api/plan").json()["has_plan"] is False)

    # 分级阅读：服务端判分
    import json as _json

    articles = _json.loads((BACKEND_DIR / "app" / "data" / "reading_articles.json").read_text(encoding="utf-8"))["articles"]
    slug = articles[0]["slug"]
    answers = [{"question_id": q["id"], "choice": q["answer"]} for q in articles[0]["questions"]]
    attempt = a.post("/api/reading/attempts", json={"slug": slug, "answers": answers, "duration_seconds": 60})
    body = attempt.json()
    check("阅读记录写入并按服务端答案判分",
          attempt.status_code == 200 and body["score"] == body["total"] == len(answers),
          f"{body.get('score')}/{body.get('total')}")
    check("B 的阅读进度为空", b.get("/api/reading/progress").json()["completed_articles"] == 0)

    # daily_stats 多用户同一天（UNIQUE(user_id, date) 的真实约束验证）
    b.post("/api/study/record", json={"word_id": word_id, "rating": 3})
    db = SessionLocal()
    try:
        from datetime import datetime, timezone

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = db.query(DailyStat).filter(DailyStat.date == today_str).all()
        check("同一天两个用户各有统计行（复合唯一生效）", len(rows) >= 2,
              f"{len(rows)} 行 user_id={[r.user_id for r in rows]}")
    finally:
        db.close()

    # 事务与唯一约束：重复邮箱必须被拒，且会话仍可继续用
    dup = boot.post("/api/auth/csrf")
    _ = dup
    try:
        db = SessionLocal()
        try:
            db.add(User(email=a.email, password_hash="x"))
            db.commit()
            check("重复邮箱被唯一约束拒绝", False, "竟然插入成功")
        except IntegrityError:
            db.rollback()
            check("重复邮箱被唯一约束拒绝", True)
            check("回滚后会话仍可用", db.query(Word).count() == 4544)
        finally:
            db.close()
    finally:
        pass


# === 4. 连接与异常处理 ===

engine.dispose()
check("引擎重连后仍可查询", ping() is True)

bad_engine_url = "postgresql+psycopg://bad:bad@127.0.0.1:1/nope?connect_timeout=2"

bad_engine = create_engine(bad_engine_url, pool_pre_ping=True)
try:
    with bad_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    check("连不上时抛异常（健康检查据此报 degraded）", False, "居然连上了")
except Exception as exc:  # noqa: BLE001
    check("连不上时抛异常（健康检查据此报 degraded）", True, type(exc).__name__)
finally:
    bad_engine.dispose()


# === 5. 收尾：清空测试库 ===

Base.metadata.drop_all(bind=engine)
check("收尾清空测试库", True)

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
