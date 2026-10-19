"""单词书路由 — 预定义（公共）+ AI 自定义（按用户隔离）

访问控制：
    - 预定义词书是公共数据，未登录也能查（前端未登录时只展示这些）；
    - 自定义词书只能由**创建它的用户**列出、查看、删除；
      查询别人（或不存在）的 custom_id 一律 404，不泄露是否存在。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import current_user_optional, require_user
from ..database import get_db
from ..models import CustomWordbook, User, Word
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


def _get_owned_custom(db: Session, wordbook_id: str, user: User | None) -> CustomWordbook:
    """取出属于当前用户的自定义词书；不存在/不属于自己/未登录都按 404 处理"""
    try:
        cid = int(wordbook_id[7:])
    except ValueError:
        raise HTTPException(status_code=404, detail="单词书不存在")
    if user is None:
        raise HTTPException(status_code=404, detail="单词书不存在")
    wb = (
        db.query(CustomWordbook)
        .filter(CustomWordbook.id == cid, CustomWordbook.user_id == user.id)
        .first()
    )
    if not wb:
        raise HTTPException(status_code=404, detail="单词书不存在")
    return wb


@router.get("")
def list_wordbooks(
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
):
    """获取单词书列表：预定义（公共）+ 当前用户的自定义书"""
    result = []
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

    if user is not None:
        customs = (
            db.query(CustomWordbook)
            .filter(CustomWordbook.user_id == user.id)
            .order_by(CustomWordbook.id.desc())
            .all()
        )
        for wb in customs:
            result.append(_custom_to_dict(db, wb))
    return result


@router.get("/{wordbook_id}")
def get_wordbook(
    wordbook_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
):
    """获取单个单词书详情（自定义书仅限本人）"""
    if wordbook_id.startswith("custom_"):
        return _custom_to_dict(db, _get_owned_custom(db, wordbook_id, user))

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
async def ai_generate(
    req: AIGenerateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """AI 根据需求直接生成主题单词书（归属当前用户）

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

    # 入库（带 user_id，之后只有本人能看到）
    wb = CustomWordbook(
        name=name[:50],
        description=f"AI 智能生成 · {query[:25]}",
        icon=icon,
        query_text=query,
        keywords=keywords_str,
        word_ids=json.dumps(word_ids),
        pos="",
        freq_max=freq_max,
        user_id=user.id,
    )
    db.add(wb)
    db.commit()
    db.refresh(wb)

    return _custom_to_dict(db, wb)


@router.delete("/{wordbook_id}")
def delete_wordbook(
    wordbook_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """删除自定义单词书（预定义书不可删；只能删自己的）"""
    if not wordbook_id.startswith("custom_"):
        raise HTTPException(status_code=400, detail="预定义单词书不可删除")
    wb = _get_owned_custom(db, wordbook_id, user)
    db.delete(wb)
    db.commit()
    return {"message": "已删除"}