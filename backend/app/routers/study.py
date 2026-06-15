"""学习路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import StudyRecordIn
from ..services import study_service

router = APIRouter(prefix="/api/study", tags=["study"])


@router.get("/today")
def get_today_words(wordbook: str | None = None, limit: int | None = None, db: Session = Depends(get_db)):
    """获取今日学习单词，可选指定单词书和每日数量"""
    new_words = study_service.get_today_new_words(db, limit=limit or 20, wordbook_id=wordbook)
    return {"type": "new", "words": new_words, "total": len(new_words)}


@router.get("/review")
def get_review_words(db: Session = Depends(get_db)):
    """获取待复习单词"""
    review_words = study_service.get_review_words(db)
    return {"type": "review", "words": review_words, "total": len(review_words)}


@router.post("/record")
def submit_study(record: StudyRecordIn, db: Session = Depends(get_db)):
    """提交学习结果（认识/不认识）"""
    result = study_service.submit_study(db, record.word_id, record.known)
    return result
