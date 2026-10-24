"""ORM 模型"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, UniqueConstraint

from .database import Base

ISO_TIMESTAMP_LENGTH = 40


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    """用户表

    email 存**规范化后**的邮箱（去空格 + 小写），唯一约束建在它上面，
    避免 Foo@x.com 与 foo@x.com 注册出两个账号。
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)   # Argon2id 哈希，绝不存明文
    created_at = Column(String(ISO_TIMESTAMP_LENGTH), default=_now_iso)
    last_login_at = Column(String(ISO_TIMESTAMP_LENGTH))


class AuthSession(Base):
    """服务端会话

    浏览器只持有随机 token（HttpOnly Cookie），库里存它的 SHA-256：
    即使数据库被读走也无法直接冒用会话。可过期、可吊销（logout 写 revoked_at）。
    """
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    csrf_token = Column(String(64), nullable=False)       # 同步器令牌（双重提交 + 会话绑定）
    created_at = Column(String(ISO_TIMESTAMP_LENGTH), default=_now_iso)
    expires_at = Column(String(ISO_TIMESTAMP_LENGTH), nullable=False, index=True)
    revoked_at = Column(String(ISO_TIMESTAMP_LENGTH))
    last_seen_at = Column(String(ISO_TIMESTAMP_LENGTH))


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
    frequency = Column(Integer, default=0)         # 词库内的排序序号（1..N，用于稳定排序）

    # === ECDICT 富化字段（由 scripts/enrich_words_from_ecdict.py 写入 JSON，迁移时回填）===
    tags = Column(String(100))                     # 考试标签，空格分隔：zk gk cet4 cet6 ky toefl ielts gre
    frq = Column(Integer)                          # COCA 语料词频序号（越小越高频；None=无数据）
    bnc = Column(Integer)                          # BNC 语料词频序号（0 表示该语料无排名）
    collins = Column(Integer)                      # 柯林斯星级 1-5
    oxford = Column(Integer, default=0)            # 是否收录于牛津核心 3000


class StudyRecord(Base):
    """学习记录表 — 跟踪每个词的学习状态"""
    __tablename__ = "study_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(Integer, nullable=False, index=True)
    # 归属用户：NULL = 多用户改造之前的遗留数据，对任何用户都不可见（不自动归属给首个注册者）
    user_id = Column(Integer, nullable=True, index=True)
    status = Column(String(20), default="new")     # new / learning / known
    know_count = Column(Integer, default=0)        # 连续「认识」次数
    unknown_count = Column(Integer, default=0)     # 连续「不认识」次数
    review_count = Column(Integer, default=0)      # 总复习次数
    next_review_at = Column(String(ISO_TIMESTAMP_LENGTH))  # 下次复习时间 ISO 8601（复习队列按此筛选）
    last_studied_at = Column(String(ISO_TIMESTAMP_LENGTH))  # 上次学习时间
    # FSRS 卡片状态（py-fsrs 的 JSON 序列化：state/step/stability/difficulty/due/last_review）
    # 历史记录由 migrations.ensure_fsrs_schema 回填，回填时保留原有 next_review_at
    fsrs_card = Column(Text)
    created_at = Column(String(ISO_TIMESTAMP_LENGTH), default=lambda: datetime.now(timezone.utc).isoformat())


class DailyStat(Base):
    """每日统计表

    注意唯一约束：原先 date 是全局唯一，多用户下同一天会有多行，
    所以迁移会把约束改成 UNIQUE(user_id, date)（SQLite 需重建表，见 migrations.py）。
    遗留行的 user_id 为 NULL；SQLite 中 NULL 互不相等，因此不会互相冲突，也不会被任何用户查到。
    """
    __tablename__ = "daily_stats"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_stats_user_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False)                # YYYY-MM-DD
    user_id = Column(Integer, nullable=True, index=True)     # NULL = 遗留数据
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
    user_id = Column(Integer, nullable=True, index=True)   # 归属用户；NULL = 遗留数据，对任何用户不可见
    description = Column(String(200))                      # 描述
    icon = Column(String(10), default="✨")                # emoji 图标
    query_text = Column(Text, nullable=False)              # 用户的原始需求
    keywords = Column(Text, nullable=False)                # JSON: 粗筛关键词列表
    word_ids = Column(Text)                                # JSON: AI 精选的 word_id 列表
    pos = Column(String(20))                               # 词性过滤，可空
    freq_max = Column(Integer, default=4544)               # 词频上限
    created_at = Column(String(ISO_TIMESTAMP_LENGTH), default=lambda: datetime.now(timezone.utc).isoformat())


class ReadingAttempt(Base):
    """分级阅读答题记录（用户级）

    只保存**服务端判分**的结果：score/total 由后端依据文章自身答案计算，
    客户端提交的分数、总题数与 user_id 一律不采信。
    """
    __tablename__ = "reading_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    slug = Column(String(64), nullable=False, index=True)   # 文章 slug（正文在 JSON，不在库里）
    level = Column(String(8))                               # A1 / A2 / B1
    score = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Integer, default=0)           # 阅读+作答耗时（前端上报，仅作参考）
    completed_at = Column(String(ISO_TIMESTAMP_LENGTH), index=True)
    created_at = Column(String(ISO_TIMESTAMP_LENGTH), default=_now_iso)


class StudyPlan(Base):
    """用户级学习计划

    MVP：每个用户一份"当前生效"的计划（user_id 唯一）。
    字段本身是可扩展的——goal_type 决定默认词书，wordbook_key 指向现有词书体系
    （预定义书 id，或本人的 custom_<id>），以后要支持多计划/多语言只需放宽唯一约束。
    """
    __tablename__ = "study_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    goal_type = Column(String(32), nullable=False)          # cet4 / cet6 / kaoyan / ielts / toefl / general
    wordbook_key = Column(String(64), nullable=False)       # 现有词书体系的 id（含 custom_<id>）
    target_date = Column(String(10))                        # YYYY-MM-DD，可空（不设目标日期）
    daily_new_words = Column(Integer, nullable=False, default=20)
    created_at = Column(String(ISO_TIMESTAMP_LENGTH), default=_now_iso)
    updated_at = Column(String(ISO_TIMESTAMP_LENGTH), default=_now_iso)


class StarredWord(Base):
    """生词本/错题本 — 收藏的难点词和测验错的词"""
    __tablename__ = "starred_words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(Integer, nullable=False, index=True)   # 关联 Word.id
    user_id = Column(Integer, nullable=True, index=True)    # 归属用户；NULL = 遗留数据，对任何用户不可见
    type = Column(String(10), nullable=False)               # star 收藏 / hard 错题
    created_at = Column(String(ISO_TIMESTAMP_LENGTH), default=lambda: datetime.now(timezone.utc).isoformat())
