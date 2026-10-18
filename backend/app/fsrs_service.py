"""FSRS 排程封装 — 在 py-fsrs 的卡片状态和本项目的学习记录之间互转

四档评分（对齐 Anki）：1 重来 / 2 困难 / 3 良好 / 4 简单

设计取舍：
    - FSRS 的完整状态用 py-fsrs 自己的 JSON 序列化存进 study_records.fsrs_card 一个列，
      而不是拆成 stability/difficulty/step 多列——少动表结构，回退也简单。
    - next_review_at 继续作为"到期时间"的唯一事实来源（复习队列按它筛选），
      这样已有的查询和界面都不用改。
    - 历史记录没有 stability/difficulty，回填时老实标成 Learning，不伪造记忆强度。
"""

import json
from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler, State

# 调度器单例：FSRS-6 默认参数 + 目标留存率 0.9（与 Anki 默认一致）
_scheduler = Scheduler()

# 评分语义，供后端与前端共用
RATING_LABELS = {1: "重来", 2: "困难", 3: "良好", 4: "简单"}


class InvalidRatingError(ValueError):
    """评分入参非法（既没给 rating 也没给 known，或 rating 越界）"""


def normalize_rating(rating: int | None = None, known: bool | None = None) -> Rating:
    """把入参统一成 fsrs.Rating

    兼容旧的 known:bool 调用：True → 良好(3)，False → 重来(1)。
    两者都没给就抛 InvalidRatingError，绝不静默按某种评分处理。
    """
    if rating is not None:
        # bool 是 int 的子类，显式排除，避免 True 被当成 rating=1
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 4:
            raise InvalidRatingError(f"rating 必须是 1-4 的整数，收到 {rating!r}")
        return Rating(rating)
    if known is not None:
        return Rating.Good if known else Rating.Again
    raise InvalidRatingError("必须提供 rating(1-4) 或 known(bool) 之一")


def parse_dt(value: str | None) -> datetime | None:
    """解析 ISO 时间字符串，统一带上 UTC 时区；无法解析返回 None"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_card(card_json: str | None) -> Card:
    """从库里读回卡片；数据缺失或损坏时退回新卡，不让一次提交整体失败"""
    if not card_json:
        return Card()
    try:
        return Card.from_json(card_json)
    except Exception:
        return Card()


def card_from_legacy(status: str | None, next_review_at: str | None, last_studied_at: str | None) -> str:
    """给迁移之前的历史记录合成一张 FSRS 卡片

    历史数据只有 status 和若干时间戳，没有 stability/difficulty，
    所以标成 Learning 让 FSRS 从头开始估计；但**继承原有到期时间**，
    保证迁移不改变既有的复习计划。
    """
    card = Card()
    card.state = State.Review if status == "known" else State.Learning
    card.step = 0
    inherited_due = parse_dt(next_review_at)
    if inherited_due is not None:
        card.due = inherited_due
    card.last_review = parse_dt(last_studied_at)
    return card.to_json()


def apply_review(card_json: str | None, rating: Rating, now: datetime | None = None):
    """执行一次评分，返回 (新的卡片JSON, 卡片对象, ReviewLog)"""
    now = now or datetime.now(timezone.utc)
    card = load_card(card_json)
    new_card, review_log = _scheduler.review_card(card, rating, now)
    return new_card.to_json(), new_card, review_log


def status_for_card(card: Card) -> str:
    """把 FSRS 状态映射回界面的 new / learning / known

    Review(2) → known：卡片已通过学习步、进入长期复习，界面上算"已掌握"；
    Learning(1)/Relearning(3) → learning。
    """
    return "known" if card.state == State.Review else "learning"


def interval_days(card: Card, now: datetime | None = None) -> float:
    """距下次复习还有多少天（用于前端展示与测试断言）"""
    now = now or datetime.now(timezone.utc)
    return max((card.due - now).total_seconds() / 86400.0, 0.0)


def preview(card_json: str | None, now: datetime | None = None) -> list[dict]:
    """预览四档评分各自会排到什么时候（纯计算，不写库）

    review_card 是纯函数，对同一张卡按四个评分各算一次不会互相影响，
    所以可以在不落库的前提下告诉用户"选哪个会推到几天后"——Anki 的按钮上也显示这个。
    """
    now = now or datetime.now(timezone.utc)
    card = load_card(card_json)
    result = []
    for value, label in RATING_LABELS.items():
        next_card, _log = _scheduler.review_card(card, Rating(value), now)
        result.append(
            {
                "rating": value,
                "label": label,
                "interval_days": round(interval_days(next_card, now), 4),
                "due": next_card.due.isoformat(),
                "fsrs_state": int(next_card.state),
            }
        )
    return result