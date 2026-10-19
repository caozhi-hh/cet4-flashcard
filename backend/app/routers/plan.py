"""学习计划路由

计划属于个人数据：身份**只来自服务端会话**（require_user），不接受客户端传入 user_id。
预测口径 = 当前用户 + 计划所选词书。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import User
from ..services import plan_service
from ..wordbook_config import GOAL_TYPES

router = APIRouter(prefix="/api/plan", tags=["plan"])


class PlanIn(BaseModel):
    goal_type: str
    wordbook_key: str | None = None
    target_date: str | None = None
    daily_new_words: int = Field(default=20)


@router.get("/options")
def plan_options():
    """可选学习目标（含各自默认词书）与每日新词量范围

    放在后端是为了让"目标 → 默认词书"只有一处定义，前端不再重复维护一份映射。
    词书清单本身仍走已有的 GET /api/wordbooks。
    """
    return {
        "goals": [
            {"goal_type": goal, "name": name, "description": desc, "default_wordbook": book}
            for goal, name, desc, book in GOAL_TYPES
        ],
        "daily_new_words_range": {
            "min": plan_service.MIN_DAILY_NEW_WORDS,
            "max": plan_service.MAX_DAILY_NEW_WORDS,
        },
    }


@router.get("")
def get_plan(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """当前用户的学习计划；未设置时返回稳定空状态（has_plan=false, plan=null）"""
    plan = plan_service.get_plan(db, user.id)
    return {
        "has_plan": plan is not None,
        "plan": plan_service.plan_to_dict(plan) if plan else None,
    }


@router.put("")
def put_plan(
    payload: PlanIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """创建或更新当前用户的计划（校验目标/词书/每日量/日期格式）"""
    try:
        plan = plan_service.upsert_plan(
            db,
            user.id,
            goal_type=payload.goal_type,
            wordbook_key=payload.wordbook_key,
            daily_new_words=payload.daily_new_words,
            target_date=payload.target_date,
        )
    except plan_service.InvalidPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"has_plan": True, "plan": plan_service.plan_to_dict(plan)}


@router.get("/forecast")
def get_forecast(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """剩余词汇 / 预计完成 / 目标日期可行性 / FSRS 到期复习负担（只读）"""
    return plan_service.forecast(db, user.id)