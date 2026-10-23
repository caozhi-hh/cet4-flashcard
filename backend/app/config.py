"""配置管理 — 环境变量 + 默认值"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# === 代理绕过 ===
# 本地若有系统代理(如 Clash 7897)会拦截后端到智谱的请求，导致 AI Connection error
# 把智谱域名加入 NO_PROXY，强制直连。生产环境(HF Spaces)无此问题
_AI_DOMAINS = "bigmodel.cn,dashscope.aliyuncs.com,aliyuncs.com,127.0.0.1,localhost"
_existing = os.environ.get("NO_PROXY", "")
if "aliyuncs" not in _existing:
    os.environ["NO_PROXY"] = f"{_existing},{_AI_DOMAINS}".strip(",") if _existing else _AI_DOMAINS
    os.environ["no_proxy"] = os.environ["NO_PROXY"]

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path("/data") if Path("/data").exists() else BASE_DIR / "data"
DB_PATH = DATA_DIR / "cet4.db"
WORDS_JSON = BASE_DIR / "data" / "cet4_words.json"
# 分级阅读文章（本项目原创示例）：跟着代码走，不受 /data 数据目录影响
READING_JSON = BASE_DIR / "data" / "reading_articles.json"

# === 数据库 ===
# 优先用环境变量 DATABASE_URL（Render/Neon 的 PostgreSQL）；未设置则沿用本地 SQLite。
# 本地开发与现有测试完全不受影响：不设这个变量就还是 sqlite:///<DB_PATH>。
_DATABASE_URL_ENV = os.getenv("DATABASE_URL", "").strip()


def normalize_database_url(url: str) -> str:
    """把常见的 PostgreSQL 连接串规整成 SQLAlchemy 2.x + psycopg3 能直接用的形式

    - Render/Neon 面板复制到的可能是 `postgres://...`（旧 Heroku 写法），
      SQLAlchemy 2.x 已不再接受该 scheme；
    - 未指定驱动时补 `+psycopg`（本项目安装的驱动）；已指定驱动的（如 `+psycopg2`）原样保留。
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def backend_for_url(url: str) -> str:
    """按 URL 判断数据库方言（engine 参数与迁移/备份逻辑据此分流）"""
    return "postgresql" if (url or "").strip().startswith("postgresql") else "sqlite"


DATABASE_URL = (
    normalize_database_url(_DATABASE_URL_ENV) if _DATABASE_URL_ENV else f"sqlite:///{DB_PATH}"
)
# 方言标记：引擎参数、迁移与备份逻辑都按它分别处理
DB_BACKEND = backend_for_url(DATABASE_URL)
IS_SQLITE = DB_BACKEND == "sqlite"

# === AI 模型(智谱 GLM,走 OpenAI 兼容接口)===
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
AI_MODEL = os.getenv("AI_MODEL", "glm-4-flash")

# === 学习参数 ===
DAILY_NEW_WORDS = 20       # 每天新学单词数
KNOW_THRESHOLD = 3         # 连续认识几次标记为 known
REVIEW_INTERVALS = [1, 1, 3, 7, 14]  # 复习间隔（天）：随记忆加深间隔变长

# === 认证 / 会话 ===
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "cet4_session")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "cet4_csrf")
CSRF_HEADER_NAME = "x-csrf-token"
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
# Cookie Secure 策略：auto=按请求协议自动判定；1=强制 Secure；0=强制关闭（纯 http 本地开发）
COOKIE_SECURE_MODE = os.getenv("COOKIE_SECURE", "auto").strip().lower()
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
# 管理接口令牌（/api/words/init 之类）。未设置时该接口一律 403，默认不对公众开放
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# === AI 接口限流（内存滑窗，按登录用户计数；0 表示不限）===
# AI 有真实成本：仅靠"必须登录"挡不住单账号刷调用，上线前先加一道最简闸门
AI_MNEMONIC_LIMIT = int(os.getenv("AI_MNEMONIC_LIMIT", "30"))    # 记忆口诀：次/小时/人
AI_WORDBOOK_LIMIT = int(os.getenv("AI_WORDBOOK_LIMIT", "5"))     # AI 生成词书：次/小时/人
AI_RATE_WINDOW_SECONDS = int(os.getenv("AI_RATE_WINDOW_SECONDS", "3600"))

# === CORS ===
# 合并部署同源不需要 CORS，这里保留兼容本地 dev（前端 3000 → 后端 8000）
# 生产用自定义域名时，自动加入（环境变量 SITE_URL）
_SITE_URL = os.getenv("SITE_URL", "")
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if _SITE_URL:
    CORS_ORIGINS.append(_SITE_URL.rstrip("/"))
