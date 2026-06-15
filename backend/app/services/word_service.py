"""词库管理服务"""

import json
import logging

from sqlalchemy.orm import Session

from ..config import WORDS_JSON
from ..models import Word

logger = logging.getLogger(__name__)


def init_words(db: Session) -> int:
    """从 JSON 初始化词库，返回新增数量"""
    count = db.query(Word).count()
    if count > 0:
        logger.info(f"词库已存在 {count} 个词，跳过初始化")
        return 0

    with open(WORDS_JSON, "r", encoding="utf-8") as f:
        words_data = json.load(f)

    for item in words_data:
        db.add(Word(
            word=item["word"],
            phonetic_us=item.get("phonetic_us"),
            phonetic_uk=item.get("phonetic_uk"),
            definition=item["definition"],
            pos=item.get("pos"),
            example=item.get("example"),
            example_cn=item.get("example_cn"),
            frequency=item.get("frequency", 0),
        ))
    db.commit()

    logger.info(f"词库初始化完成，导入 {len(words_data)} 个词")
    return len(words_data)


def get_word(db: Session, word_id: int) -> Word | None:
    return db.query(Word).filter(Word.id == word_id).first()


def search_words(db: Session, query: str, limit: int = 20) -> list[Word]:
    """模糊搜索单词"""
    return db.query(Word).filter(
        Word.word.ilike(f"%{query}%")
    ).limit(limit).all()
