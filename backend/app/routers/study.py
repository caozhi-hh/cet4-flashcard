"""学习路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..fsrs_service import InvalidRatingError
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
    """获取待复习单词（按到期时间，含已进入长期复习的卡）"""
    review_words = study_service.get_review_words(db)
    return {"type": "review", "words": review_words, "total": len(review_words)}


@router.get("/dictation")
def get_dictation_words(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """默写本章：取今天学过的词（当天没学过则回落到今日新词）。只读，不改数据。"""
    words = study_service.get_dictation_words(db, limit=limit)
    return {"type": "dictation", "words": words, "total": len(words)}


@router.get("/preview")
def preview_ratings(word_id: int, db: Session = Depends(get_db)):
    """预览该词四档评分各自的下次间隔（只读，供卡片按钮显示"1天/4天"这类提示）"""
    try:
        return {"word_id": word_id, "ratings": study_service.preview_ratings(db, word_id)}
    except study_service.UnknownWordError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/record")
def submit_study(record: StudyRecordIn, db: Session = Depends(get_db)):
    """提交学习结果（FSRS 四档评分 rating 1-4；兼容旧的 known:bool）"""
    try:
        return study_service.submit_study(db, record.word_id, rating=record.rating, known=record.known)
    except study_service.UnknownWordError as exc:
        # 词库里没有这个 word_id：拒绝而不是写孤儿记录
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidRatingError as exc:
        # rating 与 known 都没给，或 rating 越界
        raise HTTPException(status_code=422, detail=str(exc))
