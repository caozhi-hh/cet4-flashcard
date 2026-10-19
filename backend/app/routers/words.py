"""词库路由

- 词库（words）是**公共数据**，查询公开即可；
- 但 /init 这类写入型管理接口不得无条件对公众开放：需要管理员令牌（ADMIN_TOKEN），
  未配置该环境变量时一律 403（默认关闭）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..services import word_service

router = APIRouter(prefix="/api/words", tags=["words"])


@router.post("/init", dependencies=[Depends(require_admin)])
def init_words(db: Session = Depends(get_db)):
    """初始化词库（从 JSON 导入）—— 管理接口，需要 X-Admin-Token"""
    count = word_service.init_words(db)
    return {"message": f"导入 {count} 个词", "count": count}


@router.get("/search")
def search_words(q: str = "", limit: int = 20, db: Session = Depends(get_db)):
    """搜索单词（公共词库，无需登录）"""
    words = word_service.search_words(db, q, limit)
    return [
        {
            "id": w.id,
            "word": w.word,
            "phonetic_us": w.phonetic_us,
            "phonetic_uk": w.phonetic_uk,
            "definition": w.definition,
            "pos": w.pos,
            "tags": w.tags,
            "frq": w.frq,
        }
        for w in words
    ]