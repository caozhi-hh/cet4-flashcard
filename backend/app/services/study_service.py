"""学习服务 — 今日学习 + 间隔重复"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DAILY_NEW_WORDS
from ..fsrs_service import (
    InvalidRatingError,
    apply_review,
    interval_days,
    normalize_rating,
    preview,
    status_for_card,
)
from ..models import DailyStat, StudyRecord, Word
from ..wordbook_config import apply_wordbook
from fsrs import Rating


class UnknownWordError(ValueError):
    """提交了一个词库里不存在的 word_id（由路由层转 404）"""


def get_today_new_words(db: Session, limit: int = DAILY_NEW_WORDS, wordbook_id: str | None = None) -> list[dict]:
    """获取今日新词（尚未学习过的），支持预定义或自定义单词书过滤"""
    # 用 select() 而不是 .subquery()：后者会被 SQLAlchemy 隐式强制转换并告警，
    # 该隐式行为在后续版本会移除。
    learned_ids = select(StudyRecord.word_id)
    query = db.query(Word).filter(Word.id.notin_(learned_ids))
    query = apply_wordbook(query, Word, wordbook_id, db)
    new_words = query.order_by(Word.frequency).limit(limit).all()
    return [_word_to_flashcard(w, "new") for w in new_words]


def get_review_words(db: Session) -> list[dict]:
    """获取待复习的词：**只要到期就取**，不再按 status 过滤

    这条查询是 FSRS 改造后的关键变化：进入 Review 状态的卡片同样会重新到期，
    若仍按 status == "learning" 过滤，这些词会永远不再出现，间隔重复就断了。
    """
    now = datetime.now(timezone.utc).isoformat()
    records = (
        db.query(StudyRecord)
        .filter(
            StudyRecord.next_review_at.isnot(None),
            StudyRecord.next_review_at <= now,
        )
        .order_by(StudyRecord.next_review_at.asc())
        .all()
    )
    result = []
    for record in records:
        word = db.query(Word).filter(Word.id == record.word_id).first()
        if word:
            result.append(_word_to_flashcard(word, record.status))
    return result


def submit_study(db: Session, word_id: int, rating: int | None = None, known: bool | None = None) -> dict:
    """提交学习结果，用 FSRS 计算下次复习时间

    - rating: 1 重来 / 2 困难 / 3 良好 / 4 简单；known 为兼容旧的二值反馈。
    - 先校验 word_id 真实存在：SQLite 默认不强制外键，不校验就会写进孤儿 StudyRecord，
      把 learned_words 统计撑大。
    - 词库里没有该词抛 UnknownWordError（→404）；评分入参非法抛 InvalidRatingError（→422）。
    """
    if not db.query(Word.id).filter(Word.id == word_id).first():
        raise UnknownWordError(f"word_id {word_id} 不存在")

    fsrs_rating = normalize_rating(rating=rating, known=known)

    now = datetime.now(timezone.utc)
    record = db.query(StudyRecord).filter(StudyRecord.word_id == word_id).first()

    if not record:
        record = StudyRecord(
            word_id=word_id,
            status="new",
            know_count=0,
            unknown_count=0,
            review_count=0,
        )
        db.add(record)

    # 交给 FSRS：卡片状态、下次到期时间都以它为准
    card_json, card, _review_log = apply_review(record.fsrs_card, fsrs_rating, now)
    record.fsrs_card = card_json
    record.next_review_at = card.due.isoformat()
    record.last_studied_at = now.isoformat()
    record.review_count = (record.review_count or 0) + 1

    # 兼容字段继续维护，便于统计与回退：只有"重来"算遗忘
    if fsrs_rating == Rating.Again:
        record.know_count = 0
        record.unknown_count = (record.unknown_count or 0) + 1
    else:
        record.know_count = (record.know_count or 0) + 1
        record.unknown_count = 0
    record.status = status_for_card(card)

    db.commit()

    # 更新每日统计
    _update_daily_stat(db, is_new=(record.review_count == 1))

    return {
        "word_id": word_id,
        "rating": int(fsrs_rating),
        "status": record.status,
        "know_count": record.know_count,
        "next_review_at": record.next_review_at,
        "interval_days": round(interval_days(card, now), 4),
        "fsrs_state": int(card.state),
    }


def get_dictation_words(db: Session, limit: int = 20) -> list[dict]:
    """取"刚学完的这一章"用于默写（学完立刻默写的闭环）

    以 last_studied_at 的日期前缀判断"今天学过"：无状态——
    刷新页面、离线重进、换设备都能拿到同一批词，不依赖前端记住本次会话的 word_id。
    当天还没有任何学习记录时，回落到"今日新词"，避免默写页是空的。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records = (
        db.query(StudyRecord)
        .filter(
            StudyRecord.last_studied_at.isnot(None),
            StudyRecord.last_studied_at.like(f"{today}%"),
        )
        .order_by(StudyRecord.last_studied_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for record in records:
        word = db.query(Word).filter(Word.id == record.word_id).first()
        if word:
            result.append(_word_to_flashcard(word, record.status))

    if not result:
        return get_today_new_words(db, limit=limit)
    return result


def preview_ratings(db: Session, word_id: int) -> list[dict]:
    """预览该词四档评分各自的下次间隔（只读，不写库）"""
    if not db.query(Word.id).filter(Word.id == word_id).first():
        raise UnknownWordError(f"word_id {word_id} 不存在")
    record = db.query(StudyRecord).filter(StudyRecord.word_id == word_id).first()
    return preview(record.fsrs_card if record else None)


def _update_daily_stat(db: Session, is_new: bool):
    """更新今日统计"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stat = db.query(DailyStat).filter(DailyStat.date == today).first()

    if not stat:
        # 计算连续学习天数
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_stat = db.query(DailyStat).filter(DailyStat.date == yesterday).first()
        streak = (yesterday_stat.streak_days + 1) if yesterday_stat else 1

        stat = DailyStat(date=today, streak_days=streak)
        db.add(stat)

    if is_new:
        stat.new_words = (stat.new_words or 0) + 1
    else:
        stat.reviewed_words = (stat.reviewed_words or 0) + 1

    db.commit()


def _word_to_flashcard(word: Word, status: str) -> dict:
    return {
        "word": {
            "id": word.id,
            "word": word.word,
            "phonetic_us": word.phonetic_us,
            "phonetic_uk": word.phonetic_uk,
            "definition": word.definition,
            "pos": word.pos,
            "example": word.example,
            "example_cn": word.example_cn,
            # ECDICT 富化字段：前端用来显示考试标签与真实词频
            "tags": word.tags,
            "frq": word.frq,
        },
        "status": status,
    }
