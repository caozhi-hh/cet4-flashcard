"""AI 功能路由

AI 调用有真实成本：要求登录 + 按用户限流（内存滑窗，见 services/rate_limit.py）。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_user
from ..config import AI_MNEMONIC_LIMIT, AI_RATE_WINDOW_SECONDS
from ..database import get_db
from ..models import User, Word
from ..services.ai_service import generate_mnemonic
from ..services.rate_limit import ai_rate_limit

router = APIRouter(prefix="/api/ai", tags=["ai"])


class MnemonicRequest(BaseModel):
    word_id: int


@router.post(
    "/mnemonic",
    dependencies=[Depends(ai_rate_limit("ai_mnemonic", AI_MNEMONIC_LIMIT, AI_RATE_WINDOW_SECONDS))],
)
async def get_mnemonic(
    req: MnemonicRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """获取记忆口诀（需登录 + 限流；词库本身是公共数据）"""
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