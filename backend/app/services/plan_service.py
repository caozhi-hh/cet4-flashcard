"""学习计划服务 — 用户级计划 + 进度预测

设计要点：
    - 计划是**用户级**的：所有读写都带 user_id，且只从服务端会话取，不接受客户端传入；
    - 预测只统计**当前用户**、并限定在计划所选词书范围内，不混入其他用户的学习记录；
    - 词书引用复用 wordbook_config.apply_wordbook，因此预定义书与本人自定义书都支持；
    - 估算带明确说明（estimate_note），不把结果描述为保证。
"""

import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import CustomWordbook, StudyPlan, StudyRecord, Word
from ..wordbook_config import (
    GOAL_TYPE_IDS,
    WORDBOOK_DEFS,
    apply_wordbook,
    default_wordbook_for_goal,
    get_goal_type,
)

MIN_DAILY_NEW_WORDS = 1
MAX_DAILY_NEW_WORDS = 200
FORECAST_DUE_DAYS = 7

ESTIMATE_NOTE = (
    "估算基于当前每日新词量与已记录的 FSRS 复习计划，实际进度会受复习负担与执行情况影响，不构成保证。"
)


class InvalidPlanError(ValueError):
    """计划入参非法（由路由层转 422）"""


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# === 校验 ===

def validate_goal_type(goal_type: str) -> str:
    value = (goal_type or "").strip()
    if value not in GOAL_TYPE_IDS:
        raise InvalidPlanError(f"不支持的学习目标：{goal_type!r}")
    return value


def validate_daily_new_words(n: int) -> int:
    # bool 是 int 的子类，显式排除，避免 True 被当成 1
    if isinstance(n, bool) or not isinstance(n, int):
        raise InvalidPlanError("每日新词量必须是整数")
    if not (MIN_DAILY_NEW_WORDS <= n <= MAX_DAILY_NEW_WORDS):
        raise InvalidPlanError(f"每日新词量应在 {MIN_DAILY_NEW_WORDS}-{MAX_DAILY_NEW_WORDS} 之间")
    return n


def parse_target_date(raw: str | None) -> str | None:
    """校验 YYYY-MM-DD；空值表示"不设目标日期"

    允许过去日期（由预测标记为不可行），但不接受无法解析的格式。
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise InvalidPlanError("目标日期格式应为 YYYY-MM-DD")
    return parsed.isoformat()


def wordbook_exists(db: Session, wordbook_key: str, user_id: int) -> bool:
    """词书引用必须有效：公共的预定义书，或**当前用户本人**的自定义书"""
    key = (wordbook_key or "").strip()
    if not key:
        return False
    if key.startswith("custom_"):
        try:
            cid = int(key[7:])
        except ValueError:
            return False
        return (
            db.query(CustomWordbook.id)
            .filter(CustomWordbook.id == cid, CustomWordbook.user_id == user_id)
            .first()
            is not None
        )
    return any(wb_id == key for wb_id, *_ in WORDBOOK_DEFS)


# === 计划读写 ===

def get_plan(db: Session, user_id: int) -> StudyPlan | None:
    """当前生效的计划（MVP：每人一份）"""
    return db.query(StudyPlan).filter(StudyPlan.user_id == user_id).first()


def upsert_plan(
    db: Session,
    user_id: int,
    *,
    goal_type: str,
    wordbook_key: str | None,
    daily_new_words: int,
    target_date: str | None,
) -> StudyPlan:
    """创建或更新当前用户的计划（校验失败抛 InvalidPlanError）"""
    goal = validate_goal_type(goal_type)
    daily = validate_daily_new_words(daily_new_words)
    book = (wordbook_key or "").strip() or default_wordbook_for_goal(goal)
    if not wordbook_exists(db, book, user_id):
        raise InvalidPlanError(f"词书不存在或不属于你：{book!r}")
    target = parse_target_date(target_date)

    now = _iso_now()
    plan = get_plan(db, user_id)
    if plan is None:
        plan = StudyPlan(
            user_id=user_id,
            goal_type=goal,
            wordbook_key=book,
            target_date=target,
            daily_new_words=daily,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
    else:
        plan.goal_type = goal
        plan.wordbook_key = book
        plan.target_date = target
        plan.daily_new_words = daily
        plan.updated_at = now
    db.commit()
    db.refresh(plan)
    return plan


def plan_to_dict(plan: StudyPlan) -> dict:
    item = get_goal_type(plan.goal_type)
    return {
        "goal_type": plan.goal_type,
        "goal_name": item[1] if item else plan.goal_type,
        "wordbook_key": plan.wordbook_key,
        "target_date": plan.target_date,
        "daily_new_words": plan.daily_new_words,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


# === 预测 ===

def _wordbook_meta(db: Session, key: str, user_id: int) -> dict:
    """词书名 + 该词书总词数"""
    if key.startswith("custom_"):
        try:
            cid = int(key[7:])
        except ValueError:
            cid = -1
        wb = (
            db.query(CustomWordbook)
            .filter(CustomWordbook.id == cid, CustomWordbook.user_id == user_id)
            .first()
        )
        name = wb.name if wb else "自定义词书"
    else:
        name = next((n for i, n, *_ in WORDBOOK_DEFS if i == key), key)
    total = apply_wordbook(db.query(Word), Word, key, db, user_id=user_id).count()
    return {"key": key, "name": name, "total_words": total}


def due_burden(db: Session, user_id: int, word_ids_subq) -> dict:
    """基于真实 FSRS 到期记录的复习负担（限定当前用户 + 当前词书）"""
    today = _utc_today()
    rows = (
        db.query(StudyRecord.next_review_at)
        .filter(
            StudyRecord.user_id == user_id,
            StudyRecord.next_review_at.isnot(None),
            StudyRecord.word_id.in_(word_ids_subq),
        )
        .all()
    )

    overdue = 0
    due_today = 0
    buckets: dict[date, int] = {}
    for (value,) in rows:
        day_text = (value or "")[:10]
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            continue
        if day < today:
            overdue += 1
        elif day == today:
            due_today += 1
        if today <= day < today + timedelta(days=FORECAST_DUE_DAYS):
            buckets[day] = buckets.get(day, 0) + 1

    next_days = []
    for i in range(FORECAST_DUE_DAYS):
        day = today + timedelta(days=i)
        count = buckets.get(day, 0)
        if i == 0:
            # 逾期的一并算进"今天要还的债"：否则图表显示今天只有 1 张卡，
            # 但用户实际今天必须补 2 张，会低估负担。overdue 仍单独返回，信息不隐藏。
            count += overdue
        next_days.append({"date": day.isoformat(), "count": count})
    return {
        "overdue": overdue,
        "today": due_today,
        "next_7_days": next_days,
        "total_pending": overdue + due_today,
        "scope": "wordbook",  # 负担口径：当前用户 + 当前词书
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def forecast(db: Session, user_id: int) -> dict:
    """当前用户的计划预测；没有计划时返回稳定的空状态（不抛错）"""
    plan = get_plan(db, user_id)
    if plan is None:
        return {
            "has_plan": False,
            "plan": None,
            "wordbook": None,
            "learned_words": 0,
            "remaining_new_words": None,
            "days_to_finish": None,
            "estimated_finish_date": None,
            "target": None,
            "due": None,
            "estimate_note": ESTIMATE_NOTE,
            "generated_at": _iso_now(),
        }

    meta = _wordbook_meta(db, plan.wordbook_key, user_id)
    scope = apply_wordbook(db.query(Word), Word, plan.wordbook_key, db, user_id=user_id)
    subq = scope.with_entities(Word.id).statement

    learned = (
        db.query(StudyRecord)
        .filter(StudyRecord.user_id == user_id, StudyRecord.word_id.in_(subq))
        .count()
    )
    total = meta["total_words"]
    remaining = max(total - learned, 0)

    daily = plan.daily_new_words or 0
    if remaining == 0:
        days_to_finish: int | None = 0
    elif daily > 0:
        days_to_finish = math.ceil(remaining / daily)
    else:
        days_to_finish = None  # 数据异常（每日量为 0）时不做估算，而不是除零

    today = _utc_today()
    estimated_finish = (
        (today + timedelta(days=days_to_finish)).isoformat() if days_to_finish is not None else None
    )

    target = None
    if plan.target_date:
        try:
            target_day = date.fromisoformat(plan.target_date)
        except ValueError:
            target_day = None
        if target_day is not None:
            days_available = (target_day - today).days
            if days_available < 0:
                feasible: bool | None = False
                reason = "目标日期已过"
            elif remaining == 0:
                feasible = True
                reason = "该词书已学完"
            elif days_to_finish is None:
                feasible = None
                reason = "缺少有效的每日新词量，无法估算"
            else:
                feasible = days_to_finish <= days_available
                reason = (
                    f"剩余 {remaining} 个新词 ÷ 每天 {daily} 词 ≈ {days_to_finish} 天；"
                    f"距目标日还有 {days_available} 天"
                )
            target = {
                "date": target_day.isoformat(),
                "days_available": days_available,
                "feasible": feasible,
                "reason": reason,
            }

    return {
        "has_plan": True,
        "plan": plan_to_dict(plan),
        "wordbook": meta,
        "learned_words": learned,
        "remaining_new_words": remaining,
        "days_to_finish": days_to_finish,
        "estimated_finish_date": estimated_finish,
        "target": target,
        "due": due_burden(db, user_id, subq),
        "estimate_note": ESTIMATE_NOTE,
        "generated_at": _iso_now(),
    }