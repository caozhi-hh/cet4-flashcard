"""测验路由

测验题目与错题回写都限定在当前登录用户范围内。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import User
from ..schemas import QuizSubmit
from ..services import quiz_service

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.get("/daily")
def get_daily_quiz(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """获取今日测验（只从当前用户学过的词里出题）"""
    questions = quiz_service.generate_daily_quiz(db, user.id)
    return {"questions": questions, "total": len(questions)}


@router.post("/submit")
def submit_quiz(
    submit: QuizSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """提交测验答案（错题只影响当前用户的学习进度）

    客户端只提交题号与作答；正确答案与得分都由服务端依据词库数据计算。
    """
    return quiz_service.check_answers(db, user.id, [a.model_dump() for a in submit.answers])