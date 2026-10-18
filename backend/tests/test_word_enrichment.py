"""ECDICT 词库富化测试 — 数据质量、迁移回填、按标签/词频的词书

红灯背景（富化前）：
    words 表没有 tags/frq/bnc/collins/oxford 列；`frequency` 只是 1..N 的排序序号，
    没有真实语料词频，也没有任何考试标签，所以词书只能靠序号切（"前 1000 高频"其实不是高频）。

数据安全约定：
    写入只发生在 backend/tests/.tmp-enrich/；真实库只在"复制一份"之后用于迁移路径验证。

运行：python tests/test_word_enrichment.py
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

TMP_DIR = BACKEND_DIR / "tests" / ".tmp-enrich"
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

client = TestClient(app)

REAL_DB = Path(r"D:\data\cet4.db")
WORDS_JSON = BACKEND_DIR / "app" / "data" / "cet4_words.json"
ENRICH_COLUMNS = ["tags", "frq", "bnc", "collins", "oxford"]


def _columns(db: Path, table: str) -> list[str]:
    con = sqlite3.connect(str(db))
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    con.close()
    return cols


# === 1. 富化后的词库数据质量 ===

def test_words_json_is_enriched():
    """词库 JSON 必须带上 tags/frq，且没有丢词"""
    data = json.loads(WORDS_JSON.read_text(encoding="utf-8"))
    assert len(data) == 4544, f"词数变化：{len(data)}"

    tagged = sum(1 for w in data if (w.get("tags") or "").strip())
    with_frq = sum(1 for w in data if w.get("frq"))
    assert tagged >= 4300, f"带考试标签的词太少：{tagged}"
    assert with_frq >= 4400, f"带 COCA 词频的词太少：{with_frq}"

    # 标签必须来自固定词表，否则 LIKE 匹配会不可靠
    allowed = {"zk", "gk", "cet4", "cet6", "ky", "toefl", "ielts", "gre"}
    bad = [w["word"] for w in data if set((w.get("tags") or "").split()) - allowed]
    assert not bad, f"出现未在白名单内的标签：{bad[:5]}"


def test_missing_phonetics_were_filled():
    """富化应补上 ECDICT 能提供的缺失音标（富化前有 102 个词缺 phonetic_us）"""
    data = json.loads(WORDS_JSON.read_text(encoding="utf-8"))
    missing = [w["word"] for w in data if not (w.get("phonetic_us") or w.get("phonetic_uk"))]
    assert len(missing) <= 60, f"仍缺音标的词过多：{len(missing)} 个（富化前为 102）"


# === 2. 新库导入即带富化字段 ===

def test_fresh_db_has_enrichment():
    """全新库由 init_words 导入时，富化字段应当一并写入"""
    con = sqlite3.connect(str(config.DB_PATH))
    cols = [r[1] for r in con.execute("PRAGMA table_info(words)")]
    for c in ENRICH_COLUMNS:
        assert c in cols, f"words 表缺列 {c}"
    n_words = con.execute("select count(*) from words").fetchone()[0]
    n_tags = con.execute("select count(*) from words where tags is not null and tags != ''").fetchone()[0]
    n_frq = con.execute("select count(*) from words where frq is not null and frq > 0").fetchone()[0]
    row = con.execute("select tags, frq, collins, oxford from words where word='abandon'").fetchone()
    con.close()

    assert n_words == 4544, n_words
    assert n_tags >= 4300, f"库里有标签的词太少：{n_tags}"
    assert n_frq >= 4400, f"库里有词频的词太少：{n_frq}"
    assert row and "cet4" in (row[0] or ""), f"abandon 应带 cet4 标签，实际 {row}"


def test_word_api_exposes_enrichment():
    """接口返回的词条要带上 tags 与 frq，前端才能显示标签和词频"""
    words = client.get("/api/study/today?wordbook=all&limit=30").json()["words"]
    assert words, "取不到词"
    got = words[0]["word"]
    assert "tags" in got, f"词条缺少 tags 字段：{list(got.keys())}"
    assert "frq" in got, f"词条缺少 frq 字段：{list(got.keys())}"


# === 3. 按考试标签 / 真实词频的词书 ===

def test_exam_wordbooks_exist_with_words():
    """新增的按标签/词频的词书必须真实存在且有词"""
    books = {b["id"]: b for b in client.get("/api/wordbooks").json()}
    for wid in ("exam_cet4", "exam_cet6", "exam_ky", "coca1000", "collins4", "oxford3000"):
        assert wid in books, f"缺少词书 {wid}"
        assert books[wid]["word_count"] > 0, f"{wid} 词数为 0：{books[wid]}"

    # 数量应接近富化时的统计（cet4 3394 / cet6 3290 / ky 3361）
    assert 3000 < books["exam_cet4"]["word_count"] < 3600, books["exam_cet4"]["word_count"]
    assert books["coca1000"]["word_count"] == 1000, books["coca1000"]["word_count"]


def test_cet4_wordbook_only_returns_cet4_words():
    """exam_cet4 词书里的词必须都带 cet4 标签（LIKE 匹配不能误伤）"""
    words = client.get("/api/study/today?wordbook=exam_cet4&limit=50").json()["words"]
    assert words, "exam_cet4 取不到词"
    offenders = [w["word"]["word"] for w in words if "cet4" not in (w["word"].get("tags") or "").split()]
    assert not offenders, f"exam_cet4 里混入了非 cet4 词：{offenders[:5]}"


def test_coca_wordbook_respects_threshold():
    """coca1000 的词 freq(COCA) 必须 <= 1397"""
    words = client.get("/api/study/today?wordbook=coca1000&limit=50").json()["words"]
    assert words, "coca1000 取不到词"
    bad = [w["word"]["word"] for w in words if not (w["word"].get("frq") or 0) or w["word"]["frq"] > 1397]
    assert not bad, f"coca1000 混入了低频词：{bad[:5]}"


def test_core1000_unchanged():
    """老词书（按序号切）必须保持原样——不能因为富化而改变用户既有的学习范围"""
    books = {b["id"]: b for b in client.get("/api/wordbooks").json()}
    assert books["core1000"]["word_count"] == 1000, books["core1000"]
    assert books["core2000"]["word_count"] == 2000, books["core2000"]


# === 4. 真实库的迁移路径（只动副本） ===

def _make_legacy_db(path: Path, words: list[str]) -> None:
    """造一个"富化前"的库：words 表没有 tags/frq/… 列，插入若干真实存在的词。

    不直接用真实库副本的原因：真实库迁移过之后就不再有"缺列"状态，
    断言"本次一定加了列/一定回填了 N 行"会随外部状态时红时绿。
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
    for i, w in enumerate(words, start=1):
        con.execute(
            "insert into words (word, definition, frequency) values (?,?,?)",
            (w, f"n. 旧释义 {w}", i),
        )
    con.commit()
    con.close()


def test_enrichment_migration_on_legacy_schema():
    """迁移前 schema：应加上富化列、回填 tags/frq、幂等、且产生备份"""
    data = json.loads(WORDS_JSON.read_text(encoding="utf-8"))
    sample = [w["word"] for w in data[:30] if (w.get("tags") or "").strip()]
    assert sample, "词库 JSON 里没有带标签的词，无法构造成用例"

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.migrations import ensure_word_enrichment_schema
    from app.services.word_service import backfill_word_enrichment

    legacy = TMP_DIR / "legacy-enrich.db"
    _make_legacy_db(legacy, sample)
    backup_dir = TMP_DIR / "backups-enrich"
    assert "tags" not in _columns(legacy, "words"), "构造的旧库不该有 tags 列"

    eng = create_engine(f"sqlite:///{legacy}", connect_args={"check_same_thread": False})
    Session2 = sessionmaker(bind=eng)
    try:
        result = ensure_word_enrichment_schema(eng, backup_dir=backup_dir)
        assert sorted(result["added_columns"]) == sorted(ENRICH_COLUMNS), result
        assert result["backed_up"], "新增列前没有备份"
        assert Path(result["backed_up"]).exists(), "备份文件不存在"
        for c in ENRICH_COLUMNS:
            assert c in _columns(legacy, "words"), f"迁移后仍缺列 {c}"

        session = Session2()
        try:
            filled = backfill_word_enrichment(session)
            again = backfill_word_enrichment(session)
        finally:
            session.close()
        assert filled == len(sample), f"回填条数应为 {len(sample)}，实际 {filled}"
        assert again == 0, f"回填不幂等，第二次又改了 {again} 行"

        # 第二次加列调用必须是 no-op
        again_schema = ensure_word_enrichment_schema(eng, backup_dir=backup_dir)
        assert again_schema["added_columns"] == [], again_schema
        assert len(list(backup_dir.glob("*"))) == 1, "幂等重跑不该再产生备份"
    finally:
        eng.dispose()

    con = sqlite3.connect(str(legacy))
    n_tags = con.execute("select count(*) from words where tags is not null and tags != ''").fetchone()[0]
    n_frq = con.execute("select count(*) from words where frq is not null").fetchone()[0]
    con.close()
    assert n_tags == len(sample), f"回填后带标签的词数不对：{n_tags}"
    assert n_frq > 0, "frq 未回填"


def test_enrichment_migration_keeps_real_data():
    """对真实库副本执行迁移：计数与主键集合必须完全不变（不依赖真实库当前是否已迁移）"""
    assert REAL_DB.exists(), f"找不到真实库 {REAL_DB}"
    copy_db = TMP_DIR / "enrich-copy.db"
    shutil.copy(REAL_DB, copy_db)

    con = sqlite3.connect(str(copy_db))
    before_n = con.execute("select count(*) from words").fetchone()[0]
    before_ids = [r[0] for r in con.execute("select id from words order by id limit 200")]
    con.close()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.migrations import ensure_word_enrichment_schema
    from app.services.word_service import backfill_word_enrichment

    eng = create_engine(f"sqlite:///{copy_db}", connect_args={"check_same_thread": False})
    Session2 = sessionmaker(bind=eng)
    try:
        ensure_word_enrichment_schema(eng, backup_dir=TMP_DIR / "backups")
        session = Session2()
        try:
            first = backfill_word_enrichment(session)
            second = backfill_word_enrichment(session)
        finally:
            session.close()
    finally:
        eng.dispose()

    assert second == 0, f"回填不幂等，第二次又改了 {second} 行"

    con = sqlite3.connect(str(copy_db))
    after_n = con.execute("select count(*) from words").fetchone()[0]
    after_ids = [r[0] for r in con.execute("select id from words order by id limit 200")]
    n_tags = con.execute("select count(*) from words where tags is not null and tags != ''").fetchone()[0]
    con.close()

    assert before_n == after_n, f"词数变化 {before_n} -> {after_n}"
    assert before_ids == after_ids, "words 主键集合变化"
    assert n_tags >= 4300, f"迁移后带标签的词太少：{n_tags}（首次回填 {first} 行）"


def test_real_database_untouched_by_tests():
    """测试只写临时库"""
    assert str(config.DB_PATH).startswith(str(TMP_DIR)), config.DB_PATH
    if REAL_DB.exists():
        con = sqlite3.connect(str(REAL_DB))
        n = con.execute("select count(*) from words").fetchone()[0]
        con.close()
        assert n == 4544, f"真实库 words 计数变了：{n}"


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