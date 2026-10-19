"""AI 功能路由

AI 调用有成本、且属于个人使用场景，因此要求登录后才能使用。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import User, Word
from ..services.ai_service import generate_mnemonic

router = APIRouter(prefix="/api/ai", tags=["ai"])


class MnemonicRequest(BaseModel):
    word_id: int


@router.post("/mnemonic")
async def get_mnemonic(
    req: MnemonicRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """获取记忆口诀（需登录；词库本身是公共数据）"""
    word = db.query(Word).filter(Word.id == req.word_id).first()
    if not word:
        return {"error": "单词不存在"}

    mnemonic = await generate_mnemonic(
        word=word.word,
        definition=word.definition,
        phonetic=word.phonetic_us or "",
        pos=word.pos or "",
    )
    return {"word_id": word.id, "word": word.word, "mnemonic": mnemonic}