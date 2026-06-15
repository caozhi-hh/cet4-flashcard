"""学习服务 — 今日学习 + 间隔重复"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import DAILY_NEW_WORDS, KNOW_THRESHOLD, REVIEW_INTERVALS
from ..models import DailyStat, StudyRecord, Word
from ..wordbook_config import apply_wordbook


def get_today_new_words(db: Session, limit: int = DAILY_NEW_WORDS, wordbook_id: str | None = None) -> list[dict]:
    """获取今日新词（尚未学习过的），支持预定义或自定义单词书过滤"""
    learned_ids = db.query(StudyRecord.word_id).subquery()
    query = db.query(Word).filter(Word.id.notin_(learned_ids))
    query = apply_wordbook(query, Word, wordbook_id, db)
    new_words = query.order_by(Word.frequency).limit(limit).all()
    return [_word_to_flashcard(w, "new") for w in new_words]


def get_review_words(db: Session) -> list[dict]:
    """获取待复习的词（到期的 learning 状态词）"""
    now = datetime.now(timezone.utc).isoformat()
    records = (
        db.query(StudyRecord)
        .filter(
            StudyRecord.status == "learning",
            StudyRecord.next_review_at <= now,
        )
        .order_by(StudyRecord.unknown_count.desc())
        .all()
    )
    result = []
    for record in records:
        word = db.query(Word).filter(Word.id == record.word_id).first()
        if word:
            result.append(_word_to_flashcard(word, record.status))
    return result


def submit_study(db: Session, word_id: int, known: bool) -> dict:
    """提交学习结果，更新状态和下次复习时间"""
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

    record.last_studied_at = now.isoformat()
    record.review_count = (record.review_count or 0) + 1

    if known:
        record.know_count = (record.know_count or 0) + 1
        record.unknown_count = 0
        # 连续认识 N 次就标记为 known
        if record.know_count >= KNOW_THRESHOLD:
            record.status = "known"
        else:
            record.status = "learning"
            # 计算下次复习时间（间隔逐渐变长）
            interval_idx = min(record.know_count - 1, len(REVIEW_INTERVALS) - 1)
            days = REVIEW_INTERVALS[interval_idx]
            record.next_review_at = (now + timedelta(days=days)).isoformat()
    else:
        record.know_count = 0
        record.unknown_count = (record.unknown_count or 0) + 1
        record.status = "learning"
        # 不认识 → 1小时后复习
        record.next_review_at = (now + timedelta(hours=1)).isoformat()

    db.commit()

    # 更新每日统计
    _update_daily_stat(db, is_new=(record.review_count == 1))

    return {
        "word_id": word_id,
        "status": record.status,
        "know_count": record.know_count,
        "next_review_at": record.next_review_at,
    }


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
        },
        "status": status,
    }
