"""分级阅读服务 — 文章内容、分词查词、服务端判分、阅读进度

内容来源：backend/app/data/reading_articles.json（本项目**原创示例**，非官方真题）。

安全边界（本模块是这些规则的唯一落地点）：
    - 取文章详情时**剥掉正确答案**，答案只在提交后随判分结果返回；
    - 判分只依据服务端答案；客户端提交的 score / total / user_id 一律忽略；
    - 查词只做**精确匹配**，避免模糊搜索把相近词误当成释义；
    - 阅读记录一律按 user_id 隔离（来自服务端会话）。
"""

import json
import math
import re
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import READING_JSON
from ..models import ReadingAttempt, StarredWord, StudyRecord, Word
from ..reading.textitems import build_text_items, render_paragraphs

LEVELS = ["A1", "A2", "B1"]
PASS_RATIO = 0.6  # 达到 60% 视为“完成并通过”，仅用于进度展示
HISTORY_LIMIT = 20

_WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*")


class UnknownArticleError(ValueError):
    """slug 对应的文章不存在（由路由层转 404）"""


# === 内容加载 ===

_cache: dict | None = None


def load_content() -> dict:
    """读取文章 JSON（进程内缓存；文件不存在时明确报错，不静默返回空）"""
    global _cache
    if _cache is None:
        if not READING_JSON.exists():
            raise FileNotFoundError(f"阅读文章数据不存在：{READING_JSON}")
        _cache = json.loads(READING_JSON.read_text(encoding="utf-8"))
    return _cache


def all_articles() -> list[dict]:
    return load_content().get("articles", [])


def _article_text(article: dict) -> str:
    return "\n".join(p.get("en", "") for p in article.get("paragraphs", []))


def _word_count(article: dict) -> int:
    return len(_WORD_RE.findall(_article_text(article)))


def get_raw(slug: str) -> dict:
    """取原始文章（**含答案**，仅供服务端内部使用）"""
    for article in all_articles():
        if article.get("slug") == slug:
            return article
    raise UnknownArticleError(f"文章不存在：{slug}")


def _summary(article: dict) -> dict:
    return {
        "slug": article["slug"],
        "title": article["title"],
        "title_zh": article.get("title_zh", ""),
        "level": article.get("level"),
        "topic": article.get("topic", ""),
        "goals": article.get("goals", []),
        "minutes": article.get("minutes"),
        "word_count": _word_count(article),
        "question_count": len(article.get("questions", [])),
        "source": article.get("source", ""),
    }


def list_articles(level: str | None = None, goal: str | None = None) -> dict:
    """文章列表，可按难度与学习目标筛选（都是公共内容，不需要登录）"""
    items = all_articles()
    if level:
        wanted = level.strip().upper()
        if wanted not in LEVELS:
            raise UnknownArticleError(f"不支持的难度：{level}")
        items = [a for a in items if (a.get("level") or "").upper() == wanted]
    if goal:
        items = [a for a in items if goal in (a.get("goals") or [])]
    return {
        "articles": [_summary(a) for a in items],
        "total": len(items),
        "levels": LEVELS,
    }


def public_article(slug: str, db: Session, user_id: int | None) -> dict:
    """文章详情：正文 + 分词渲染项 + 题目（**不含正确答案**）"""
    article = get_raw(slug)
    items = build_text_items(
        [p.get("en", "") for p in article.get("paragraphs", [])],
        terms=_terms_for(db, user_id, _article_text(article)),
    )
    return {
        "article": {
            **_summary(article),
            "paragraphs": [
                {"en": p.get("en", ""), "zh": p.get("zh", "")} for p in article.get("paragraphs", [])
            ],
            # 题目只给题干与选项；answer/explanation 只随提交结果返回
            "questions": [
                {
                    "id": q["id"],
                    "prompt": q["prompt"],
                    "options": list(q["options"]),
                }
                for q in article.get("questions", [])
            ],
        },
        "tokens": render_paragraphs(items),
    }


# === 查词（精确匹配现有词库） ===

def _terms_for(db: Session, user_id: int | None, text: str) -> dict[str, dict]:
    """把正文里出现过的词，用**公共词库**逐个精确匹配，并带上当前用户的掌握状态"""
    wanted = {w.lower() for w in _WORD_RE.findall(text)}
    if not wanted:
        return {}

    rows = db.query(Word).filter(func.lower(Word.word).in_(wanted)).all()
    if not rows:
        return {}

    word_ids = [w.id for w in rows]
    records: dict[int, str] = {}
    starred: set[int] = set()
    if user_id is not None:
        # 只看当前用户自己的记录：别人的掌握状态不能影响我的显示
        records = {
            r.word_id: r.status
            for r in db.query(StudyRecord)
            .filter(StudyRecord.user_id == user_id, StudyRecord.word_id.in_(word_ids))
            .all()
        }
        starred = {
            s.word_id
            for s in db.query(StarredWord)
            .filter(StarredWord.user_id == user_id, StarredWord.word_id.in_(word_ids))
            .all()
        }

    terms: dict[str, dict] = {}
    for w in rows:
        key = w.word.lower()
        status = records.get(w.id) or "new"
        terms[key] = {
            "word_id": w.id,
            "headword": w.word,
            "definition": w.definition,
            "phonetic": w.phonetic_us or w.phonetic_uk,
            "tags": w.tags,
            "frq": w.frq,
            "status": status,
            "starred": w.id in starred,
        }
    return terms


def lookup_word(db: Session, word: str, user_id: int | None) -> dict:
    """点词查义：**只做精确匹配**（不模糊搜索，避免把相近词当成本词）"""
    key = (word or "").strip().lower()
    if not key:
        return {"found": False, "word": word, "message": "请输入要查询的单词"}
    if not _WORD_RE.fullmatch(key):
        return {"found": False, "word": word, "message": "只支持查询单个英文单词"}

    row = db.query(Word).filter(func.lower(Word.word) == key).first()
    if row is None:
        # 明确反馈“未收录”，而不是给一个不相关的近似词
        return {
            "found": False,
            "word": key,
            "message": "词库暂未收录该词，可先加入生词本稍后复习",
        }

    term = _terms_for(db, user_id, key).get(key, {})
    return {"found": True, "word": key, **{k: v for k, v in term.items() if k != "status"}, "status": term.get("status", "new")}


# === 提交与判分 ===

def grade(db: Session, user_id: int, slug: str, answers: list[dict], duration_seconds: int = 0) -> dict:
    """按服务端答案判分并落库

    - 客户端只提供 question_id 与所选序号；分数、总题数、用户身份都由服务端决定；
    - 同一题重复提交只算第一次（防止重复刷分）；
    - 未作答的题计入总题数但不给分。
    """
    article = get_raw(slug)
    questions = article.get("questions", [])
    key = {q["id"]: q for q in questions}

    answered: dict[str, int | None] = {}
    for item in answers or []:
        qid = str(item.get("question_id") or "")
        if qid not in key or qid in answered:
            continue  # 未知题号忽略；重复题号只取第一次
        choice = item.get("choice")
        answered[qid] = choice if isinstance(choice, int) and not isinstance(choice, bool) else None

    score = 0
    detail = []
    for q in questions:
        chosen = answered.get(q["id"])
        correct = chosen is not None and chosen == q["answer"]
        if correct:
            score += 1
        detail.append(
            {
                "question_id": q["id"],
                "chosen": chosen,
                "correct_choice": q["answer"],
                "correct": correct,
                "explanation": q.get("explanation", ""),
            }
        )

    total = len(questions)
    now = datetime.now(timezone.utc)
    attempt = ReadingAttempt(
        user_id=user_id,
        slug=slug,
        level=article.get("level"),
        score=score,
        total=total,
        duration_seconds=max(0, int(duration_seconds or 0)),
        completed_at=now.isoformat(),
        created_at=now.isoformat(),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return {
        "slug": slug,
        "title": article.get("title", ""),
        "level": article.get("level"),
        "score": score,
        "total": total,
        "answered": len(answered),
        "passed": total > 0 and score / total >= PASS_RATIO,
        "duration_seconds": attempt.duration_seconds,
        "completed_at": attempt.completed_at,
        "details": detail,
    }


# === 进度 ===

def progress(db: Session, user_id: int) -> dict:
    """当前用户的阅读完成情况与历史记录（只统计自己的记录）"""
    attempts = (
        db.query(ReadingAttempt)
        .filter(ReadingAttempt.user_id == user_id)
        .order_by(ReadingAttempt.completed_at.desc(), ReadingAttempt.id.desc())
        .all()
    )

    by_slug: dict[str, list[ReadingAttempt]] = {}
    for a in attempts:
        by_slug.setdefault(a.slug, []).append(a)

    articles = all_articles()
    items = []
    completed_slugs: list[str] = []
    passed_slugs: list[str] = []
    for article in articles:
        slug = article["slug"]
        mine = by_slug.get(slug, [])
        if not mine:
            items.append({**_summary(article), "attempts": 0, "best_score": None,
                          "best_total": None, "last_completed_at": None})
            continue
        best = max(mine, key=lambda a: (a.score / a.total) if a.total else 0)
        completed_slugs.append(slug)
        if best.total and best.score / best.total >= PASS_RATIO:
            passed_slugs.append(slug)
        items.append({
            **_summary(article),
            "attempts": len(mine),
            "best_score": best.score,
            "best_total": best.total,
            "last_completed_at": mine[0].completed_at,
            "last_duration_seconds": mine[0].duration_seconds,
        })

    by_level = []
    for level in LEVELS:
        level_items = [i for i in items if i.get("level") == level]
        by_level.append({
            "level": level,
            "total": len(level_items),
            "completed": len([i for i in level_items if i["attempts"] > 0]),
        })

    return {
        "total_articles": len(articles),
        "completed_articles": len(completed_slugs),
        "passed_articles": len(passed_slugs),
        "completed_slugs": completed_slugs,
        "pass_ratio": PASS_RATIO,
        "by_level": by_level,
        "articles": items,
        "history": [
            {
                "slug": a.slug,
                "title": next((x["title"] for x in articles if x["slug"] == a.slug), a.slug),
                "level": a.level,
                "score": a.score,
                "total": a.total,
                "duration_seconds": a.duration_seconds,
                "completed_at": a.completed_at,
            }
            for a in attempts[:HISTORY_LIMIT]
        ],
    }


def estimate_reading_minutes(word_count: int) -> int:
    """按 100 词/分钟粗算阅读时长（用于列表展示，帮助估算成本很低）"""
    return max(1, math.ceil(word_count / 100))