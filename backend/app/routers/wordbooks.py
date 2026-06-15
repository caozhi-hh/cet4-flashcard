"""单词书路由 — 预定义 + AI 自定义"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CustomWordbook, Word
from ..services.ai_service import generate_wordbook_config, generate_wordbook_words, refine_word_selection
from ..wordbook_config import WORDBOOK_DEFS, apply_custom_filter, get_preset_filter

router = APIRouter(prefix="/api/wordbooks", tags=["wordbooks"])


def _count_custom(db: Session, wb: CustomWordbook) -> int:
    """计算自定义单词书的词数"""
    keywords = json.loads(wb.keywords) if wb.keywords else []
    return apply_custom_filter(db.query(Word), Word, keywords, wb.pos, wb.freq_max).count()


def _custom_to_dict(db: Session, wb: CustomWordbook) -> dict:
    # 优先用已存的 word_ids 数量（快且准）；为空则查库 fallback
    if wb.word_ids:
        try:
            count = len(json.loads(wb.word_ids))
        except (ValueError, TypeError):
            count = _count_custom(db, wb)
    else:
        count = _count_custom(db, wb)
    return {
        "id": f"custom_{wb.id}",
        "name": wb.name,
        "description": wb.description or "",
        "icon": wb.icon or "✨",
        "color": "#C9A0DC",  # 自定义书用淡紫
        "word_count": count,
        "is_custom": True,
        "query_text": wb.query_text,
    }


@router.get("")
def list_wordbooks(db: Session = Depends(get_db)):
    """获取所有单词书（预定义 + 自定义）"""
    result = []
    # 预定义
    for wb_id, name, desc, icon, color, filter_fn in WORDBOOK_DEFS:
        count = filter_fn(db.query(Word), Word).count()
        result.append({
            "id": wb_id,
            "name": name,
            "description": desc,
            "icon": icon,
            "color": color,
            "word_count": count,
            "is_custom": False,
        })
    # 自定义（AI 生成）
    customs = db.query(CustomWordbook).order_by(CustomWordbook.id.desc()).all()
    for wb in customs:
        result.append(_custom_to_dict(db, wb))
    return result


@router.get("/{wordbook_id}")
def get_wordbook(wordbook_id: str, db: Session = Depends(get_db)):
    """获取单个单词书详情"""
    # 自定义书
    if wordbook_id.startswith("custom_"):
        cid = int(wordbook_id[7:])
        wb = db.query(CustomWordbook).filter(CustomWordbook.id == cid).first()
        if not wb:
            raise HTTPException(status_code=404, detail="单词书不存在")
        return _custom_to_dict(db, wb)
    # 预定义书
    filter_fn = get_preset_filter(wordbook_id)
    if filter_fn is None:
        raise HTTPException(status_code=404, detail="单词书不存在")
    for wb_id, name, desc, icon, color, _ in WORDBOOK_DEFS:
        if wb_id == wordbook_id:
            count = filter_fn(db.query(Word), Word).count()
            return {"id": wb_id, "name": name, "description": desc,
                    "icon": icon, "color": color, "word_count": count, "is_custom": False}
    raise HTTPException(status_code=404, detail="单词书不存在")


class AIGenerateIn(BaseModel):
    query: str


@router.post("/ai-generate")
async def ai_generate(req: AIGenerateIn, db: Session = Depends(get_db)):
    """AI 根据需求直接生成主题单词书

    流程：AI 直接列出主题相关四级词 → 匹配词库 → 存 word_ids
    （若 AI 列词为空，fallback 到粗筛+精选两阶段）
    """
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入单词书需求")

    # 主方案：AI 直接出词
    result = await generate_wordbook_words(query)
    ai_words = result.get("words", [])

    word_ids: list[int] = []
    if ai_words:
        # 用 AI 列出的英文词【精确匹配】词库（不做模糊匹配，避免混入无关词）
        matched = db.query(Word).filter(Word.word.in_(ai_words)).all()
        word_ids = [w.id for w in matched]

    # 兜底：AI 出词失败或匹配为空，用粗筛+精选
    if not word_ids:
        config = await generate_wordbook_config(query)
        keywords = config.get("keywords", [])
        cand_query = apply_custom_filter(
            db.query(Word), Word, keywords,
            config.get("pos", ""), int(config.get("freq_max", 4544) or 4544)
        )
        candidates = [
            {"id": w.id, "word": w.word, "definition": w.definition}
            for w in cand_query.order_by(Word.frequency).all()
        ]
        word_ids = await refine_word_selection(query, candidates)
        name = config.get("name", query[:8] + "词书")
        icon = config.get("icon", "✨")
        keywords_str = json.dumps(keywords, ensure_ascii=False)
        freq_max = int(config.get("freq_max", 4544) or 4544)
    else:
        name = result.get("name", query[:8] + "词书")
        icon = result.get("icon", "✨")
        keywords_str = json.dumps(ai_words[:15], ensure_ascii=False)
        freq_max = 4544

    # 入库
    wb = CustomWordbook(
        name=name[:50],
        description=f"AI 智能生成 · {query[:25]}",
        icon=icon,
        query_text=query,
        keywords=keywords_str,
        word_ids=json.dumps(word_ids),
        pos="",
        freq_max=freq_max,
    )
    db.add(wb)
    db.commit()
    db.refresh(wb)

    return _custom_to_dict(db, wb)


@router.delete("/{wordbook_id}")
def delete_wordbook(wordbook_id: str, db: Session = Depends(get_db)):
    """删除自定义单词书（预定义书不可删）"""
    if not wordbook_id.startswith("custom_"):
        raise HTTPException(status_code=400, detail="预定义单词书不可删除")
    cid = int(wordbook_id[7:])
    wb = db.query(CustomWordbook).filter(CustomWordbook.id == cid).first()
    if not wb:
        raise HTTPException(status_code=404, detail="单词书不存在")
    db.delete(wb)
    db.commit()
    return {"message": "已删除"}
