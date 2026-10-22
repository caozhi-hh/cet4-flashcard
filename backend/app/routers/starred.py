"""生词本/错题本路由

所有读写都限定在当前登录用户：查询带 user_id，写入带 user_id，
删除同样按 user_id 过滤（删不到别人的行）。
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import StarredWord, User, Word

router = APIRouter(prefix="/api/starred", tags=["starred"])


class StarIn(BaseModel):
    word_id: int
    type: str = "star"  # star 收藏 / hard 错题


def _word_payload(w: Word, starred_type: str) -> dict:
    return {
        "id": w.id,
        "word": w.word,
        "phonetic_us": w.phonetic_us,
        "phonetic_uk": w.phonetic_uk,
        "definition": w.definition,
        "pos": w.pos,
        "example": w.example,
        "example_cn": w.example_cn,
        "tags": w.tags,
        "frq": w.frq,
        "starred_type": starred_type,
    }


@router.get("")
def list_starred(
    type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """获取当前用户的生词本/错题本（默认全部）"""
    q = db.query(StarredWord).filter(StarredWord.user_id == user.id)
    if type:
        q = q.filter(StarredWord.type == type)
    rows = q.order_by(StarredWord.id.desc()).all()

    word_ids = [r.word_id for r in rows]
    words = db.query(Word).filter(Word.id.in_(word_ids)).all() if word_ids else []
    word_map = {w.id: w for w in words}
    result = [_word_payload(word_map[r.word_id], r.type) for r in rows if r.word_id in word_map]
    return {"words": result, "total": len(result)}


@router.post("")
def add_starred(req: StarIn, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """添加到生词本/错题本（同一用户已存在则忽略）"""
    if not db.query(Word.id).filter(Word.id == req.word_id).first():
        raise HTTPException(status_code=404, detail="单词不存在")

    existing = (
        db.query(StarredWord)
        .filter(
            StarredWord.user_id == user.id,
            StarredWord.word_id == req.word_id,
            StarredWord.type == req.type,
        )
        .first()
    )
    if existing:
        return {"message": "已存在", "exists": True}

    db.add(StarredWord(word_id=req.word_id, user_id=user.id, type=req.type))
    db.commit()
    return {"message": "已添加", "exists": False}


@router.delete("/{word_id}")
def remove_starred(
    word_id: int,
    type: str = "star",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """从当前用户的生词本/错题本移除"""
    rows = (
        db.query(StarredWord)
        .filter(
            StarredWord.user_id == user.id,
            StarredWord.word_id == word_id,
            StarredWord.type == type,
        )
        .all()
    )
    for row in rows:
        db.delete(row)
    db.commit()
    return {"message": "已移除", "count": len(rows)}


@router.get("/ids")
def get_starred_ids(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """获取当前用户已收藏/错题的 word_id（前端快速判断标记状态）"""
    rows = db.query(StarredWord).filter(StarredWord.user_id == user.id).all()
    stars = [r.word_id for r in rows if r.type == "star"]
    hards = [r.word_id for r in rows if r.type == "hard"]
    return {"stars": stars, "hards": hards}