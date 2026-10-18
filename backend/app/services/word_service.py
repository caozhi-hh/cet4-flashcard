"""词库管理服务"""

import json
import logging

from sqlalchemy.orm import Session

from ..config import WORDS_JSON
from ..models import Word

logger = logging.getLogger(__name__)


def init_words(db: Session) -> int:
    """从 JSON 初始化/补齐词库，返回新增数量。

    按 JSON 词数补齐：已有词数不足时导入缺失部分，保证词库始终完整。
    （原先"词库非空就跳过"会导致残留旧数据无法更新到全量。）
    """
    with open(WORDS_JSON, "r", encoding="utf-8") as f:
        words_data = json.load(f)

    existing = db.query(Word).count()
    if existing >= len(words_data):
        logger.info(f"词库已完整 {existing} 个词，跳过初始化")
        return 0

    # 已有词的索引集合，避免重复导入
    existing_words = {w.word for w in db.query(Word.word).all()}
    added = 0
    for item in words_data:
        if item["word"] in existing_words:
            continue
        db.add(Word(
            word=item["word"],
            phonetic_us=item.get("phonetic_us"),
            phonetic_uk=item.get("phonetic_uk"),
            definition=item["definition"],
            pos=item.get("pos"),
            example=item.get("example"),
            example_cn=item.get("example_cn"),
            frequency=item.get("frequency", 0),
            tags=item.get("tags"),
            frq=item.get("frq"),
            bnc=item.get("bnc"),
            collins=item.get("collins"),
            oxford=item.get("oxford"),
        ))
        added += 1
    db.commit()

    logger.info(f"词库补齐完成：原有 {existing}，新增 {added}，共 {existing + added} 个词")
    return added


def backfill_word_enrichment(db: Session) -> int:
    """给已有词补齐 ECDICT 富化字段（tags/frq/bnc/collins/oxford），返回更新条数

    为什么需要它：init_words 只负责"补缺失的词"，不更新已存在的行。
    加列后老数据的这些字段是 NULL，必须回填，否则新词书（按考试标签筛选）会是空的。
    幂等：只处理 tags 仍为 NULL 的行，回填过（含空字符串）就不再重复处理。
    """
    with open(WORDS_JSON, "r", encoding="utf-8") as f:
        by_word = {item["word"]: item for item in json.load(f)}

    updated = 0
    for word in db.query(Word).filter(Word.tags.is_(None)).all():
        item = by_word.get(word.word)
        if not item:
            continue
        word.tags = item.get("tags") or ""
        word.frq = item.get("frq")
        word.bnc = item.get("bnc")
        word.collins = item.get("collins")
        word.oxford = item.get("oxford") or 0
        updated += 1
    if updated:
        db.commit()
        logger.info(f"ECDICT 富化字段回填完成：{updated} 个词")
    return updated


def get_word(db: Session, word_id: int) -> Word | None:
    return db.query(Word).filter(Word.id == word_id).first()


def search_words(db: Session, query: str, limit: int = 20) -> list[Word]:
    """模糊搜索单词"""
    return db.query(Word).filter(
        Word.word.ilike(f"%{query}%")
    ).limit(limit).all()
