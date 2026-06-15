"""单词书配置 — 预定义热门四级单词书

单词书是虚拟的（不存数据库），按配置动态过滤 Word 查询。
filter_func 接收 (query, model) 参数，返回过滤后的 query。
"""


def _filter_all(query, Word):
    return query


def _filter_freq_le(max_freq):
    def _f(query, Word):
        return query.filter(Word.frequency <= max_freq)
    return _f


def _filter_freq_range(lo, hi):
    def _f(query, Word):
        return query.filter(Word.frequency.between(lo, hi))
    return _f


def _filter_pos(pos_str):
    def _f(query, Word):
        return query.filter(Word.pos.like(f"%{pos_str}%"))
    return _f


# ===== 单词书定义 =====
# (id, name, description, icon, color, filter_func)
WORDBOOK_DEFS = [
    ("all",          "四级大纲全词汇",      "完整四级大纲 4500+ 词汇，系统掌握",          "📚", "#D4A574", _filter_all),
    ("core1000",     "高频核心 1000 词",    "考试最高频 1000 词，先背这些拿基础分",       "🔥", "#E8A87C", _filter_freq_le(1000)),
    ("core2000",     "高频核心 2000 词",    "覆盖 90% 考试词汇，稳过四级",                "⭐", "#F5DEB3", _filter_freq_le(2000)),
    ("verbs",        "动词专练",           "四级核心动词，攻克阅读理解",                  "🏃", "#A8D8B9", _filter_pos("v")),
    ("nouns",        "名词专练",           "四级核心名词，扩大词汇量",                    "📖", "#F4A6A6", _filter_pos("n")),
    ("adj",          "形容词专练",          "四级核心形容词，提升表达能力",                 "🎨", "#C9A0DC", _filter_pos("adj")),
    ("breakthrough", "进阶突破 2000 词",    "中频进阶词汇 (1001-3000)，冲击高分",          "🚀", "#7FC8A9", _filter_freq_range(1001, 3000)),
]

# 默认单词书
DEFAULT_WORDBOOK = "core1000"


def get_preset_filter(wordbook_id: str):
    """获取预定义单词书的 filter_func，不存在返回 None"""
    for wid, _, _, _, _, filter_fn in WORDBOOK_DEFS:
        if wid == wordbook_id:
            return filter_fn
    return None


def apply_custom_filter(query, Word, keywords: list[str], pos: str = "", freq_max: int = 4544):
    """应用自定义单词书筛选条件

    - keywords: 在 definition 中 OR 匹配（任一关键词命中即入选）
    - pos: 词性过滤（支持 v/n/adj/adv，多词性 / 分隔）
    - freq_max: 词频上限
    """
    from sqlalchemy import or_

    # 关键词匹配（definition 或 example 包含任一关键词）
    if keywords:
        conditions = []
        for kw in keywords:
            kw = kw.strip()
            if kw:
                conditions.append(Word.definition.like(f"%{kw}%"))
                if hasattr(Word, "example_cn") and Word.example_cn:
                    conditions.append(Word.example_cn.like(f"%{kw}%"))
        if conditions:
            query = query.filter(or_(*conditions))

    # 词性过滤
    if pos and pos.strip():
        pos_parts = [p.strip() for p in pos.split("/") if p.strip()]
        if len(pos_parts) == 1:
            query = query.filter(Word.pos.like(f"%{pos_parts[0]}%"))
        elif pos_parts:
            query = query.filter(or_(*[Word.pos.like(f"%{p}%") for p in pos_parts]))

    # 词频上限
    if freq_max and freq_max < 4544:
        query = query.filter(Word.frequency <= freq_max)

    return query


def apply_wordbook(query, Word, wordbook_id: str | None, db) -> "Query":
    """统一应用词书过滤（预定义或自定义），返回过滤后的 query。

    - wordbook_id 为 None 或空 → 用默认书
    - custom_ 前缀 → 优先用 AI 精选的 word_ids；无则 fallback 到关键词过滤
    - 其他 → 预定义书
    """
    import json as _json
    wb_id = wordbook_id or DEFAULT_WORDBOOK

    if wb_id.startswith("custom_"):
        from .models import CustomWordbook
        try:
            cid = int(wb_id[7:])
        except ValueError:
            return query
        wb = db.query(CustomWordbook).filter(CustomWordbook.id == cid).first()
        if not wb:
            return query
        # 优先用 AI 精选的 word_ids
        word_ids = _json.loads(wb.word_ids) if wb.word_ids else None
        if word_ids:
            return query.filter(Word.id.in_(word_ids))
        # fallback：关键词过滤
        keywords = _json.loads(wb.keywords) if wb.keywords else []
        return apply_custom_filter(query, Word, keywords, wb.pos, wb.freq_max)

    filter_fn = get_preset_filter(wb_id)
    if filter_fn:
        return filter_fn(query, Word)
    return query
