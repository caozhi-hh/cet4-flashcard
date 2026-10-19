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
DATABASE_URL = f"sqlite:///{DB_PATH}"

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
