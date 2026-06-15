"""生词本/错题本路由"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import StarredWord, Word

router = APIRouter(prefix="/api/starred", tags=["starred"])


class StarIn(BaseModel):
    word_id: int
    type: str = "star"  # star 收藏 / hard 错题


@router.get("")
def list_starred(type: str | None = None, db: Session = Depends(get_db)):
    """获取生词本/错题本列表（默认全部）"""
    q = db.query(StarredWord)
    if type:
        q = q.filter(StarredWord.type == type)
    rows = q.order_by(StarredWord.id.desc()).all()
    word_ids = [r.word_id for r in rows]
    words = db.query(Word).filter(Word.id.in_(word_ids)).all() if word_ids else []
    word_map = {w.id: w for w in words}
    result = []
    for r in rows:
        w = word_map.get(r.word_id)
        if w:
            result.append({
                "id": w.id, "word": w.word,
                "phonetic_us": w.phonetic_us, "phonetic_uk": w.phonetic_uk,
                "definition": w.definition, "pos": w.pos,
                "example": w.example, "example_cn": w.example_cn,
                "starred_type": r.type,
            })
    return {"words": result, "total": len(result)}


@router.post("")
def add_starred(req: StarIn, db: Session = Depends(get_db)):
    """添加到生词本/错题本（已存在则忽略）"""
    existing = db.query(StarredWord).filter(
        StarredWord.word_id == req.word_id, StarredWord.type == req.type
    ).first()
    if existing:
        return {"message": "已存在", "exists": True}
    row = StarredWord(word_id=req.word_id, type=req.type)
    db.add(row)
    db.commit()
    return {"message": "已添加", "exists": False}


@router.delete("/{word_id}")
def remove_starred(word_id: int, type: str = "star", db: Session = Depends(get_db)):
    """从生词本/错题本移除"""
    rows = db.query(StarredWord).filter(
        StarredWord.word_id == word_id, StarredWord.type == type
    ).all()
    for r in rows:
        db.delete(r)
    db.commit()
    return {"message": "已移除", "count": len(rows)}


@router.get("/ids")
def get_starred_ids(db: Session = Depends(get_db)):
    """获取所有已收藏/错题的 word_id（前端快速判断标记状态）"""
    rows = db.query(StarredWord).all()
    stars = [r.word_id for r in rows if r.type == "star"]
    hards = [r.word_id for r in rows if r.type == "hard"]
    return {"stars": stars, "hards": hards}
