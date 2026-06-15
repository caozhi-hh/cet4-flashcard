"""ORM 模型"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Float, Integer, String, Text

from .database import Base


class Word(Base):
    """词库表 — 应用启动时从 JSON 导入"""
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(100), nullable=False, unique=True, index=True)
    phonetic_us = Column(String(100))
    phonetic_uk = Column(String(100))
    definition = Column(Text, nullable=False)      # 中文释义，多个用分号分隔
    pos = Column(String(20))                       # 词性：n./v./adj. 等
    example = Column(Text)                         # 英文例句
    example_cn = Column(Text)                      # 例句中文翻译
    frequency = Column(Integer, default=0)         # 词频排序


class StudyRecord(Base):
    """学习记录表 — 跟踪每个词的学习状态"""
    __tablename__ = "study_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(Integer, nullable=False, index=True)
    status = Column(String(20), default="new")     # new / learning / known
    know_count = Column(Integer, default=0)        # 连续「认识」次数
    unknown_count = Column(Integer, default=0)     # 连续「不认识」次数
    review_count = Column(Integer, default=0)      # 总复习次数
    next_review_at = Column(String(30))            # 下次复习时间 ISO 8601
    last_studied_at = Column(String(30))           # 上次学习时间
    created_at = Column(String(30), default=lambda: datetime.now(timezone.utc).isoformat())


class DailyStat(Base):
    """每日统计表"""
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, unique=True)  # YYYY-MM-DD
    new_words = Column(Integer, default=0)          # 当日新学数
    reviewed_words = Column(Integer, default=0)     # 当日复习数
    quiz_score = Column(Integer, default=0)         # 测验得分
    quiz_total = Column(Integer, default=0)         # 测验总题数
    streak_days = Column(Integer, default=0)        # 连续学习天数


class CustomWordbook(Base):
    """AI 生成的自定义单词书"""
    __tablename__ = "custom_wordbooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)              # 书名
    description = Column(String(200))                      # 描述
    icon = Column(String(10), default="✨")                # emoji 图标
    query_text = Column(Text, nullable=False)              # 用户的原始需求
    keywords = Column(Text, nullable=False)                # JSON: 粗筛关键词列表
    word_ids = Column(Text)                                # JSON: AI 精选的 word_id 列表
    pos = Column(String(20))                               # 词性过滤，可空
    freq_max = Column(Integer, default=4544)               # 词频上限
    created_at = Column(String(30), default=lambda: datetime.now(timezone.utc).isoformat())


class StarredWord(Base):
    """生词本/错题本 — 收藏的难点词和测验错的词"""
    __tablename__ = "starred_words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(Integer, nullable=False, index=True)   # 关联 Word.id
    type = Column(String(10), nullable=False)               # star 收藏 / hard 错题
    created_at = Column(String(30), default=lambda: datetime.now(timezone.utc).isoformat())
