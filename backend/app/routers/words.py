"""词库路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import word_service

router = APIRouter(prefix="/api/words", tags=["words"])


@router.post("/init")
def init_words(db: Session = Depends(get_db)):
    """初始化词库（从 JSON 导入）"""
    count = word_service.init_words(db)
    return {"message": f"导入 {count} 个词", "count": count}


@router.get("/search")
def search_words(q: str = "", limit: int = 20, db: Session = Depends(get_db)):
    """搜索单词"""
    words = word_service.search_words(db, q, limit)
    return [
        {
            "id": w.id,
            "word": w.word,
            "phonetic_us": w.phonetic_us,
            "phonetic_uk": w.phonetic_uk,
            "definition": w.definition,
            "pos": w.pos,
        }
        for w in words
    ]
