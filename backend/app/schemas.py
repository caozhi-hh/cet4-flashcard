"""Pydantic 请求/响应模型"""

from pydantic import BaseModel


# === 单词 ===
class WordOut(BaseModel):
    id: int
    word: str
    phonetic_us: str | None = None
    phonetic_uk: str | None = None
    definition: str
    pos: str | None = None
    example: str | None = None
    example_cn: str | None = None


# === 闪卡 ===
class FlashCardOut(BaseModel):
    word: WordOut
    status: str           # new / learning / known
    mnemonic: str | None = None  # AI 记忆口诀（按需加载）


# === 学习记录 ===
class StudyRecordIn(BaseModel):
    word_id: int
    known: bool


class StudyRecordOut(BaseModel):
    word_id: int
    status: str
    know_count: int
    next_review_at: str | None = None


# === 测验 ===
class QuizQuestion(BaseModel):
    word_id: int
    word: str
    quiz_type: str           # choice / fill
    question: str
    options: list[str] | None = None
    correct_answer: str
    hint: str | None = None  # 填空题提示


class QuizSubmit(BaseModel):
    answers: list[dict]      # [{"word_id": 1, "answer": "xxx"}]


class QuizResult(BaseModel):
    score: int
    total: int
    wrong_words: list[WordOut]


# === 进度 ===
class ProgressOverview(BaseModel):
    total_words: int
    learned_words: int
    known_words: int
    today_new: int
    today_reviewed: int
    streak_days: int


class DailyProgress(BaseModel):
    date: str
    new_words: int
    reviewed_words: int
