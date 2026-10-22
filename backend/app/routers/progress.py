"""进度统计路由

统计口径全部限定在当前登录用户：
    - total 来自公共词库（与用户无关）
    - learned/known 只数**该用户自己**的学习记录
    - today/streak 取自该用户当天的 daily_stats（每用户每天一行）
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import DailyStat, StudyRecord, User, Word
from ..wordbook_config import apply_wordbook

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/overview")
def get_overview(
    wordbook: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """进度总览 — total/learned/known 按当前词书过滤；today/streak 为当前用户当日统计"""
    word_query = apply_wordbook(db.query(Word), Word, wordbook, db, user_id=user.id)
    total = word_query.count()

    # .statement 取出底层 select()：直接传 Subquery 会被 SQLAlchemy 隐式强制转换并告警
    word_ids_subq = word_query.with_entities(Word.id).statement

    # 已学/已掌握：既要落在词书范围内，又只能是当前用户的记录
    learned = (
        db.query(StudyRecord)
        .filter(StudyRecord.user_id == user.id, StudyRecord.word_id.in_(word_ids_subq))
        .count()
    )
    known = (
        db.query(StudyRecord)
        .filter(
            StudyRecord.user_id == user.id,
            StudyRecord.word_id.in_(word_ids_subq),
            StudyRecord.status == "known",
        )
        .count()
    )

    # 今日统计（当前用户，不按词书）
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_stat = (
        db.query(DailyStat)
        .filter(DailyStat.user_id == user.id, DailyStat.date == today)
        .first()
    )

    return {
        "total_words": total,
        "learned_words": learned,
        "known_words": known,
        "today_new": today_stat.new_words if today_stat else 0,
        "today_reviewed": today_stat.reviewed_words if today_stat else 0,
        "streak_days": today_stat.streak_days if today_stat else 0,
    }


@router.get("/calendar")
def get_calendar(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """近 N 天每日学习量（只取当前用户）"""
    stats = (
        db.query(DailyStat)
        .filter(DailyStat.user_id == user.id)
        .order_by(DailyStat.date.desc())
        .limit(days)
        .all()
    )
    return [
        {
            "date": s.date,
            "new_words": s.new_words,
            "reviewed_words": s.reviewed_words,
        }
        for s in reversed(stats)
    ]