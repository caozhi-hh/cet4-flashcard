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


def _filter_tag(tag: str):
    """按 ECDICT 考试标签筛选。

    tags 存的是空格分隔的固定词表（zk gk cet4 cet6 ky toefl ielts gre），
    这些标签互不为子串（如 cet4 与 cet6 不同、ky 与 gk 不同），所以 LIKE '%tag%' 不会误匹配。
    """
    def _f(query, Word):
        return query.filter(Word.tags.like(f"%{tag}%"))
    return _f


def _filter_coca_top(threshold: int):
    """按 COCA 真实语料词频取前 N 高频。

    这里用"词频序号 <= 阈值"而不是 .limit(N)：apply_wordbook 既用于取词也用于统计总数，
    在 filter 里塞 limit 会让 total/learned 统计失真。
    阈值由富化后的数据算出（见 scripts/enrich_words_from_ecdict.py 输出）：
      前 500 → frq ≤ 726，前 1000 → frq ≤ 1397，前 2000 → frq ≤ 2810
    """
    def _f(query, Word):
        return query.filter(Word.frq.isnot(None), Word.frq > 0, Word.frq <= threshold)
    return _f


def _filter_min_collins(stars: int):
    """柯林斯星级 ≥ stars（4 星以上 1267 词，5 星 448 词）"""
    def _f(query, Word):
        return query.filter(Word.collins.isnot(None), Word.collins >= stars)
    return _f


def _filter_oxford(query, Word):
    """牛津核心 3000（2535 词）"""
    return query.filter(Word.oxford == 1)


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
    # === 以下按 ECDICT 的考试标签与真实语料词频筛选（数据来源见 scripts/enrich_words_from_ecdict.py）===
    ("exam_cet4",    "四级考纲标注词",      "ECDICT 标注 cet4 的 3300+ 词，最贴近考纲",    "🎯", "#D98F8F", _filter_tag("cet4")),
    ("exam_cet6",    "六级拓展词",          "ECDICT 标注 cet6 的词，四级后继续拔高",       "📈", "#8FA8D9", _filter_tag("cet6")),
    ("exam_ky",      "考研核心词",          "ECDICT 标注 ky（考研）的词，重合度极高",      "🎓", "#B9A8D8", _filter_tag("ky")),
    ("coca1000",     "真·高频 1000（COCA）", "按 COCA 语料真实词频排的 1000 词（frq≤1397）", "📊", "#7FC8A9", _filter_coca_top(1397)),
    ("collins4",     "柯林斯 4 星以上",      "柯林斯词典 4-5 星词（1267 词），优先掌握",     "🌟", "#E0B76E", _filter_min_collins(4)),
    ("oxford3000",   "牛津核心 3000",        "收录于牛津核心 3000 的词（2535 词）",         "🏛", "#9FC8B0", _filter_oxford),
]

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


def apply_wordbook(query, Word, wordbook_id: str | None, db, user_id: int | None = None) -> "Query":
    """统一应用词书过滤（预定义或自定义），返回过滤后的 query。

    - wordbook_id 为 None 或空 → 用默认书
    - custom_ 前缀 → **只允许当前用户自己的自定义书**；不存在或不属于自己时返回空集，
      绝不因为"查不到"而退化成不过滤（那等于把整个词库当成了别人的私有书内容）
    - 预定义书是公共数据，与 user_id 无关
    """
    import json as _json

    from sqlalchemy import false

    wb_id = wordbook_id or DEFAULT_WORDBOOK

    if wb_id.startswith("custom_"):
        from .models import CustomWordbook

        try:
            cid = int(wb_id[7:])
        except ValueError:
            return query.filter(false())
        wb = (
            db.query(CustomWordbook)
            .filter(CustomWordbook.id == cid, CustomWordbook.user_id == user_id)
            .first()
        )
        if not wb:
            return query.filter(false())
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
