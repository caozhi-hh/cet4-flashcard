"""AI 服务 — 记忆口诀 + 测验生成"""

import json
import logging

from openai import OpenAI

from ..config import AI_API_KEY, AI_BASE_URL, AI_MODEL

logger = logging.getLogger(__name__)

client = OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL) if AI_API_KEY else None


async def generate_mnemonic(word: str, definition: str, phonetic: str = "", pos: str = "") -> str:
    """生成记忆口诀"""
    if not client:
        return "AI 服务未配置，请设置 AI_API_KEY"

    prompt = f"""你是一个英语词汇记忆专家。请为以下英语单词生成帮助中国学生记忆的解析，按顺序输出：

单词：{word}
音标：{phonetic}
词性：{pos}
中文释义：{definition}

请用以下格式回复（每部分 1-2 句，简洁）：

【词根词缀】（最重要，必须先写）拆解词根/词缀/词源，用 + 号连接。
  示例：unprecedented → un(否定) + pre(前) + ced(走) + ent + ed，意为"从未走在前面的"，即史无前例。
  示例：import → im(进) + port(搬运) = 进口。
  若是短词无明显词根，改为【词源/构成】简述。
【拆分联想】将单词拆成易记部分并联想（如 restaurant → rest(休息) + aurant，吃饭的地方要"休息")。
【谐音联想】中文谐音记忆法（如有好的谐音；不适合可跳过）。
【情境记忆】一句简短情境帮助记忆。

风格：实用、易记、不啰嗦。"""

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"AI 生成记忆口诀失败: {e}")
        return f"生成失败：{e}"


async def generate_wordbook_words(query: str) -> dict:
    """AI 直接根据主题生成相关四级单词列表（用自己的知识，不依赖粗筛）

    返回: {name, icon, words: [英文单词列表]}
    比粗筛+精选两阶段更精准：AI 直接列出它知道的主题词
    """
    if not client:
        return {"name": query[:8] + "词书", "icon": "✨", "words": []}

    prompt = f"""你是大学英语四级词汇专家。用户想创建一本关于「{query}」的单词书。

请直接列出 80-150 个【与该主题强相关】且【属于大学英语四级（CET4）常见词汇】的英文单词（全小写）。

要求：
- 优先具体名词 + 相关动词/形容词。例：「食物」→ bread, apple, milk, cake, vegetable, meat, rice, fish, egg, cook, eat, taste, hungry, delicious, restaurant, menu, fork, spoon, bowl, dish...
- 必须是真实、日常常用的词（四级难度）
- 不要超出主题、不要生僻词
- 不要重复
- 只给单词，不给解释

返回严格 JSON（不要markdown代码块、不要其他文字）：
{{"name":"书名(≤8字)","icon":"最能代表主题的emoji","words":["word1","word2","word3"]}}"""

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=2500,
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            content = content.replace("```json", "").replace("```", "").strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            words = [str(w).lower().strip() for w in data.get("words", []) if str(w).strip()]
            if words:
                return {"name": data.get("name", query[:8] + "词书")[:50],
                        "icon": data.get("icon", "✨")[:6], "words": words}
        logger.error(f"AI 生成词列表无法解析: {content[:200]}")
    except Exception as e:
        logger.error(f"AI 生成词列表失败: {e}")
    return {"name": query[:8] + "词书", "icon": "✨", "words": []}


async def generate_wordbook_config(query: str) -> dict:
    """AI 分析用户需求，生成单词书筛选配置

    返回: {name, description, icon, keywords, pos, freq_max}
    keywords 用于在单词 definition 中匹配；pos 词性过滤；freq_max 词频上限
    """
    if not client:
        # 降级：无 AI key 时用中文滑窗分词，至少能匹配一些词
        strip_chars = "，。、；：！？的了吗呢吧和与及是有关相 \t\n"
        clean = query
        for ch in strip_chars:
            clean = clean.replace(ch, "")
        keywords = []
        for i in range(len(clean) - 1):
            kw = clean[i:i + 2]
            if len(kw) == 2:
                keywords.append(kw)
        keywords = list(dict.fromkeys(keywords))[:6]
        if not keywords:
            keywords = [query[:2]] if len(query) >= 2 else [query]
        return {
            "name": query[:10] + "词书" if len(query) <= 8 else "自定义词书",
            "description": f"基于「{query[:15]}」的单词集",
            "icon": "✨",
            "keywords": keywords,
            "pos": "",
            "freq_max": 4544,
        }

    prompt = f"""你是大学英语四级词汇专家。用户想创建一本单词书，需求是："{query}"

词库是四级大纲词汇(约4500词)，每个词有中文释义(definition)、词性(pos)、词频排名(frequency，1=最高频)。

请生成单词书配置，返回严格 JSON（不要markdown、不要其他文字）：
{{
  "name": "简洁书名(≤10字)",
  "description": "一句话描述(≤20字)",
  "icon": "最能代表该主题的emoji",
  "keywords": ["宽泛关键词1", "宽泛关键词2"],
  "pos": "",
  "freq_max": 4544
}}

keywords 规则（最重要）：
- 生成 10-15 个【宽泛、覆盖面广】的中文关键词，用于在释义中模糊匹配，宁多勿漏
- 要覆盖主题的方方面面（如「食物」→["食物","吃","喝","菜","饭","味","水果","面","糖","肉","餐","饿","渴","米","茶"]）
- 关键词要短（1-3字），是释义里真实会出现的字词
- 不要太具体（"苹果"不好，"水果"好）

pos：词性过滤，用户明确指定才填(v/n/adj/adv)，否则空字符串
freq_max：泛主题填4544；若明显是高频基础词填2000
只返回 JSON"""

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
        logger.error(f"AI 返回无法解析: {content}")
        return {"name": "自定义词书", "description": query[:20], "icon": "✨",
                "keywords": [query[:4]], "pos": "", "freq_max": 4544}
    except Exception as e:
        logger.error(f"AI 生成单词书配置失败: {e}")
        return {"name": "自定义词书", "description": query[:20], "icon": "✨",
                "keywords": [query[:4]], "pos": "", "freq_max": 4544}


async def refine_word_selection(query: str, candidates: list[dict]) -> list[int]:
    """AI 从粗筛候选词中精选，返回按常用度+相关度排序的 word_id 列表

    candidates: [{"id":1,"word":"apple","definition":"n. 苹果"}, ...]
    无 AI key 或候选太少时，直接按词频返回全部候选
    """
    if not client or len(candidates) <= 40:
        return [c["id"] for c in candidates[:150]]

    # 限制 token：取词频最低（最高频）的 250 个候选
    sample = candidates[:250]
    cand_text = "\n".join(f'{c["id"]}|{c["word"]}|{c["definition"][:25]}' for c in sample)

    prompt = f"""用户想创建关于「{query}」的四级单词书。以下是粗筛候选词（格式 id|单词|释义，按词频高到低）：

{cand_text}

挑出【真正与「{query}」紧密相关】且【常用】的词，按相关度排序，选 60-120 个。宁缺毋滥。
只返回纯JSON，不要markdown代码块、不要解释：
{{"word_ids":[1,2,3]}}"""

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2500,
        )
        content = response.choices[0].message.content.strip()
        # 鲁棒提取 JSON：去 markdown 代码块、去前后多余文字
        cleaned = content
        if "```" in cleaned:
            # 去掉 ```json 和 ``` 标记行
            cleaned = cleaned.replace("```json", "").replace("```", "")
            cleaned = cleaned.strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(cleaned[start:end])
            ids = data.get("word_ids", [])
            result = []
            for i in ids:
                try:
                    result.append(int(i))
                except (ValueError, TypeError):
                    continue
            if result:
                return result[:150]
        logger.error(f"AI 精选返回无法解析: {content[:200]}")
    except Exception as e:
        logger.error(f"AI 精选失败: {e}")
    # 兜底：候选少时返回全部，多时取较相关的中段（前150容易混入高频无关词，但无更好办法）
    return [c["id"] for c in candidates[:min(len(candidates), 120)]]


async def generate_ai_quiz(words: list[dict]) -> list[dict]:
    """AI 生成测验题目"""
    if not client:
        return []

    word_list = "\n".join(
        f"- {w['word']}: {w['definition']}" for w in words
    )

    prompt = f"""你是英语四级考试出题专家。根据以下单词生成10道测验题。

单词列表：
{word_list}

混合题型：
- 7道四选一选择题（4道英文选中文，3道中文选英文）
- 3道填空题（给出中文释义，填写英文单词）

请直接返回 JSON 数组，格式：
[{{"type":"choice","word":"xxx","question":"...","options":["A...","B...","C...","D..."],"correct":"B","word_id":123}}, ...]
[{{"type":"fill","word":"xxx","question":"...","hint":"...","answer":"xxx","word_id":123}}, ...]"""

    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        # 提取 JSON
        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
        return []
    except Exception as e:
        logger.error(f"AI 生成测验失败: {e}")
        return []
