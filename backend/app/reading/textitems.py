"""文本分词与"渲染项"计算 —— 阅读页点词查义的基础

本模块的**核心算法改写自 Lute**（https://github.com/LuteOrg/lute-v3），MIT License：
    lute/read/render/calculate_textitems.py —— 重叠项消解：按 (index, -token_count) 排序后
                                               从后往前写入，再用 display_count 决定真正渲染的项
    lute/read/render/text_item.py           —— TextItem 展示契约：display_text / status_class / span_id

MIT 许可要求保留版权与许可声明，全文如下：

    MIT License

    Copyright (c) 2023 Jeff Zohrab

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

与本项目的差异（我们没有 Flask/Jinja，也没有 Lute 那套 Term 表）：
    - 分词用正则实现，不引入按语言的 parser；
    - "term" 来自本项目公共词库 words 表（**精确匹配** headword），
      掌握状态来自当前用户自己的学习记录 —— 不引入 Lute 的 Term/status 数据模型；
    - 输出为普通 dict，供 FastAPI 直接序列化。
"""

import re
from collections import Counter
from dataclasses import dataclass, field

# 零宽空格：多词项内部用它连接 token（沿用 Lute 的做法，避免与正文空格混淆）
ZWS = "\u200B"
# 段落标记 token：与 Lute 一致，用它在一趟扫描里算出每个项的段落号
PARAGRAPH_MARK = "¶"

# 词 / 数字 / 标点与空白。连字符与撇号算作词的一部分（don't、well-known）
TOKEN_RE = re.compile(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*|[0-9]+|[^\sA-Za-z0-9]+|\s+")
SENTENCE_END = ".!?"

# 掌握状态：与 Lute 的 status0/1..5 同构，但用本项目自己的词汇
STATUS_UNKNOWN = "unknown"   # 词库里没有收录
STATUS_NEW = "new"           # 收录了但当前用户没学过
STATUS_LEARNING = "learning"
STATUS_KNOWN = "known"


@dataclass
class TextItem:
    """要渲染的一个单元（一个词、一段空白或一个标点）

    display_count / display_text 的语义来自 Lute 的 TextItem：
    当一个项被更长的项覆盖时，只渲染它**末尾**的若干个 token。
    """

    index: int
    text: str
    text_lc: str
    token_count: int = 1
    display_count: int = 1
    is_word: bool = False
    sentence_number: int = 0
    paragraph_number: int = 0
    term: dict | None = None
    extra_classes: list[str] = field(default_factory=list)

    @property
    def display_text(self) -> str:
        """被覆盖时只显示末尾 display_count 个 token"""
        toks = self.text.split(ZWS)
        return ZWS.join(toks[-self.display_count :])

    @property
    def html_text(self) -> str:
        return self.display_text.replace(ZWS, "")

    @property
    def span_id(self) -> str:
        """每个 span 一个稳定 id（沿用 Lute 的 ID-{句}-{起始索引} 形式）"""
        return f"ID-{self.sentence_number}-{self.index}"

    @property
    def status(self) -> str:
        if not self.is_word or not self.term:
            return STATUS_UNKNOWN
        return self.term.get("status") or STATUS_NEW

    @property
    def html_class_string(self) -> str:
        """渲染用的 class（对应 Lute 的 html_class_string）"""
        classes = ["textitem"]
        if not self.is_word:
            return " ".join(classes)
        classes += ["click", "word", f"status-{self.status}"]
        if self.display_text != self.text:
            classes.append("overlapped")
        return " ".join(classes + self.extra_classes)

    def to_dict(self) -> dict:
        return {
            "text": self.html_text,
            "index": self.index,
            "span_id": self.span_id,
            "is_word": self.is_word,
            "sentence": self.sentence_number,
            "paragraph": self.paragraph_number,
            "status": self.status,
            "term": self.term if self.is_word else None,
        }


def tokenize(paragraphs: list[str]) -> list[dict]:
    """把段落切成 token 序列：词 / 空白 / 标点；段落之间插入 ¶ 标记"""
    tokens: list[dict] = []
    for i, para in enumerate(paragraphs):
        if i > 0:
            tokens.append({"token": PARAGRAPH_MARK, "is_word": False})
        for m in TOKEN_RE.finditer(para or ""):
            raw = m.group(0)
            tokens.append({"token": raw, "is_word": bool(raw[:1].isalnum())})
    return tokens


def _sentence_numbers(tokens: list[dict]) -> list[int]:
    """给每个 token 标注句子号（遇到 . ! ? 结束一句；¶ 也另起一句）"""
    numbers: list[int] = []
    current = 0
    for tok in tokens:
        numbers.append(current)
        raw = tok["token"]
        if raw == PARAGRAPH_MARK:
            current += 1
        elif not tok["is_word"] and raw.strip() and raw.strip()[-1] in SENTENCE_END:
            current += 1
    return numbers


def get_string_indexes(strings: list[str], content: str) -> list[tuple[str, int]]:
    """在 content 中找出 strings 的出现位置（支持重叠匹配）

    直接沿用 Lute 的实现思路：两侧补零宽空格后做前瞻正则匹配，
    这样 "_b_b_" 这类重叠也能都找出来（Lute 源码注释引用的正是这个经典问题）。
    strings 与 content 都必须是**小写**。
    """
    search = ZWS + content + ZWS
    zws_positions = [i for i, ch in enumerate(search) if ch == ZWS]
    found: list[tuple[str, int]] = []
    for s in strings:
        pattern = rf"(?=({re.escape(ZWS + s + ZWS)}))"
        for m in re.finditer(pattern, search):
            found.append((s, zws_positions.index(m.start())))
    return found


def build_text_items(
    paragraphs: list[str],
    terms: dict[str, dict] | None = None,
    multiword_terms: list[str] | None = None,
) -> list[TextItem]:
    """计算真正要渲染的渲染项列表

    terms: 小写词 → {word_id, headword, definition, phonetic, status, starred}
    multiword_terms: 词组（本项目词库暂无词组，参数保留以复用同一套重叠消解算法）
    """
    terms = terms or {}
    tokens = tokenize(paragraphs)
    if not tokens:
        return []

    tokens_orig = [t["token"] for t in tokens]
    tokens_lc = [t.lower() for t in tokens_orig]
    sentences = _sentence_numbers(tokens)

    items: list[TextItem] = []

    def add(index: int, text_lc: str, count: int) -> None:
        text_orig = (
            tokens_orig[index] if count == 1 else ZWS.join(tokens_orig[index : index + count])
        )
        term = terms.get(text_lc)
        items.append(
            TextItem(
                index=index,
                text=text_orig,
                text_lc=text_lc,
                token_count=count,
                is_word=term is not None,
                sentence_number=sentences[index],
                term=term,
            )
        )

    # 1) 每个 token 先各自成项（非词 token 没有 term，因而 is_word=False）
    for i in range(len(tokens)):
        add(i, tokens_lc[i], 1)

    # 2) 多词项（若有）
    if multiword_terms:
        joined = ZWS.join(tokens_lc)
        for text_lc, index in get_string_indexes(multiword_terms, joined):
            add(index, text_lc, text_lc.count(ZWS) + 1)

    # 3) 重叠消解：按 (起始, token 数降序) 排序，**从后往前**写入占位数组，
    #    于是"更长的项"会覆盖较短的项，且不会重复渲染任何 token。
    items.sort(key=lambda x: (x.index, -x.token_count))
    written: list[int | None] = [None] * len(tokens)
    for item in reversed(items):
        for pos in range(item.index, item.index + item.token_count):
            written[pos] = id(item)

    counts = Counter(written)
    for item in items:
        item.display_count = counts.get(id(item), 0)
    visible = [it for it in items if it.display_count > 0]

    # 4) 段落号（¶ 标记本身属于上一段）
    paragraph = 0
    for item in visible:
        item.paragraph_number = paragraph
        if item.text == PARAGRAPH_MARK:
            paragraph += 1

    return visible


def render_paragraphs(items: list[TextItem]) -> list[list[dict]]:
    """把渲染项按段落分组，并去掉段落标记本身（前端直接按段落渲染）"""
    paragraphs: dict[int, list[dict]] = {}
    for item in items:
        if item.text == PARAGRAPH_MARK:
            continue
        paragraphs.setdefault(item.paragraph_number, []).append(item.to_dict())
    return [paragraphs[k] for k in sorted(paragraphs)]