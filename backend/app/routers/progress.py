"""进度统计路由"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DailyStat, StudyRecord, Word
from ..wordbook_config import apply_wordbook

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/overview")
def get_overview(wordbook: str | None = None, db: Session = Depends(get_db)):
    """进度总览 — total/learned/known 按当前词书过滤；today/streak 为全局每日统计"""
    # 按词书过滤的词集
    word_query = apply_wordbook(db.query(Word), Word, wordbook, db)
    total = word_query.count()

    # 当前词书范围内的词 id
    word_ids_subq = word_query.with_entities(Word.id).subquery()

    # 已学/已掌握：StudyRecord 限定在词书范围内
    learned = db.query(StudyRecord).filter(StudyRecord.word_id.in_(word_ids_subq)).count()
    known = (
        db.query(StudyRecord)
        .filter(StudyRecord.word_id.in_(word_ids_subq), StudyRecord.status == "known")
        .count()
    )

    # 今日统计（全局，不按词书）
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_stat = db.query(DailyStat).filter(DailyStat.date == today).first()

    return {
        "total_words": total,
        "learned_words": learned,
        "known_words": known,
        "today_new": today_stat.new_words if today_stat else 0,
        "today_reviewed": today_stat.reviewed_words if today_stat else 0,
        "streak_days": today_stat.streak_days if today_stat else 0,
    }


@router.get("/calendar")
def get_calendar(days: int = 30, db: Session = Depends(get_db)):
    """近 N 天每日学习量"""
    stats = db.query(DailyStat).order_by(DailyStat.date.desc()).limit(days).all()
    return [
        {
            "date": s.date,
            "new_words": s.new_words,
            "reviewed_words": s.reviewed_words,
        }
        for s in reversed(stats)
    ]
