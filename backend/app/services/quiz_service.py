"""测验生成服务"""

import random

from sqlalchemy.orm import Session

from ..models import StudyRecord, Word


def generate_daily_quiz(db: Session, count: int = 10) -> list[dict]:
    """生成每日测验（混合选择题和填空题）"""
    # 从最近学过的词中选题
    records = (
        db.query(StudyRecord)
        .filter(StudyRecord.status.in_(["learning", "new"]))
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

    if len(words) < 4:
        return []

    # 随机选 count 个词
    selected = random.sample(words, min(count, len(words)))
    all_words = db.query(Word).all()

    # 题型分配：约 40% 选择 + 30% 听音辨义 + 30% 拼写
    n = len(selected)
    choice_n = max(1, n * 4 // 10)
    listen_n = max(1, n * 3 // 10)
    spell_n = max(0, n - choice_n - listen_n)

    def _chinese_options(word):
        """生成中文释义四选一（1正确 + 3干扰）"""
        correct = word.definition.split("；")[0] if "；" in word.definition else word.definition
        others = [w for w in all_words if w.id != word.id]
        distractors = random.sample(others, min(3, len(others)))
        options = [correct] + [
            d.definition.split("；")[0] if "；" in d.definition else d.definition
            for d in distractors
        ]
        random.shuffle(options)
        return options, correct

    questions = []
    idx = 0

    # 选择题：英文选中文
    for word in selected[idx:idx + choice_n]:
        idx += 1
        options, correct = _chinese_options(word)
        questions.append({
            "word_id": word.id,
            "word": word.word,
            "quiz_type": "choice",
            "question": f'"{word.word}" 的中文意思是？',
            "options": options,
            "correct_answer": correct,
        })

    # 听音辨义：播读音选中文（不显示英文）
    for word in selected[idx:idx + listen_n]:
        idx += 1
        options, correct = _chinese_options(word)
        questions.append({
            "word_id": word.id,
            "word": word.word,
            "quiz_type": "listen",
            "question": "🔊 听音辨义：点击播放单词读音，选出正确释义",
            "options": options,
            "correct_answer": correct,
        })

    # 拼写默写：看中文写英文（不给首字母提示，更硬核）
    for word in selected[idx:idx + spell_n]:
        idx += 1
        definition = word.definition.split("；")[0] if "；" in word.definition else word.definition
        questions.append({
            "word_id": word.id,
            "word": word.word,
            "quiz_type": "spell",
            "question": f'拼写默写：请拼写出「{definition}」的英文单词',
            "correct_answer": word.word.lower(),
        })

    random.shuffle(questions)
    return questions


def check_answers(db: Session, answers: list[dict]) -> dict:
    """批改测验答案"""
    score = 0
    wrong_words = []

    for ans in answers:
        word = db.query(Word).filter(Word.id == ans["word_id"]).first()
        if not word:
            continue

        user_answer = ans.get("answer", "").strip().lower()
        correct = ans.get("correct_answer", "").lower()

        if user_answer == correct:
            score += 1
        else:
            wrong_words.append(word)
            # 错题标记为不认识
            from .study_service import submit_study
            submit_study(db, word.id, known=False)

    return {
        "score": score,
        "total": len(answers),
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
            }
            for w in wrong_words
        ],
    }
