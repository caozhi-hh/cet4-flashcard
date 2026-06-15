"""测验路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import QuizSubmit
from ..services import quiz_service

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.get("/daily")
def get_daily_quiz(db: Session = Depends(get_db)):
    """获取今日测验"""
    questions = quiz_service.generate_daily_quiz(db)
    return {"questions": questions, "total": len(questions)}


@router.post("/submit")
def submit_quiz(submit: QuizSubmit, db: Session = Depends(get_db)):
    """提交测验答案"""
    result = quiz_service.check_answers(db, submit.answers)
    return result
