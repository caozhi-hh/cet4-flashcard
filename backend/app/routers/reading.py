"""分级阅读路由

公共内容（文章列表 / 详情 / 查词）不需要登录；个人数据（提交作答、阅读历史）必须登录，
且用户身份**只取服务端会话**。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_user_optional, require_user
from ..database import get_db
from ..models import User
from ..services import reading_service

router = APIRouter(prefix="/api/reading", tags=["reading"])


class AnswerIn(BaseModel):
    question_id: str
    choice: int | None = None


class AttemptIn(BaseModel):
    slug: str
    answers: list[AnswerIn] = Field(default_factory=list)
    duration_seconds: int = 0
    # 注意：这里**没有** score / total / user_id 字段。
    # 客户端即使提交这些字段也不会被采用，分数由服务端依据文章答案计算。


@router.get("/articles")
def list_articles(level: str | None = None, goal: str | None = None):
    """文章列表，支持按难度与学习目标筛选"""
    try:
        return reading_service.list_articles(level=level, goal=goal)
    except reading_service.UnknownArticleError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/articles/{slug}")
def get_article(
    slug: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
):
    """文章详情（正文分词 + 题目，**不含正确答案**）

    未登录也能读：此时所有词的状态按"未学"展示，不涉及任何个人数据。
    """
    try:
        return reading_service.public_article(slug, db, user.id if user else None)
    except reading_service.UnknownArticleError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/lookup")
def lookup_word(
    word: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
):
    """点词查义：只做**精确匹配**，未收录时给出明确反馈"""
    return reading_service.lookup_word(db, word, user.id if user else None)


@router.post("/attempts")
def submit_attempt(
    payload: AttemptIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """提交作答：由服务端判分并保存记录（返回才公布正确答案与解析）"""
    try:
        return reading_service.grade(
            db,
            user.id,
            payload.slug,
            [a.model_dump() for a in payload.answers],
            payload.duration_seconds,
        )
    except reading_service.UnknownArticleError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/progress")
def get_progress(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """当前用户的阅读完成情况与历史记录"""
    return reading_service.progress(db, user.id)