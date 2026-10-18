"""Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field


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
    tags: str | None = None      # ECDICT 考试标签，空格分隔
    frq: int | None = None       # COCA 语料词频序号


# === 闪卡 ===
class FlashCardOut(BaseModel):
    word: WordOut
    status: str           # new / learning / known
    mnemonic: str | None = None  # AI 记忆口诀（按需加载）


# === 学习记录 ===
class StudyRecordIn(BaseModel):
    """提交一次学习结果

    rating 是 FSRS 四档评分：1 重来 / 2 困难 / 3 良好 / 4 简单；
    known 是改造前的二值反馈，保留以兼容已构建的旧前端产物。
    两者至少要给一个（都不给由服务层抛 InvalidRatingError → 422）。
    """
    word_id: int
    rating: int | None = Field(default=None, ge=1, le=4)
    known: bool | None = None


class StudyRecordOut(BaseModel):
    word_id: int
    rating: int
    status: str
    know_count: int
    next_review_at: str | None = None
    interval_days: float = 0.0
    fsrs_state: int = 1


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
