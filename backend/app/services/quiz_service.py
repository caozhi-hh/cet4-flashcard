"""测验生成服务

安全约定：正确答案**不下发**给客户端，判分只依据词库自身数据。
"""

import random
import re

from sqlalchemy.orm import Session

from ..models import StudyRecord, Word


def generate_daily_quiz(db: Session, user_id: int, count: int = 10) -> list[dict]:
    """生成每日测验（混合选择题和填空题）

    只从**当前用户**最近学过的词里选题；该用户还没有学习记录时，
    退化为从公共词库取词（词库是共享数据，不涉及隐私）。

    词池不足 4 个时用词库补足：只学过 1-3 个词的新用户原先会拿到一张空卷
    （生成器直接返回 []），测验页空白 —— 这是主流程缺陷，不是"没题可出"。
    """
    # 从最近学过的词中选题
    records = (
        db.query(StudyRecord)
        .filter(
            StudyRecord.user_id == user_id,
            StudyRecord.status.in_(["learning", "new"]),
        )
        .order_by(StudyRecord.last_studied_at.desc())
        .limit(30)
        .all()
    )

    if not records:
        # 如果没有学习记录，从词库随机取
        words = db.query(Word).order_by(Word.frequency).limit(30).all()
    else:
        words = []
        for r in records:
            w = db.query(Word).filter(Word.id == r.word_id).first()
            if w:
                words.append(w)

    # 补足词池：优先保留"自己学过的词"，不够再用词库里的高频词补齐
    if len(words) < 4:
        have = {w.id for w in words}
        extra = (
            db.query(Word)
            .filter(Word.id.notin_(have))
            .order_by(Word.frequency)
            .limit(30 - len(words))
            .all()
        )
        words.extend(extra)

    if len(words) < 4:
        return []

    selected = random.sample(words, min(count, len(words)))
    all_words = db.query(Word).all()

    # 题型分配：约 40% 选择 + 30% 听音辨义 + 30% 拼写
    n = len(selected)
    choice_n = max(1, n * 4 // 10)
    listen_n = max(1, n * 3 // 10)
    spell_n = max(0, n - choice_n - listen_n)

    def _chinese_options(word):
        """生成中文释义四选一（1正确 + 3干扰）"""
        correct = _definition_form(word)
        others = [w for w in all_words if w.id != word.id]
        distractors = random.sample(others, min(3, len(others)))
        options = [correct] + [_definition_form(d) for d in distractors]
        random.shuffle(options)
        return options, correct

    questions = []
    idx = 0

    # 选择题：英文选中文
    for word in selected[idx:idx + choice_n]:
        idx += 1
        options, _correct = _chinese_options(word)
        questions.append({
            "word_id": word.id,
            "word": word.word,
            "quiz_type": "choice",
            "question": f'"{word.word}" 的中文意思是？',
            "options": options,
            # 注意：**不下发正确答案**，判分由服务端依据词库数据完成
        })

    # 听音辨义：播读音选中文（不显示英文）
    for word in selected[idx:idx + listen_n]:
        idx += 1
        options, _correct = _chinese_options(word)
        questions.append({
            "word_id": word.id,
            "word": word.word,
            "quiz_type": "listen",
            "question": "🔊 听音辨义：点击播放单词读音，选出正确释义",
            "options": options,
        })

    # 拼写默写：看中文写英文（不给首字母提示，更硬核）
    for word in selected[idx:idx + spell_n]:
        idx += 1
        definition = _definition_form(word)
        questions.append({
            "word_id": word.id,
            "word": word.word,
            "quiz_type": "spell",
            "question": f'拼写默写：请拼写出「{definition}」的英文单词',
        })

    random.shuffle(questions)
    return questions


def _normalize(text: str) -> str:
    """比较用归一化：去首尾空白、折叠内部空白、统一小写"""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _definition_form(word: Word) -> str:
    """词库里用于出题的那一条释义（与出题时的取法保持一致）"""
    definition = word.definition or ""
    return definition.split("；")[0] if "；" in definition else definition


def _is_correct(word: Word, user_answer: str) -> bool:
    """判分只依据**词库自身数据**

    释义题（选择 / 听音辨义）对释义；拼写题对英文单词。
    客户端提交的 correct_answer 一律不参与判定 —— 否则改一个字段就能拿满分。
    """
    given = _normalize(user_answer)
    if not given:
        return False
    return given == _normalize(_definition_form(word)) or given == _normalize(word.word)


def check_answers(db: Session, user_id: int, answers: list[dict]) -> dict:
    """批改测验答案（错题只回写**该用户自己**的学习进度）"""
    score = 0
    unanswered = 0
    wrong_words = []

    for ans in answers:
        word = db.query(Word).filter(Word.id == ans["word_id"]).first()
        if not word:
            continue

        user_answer = (ans.get("answer") or "").strip()

        # 未作答：既不判对也不判错，更不回写学习进度。
        # 必须跳过 submit_study：known=False 会把 know_count 清零、状态退回 learning，
        # 那样"只答几题就交卷"会不可逆地清掉这些词已积累的连续认识次数。
        if not user_answer:
            unanswered += 1
            continue

        # 判分只用词库数据（不读客户端提交的 correct_answer）
        if _is_correct(word, user_answer):
            score += 1
        else:
            wrong_words.append(word)
            # 错题标记为不认识（限定当前用户）
            from .study_service import submit_study

            submit_study(db, user_id, word.id, known=False)

    return {
        "score": score,
        "total": len(answers),
        "unanswered": unanswered,
        "wrong_words": [
            {
                "id": w.id,
                "word": w.word,
                "phonetic_us": w.phonetic_us,
                "phonetic_uk": w.phonetic_uk,
                "definition": w.definition,
                "pos": w.pos,
                "example": w.example,
                "example_cn": w.example_cn,
                "tags": w.tags,
                "frq": w.frq,
            }
            for w in wrong_words
        ],
    }
