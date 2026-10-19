"""认证与会话

设计要点：
    - 密码用 **Argon2id** 哈希（argon2-cffi 默认参数 m=64MiB / t=3 / p=4），永不存明文。
    - 会话是**服务端**的：浏览器只拿随机 token（HttpOnly Cookie），库里存 SHA-256 摘要，
      因此可过期、可吊销，且数据库泄露也无法直接冒用。
    - 认证凭证只走 HttpOnly Cookie，**不进 localStorage**。
    - 写请求做 CSRF 防护：双重提交 + 会话绑定（header 必须等于 cookie，且等于会话里的同步器令牌）。
"""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import (
    ADMIN_TOKEN,
    COOKIE_SAMESITE,
    COOKIE_SECURE_MODE,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TTL_DAYS,
)
from .database import SessionLocal, get_db
from .models import AuthSession, User

logger = logging.getLogger(__name__)

# Argon2id（argon2-cffi 的默认类型就是 argon2id）
_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_EMAIL_LENGTH = 255

# 结构校验：不追求 RFC 5322 全覆盖，够挡住明显非法输入即可；唯一性由数据库约束保证
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


# === 邮箱 ===

def normalize_email(raw: str) -> str:
    """规范化邮箱：去首尾空格 + 全小写（唯一约束建在规范化结果上）"""
    return (raw or "").strip().lower()


def validate_email(email: str) -> None:
    if not email:
        raise ValueError("邮箱不能为空")
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValueError("邮箱过长")
    if not _EMAIL_RE.match(email):
        raise ValueError("邮箱格式不正确")


def validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LENGTH} 位")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"密码不能超过 {MAX_PASSWORD_LENGTH} 位")


# === 密码哈希 ===

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """校验密码；任何解析/校验异常都返回 False，不向调用方泄露细节"""
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# === 会话 ===

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User, ttl_days: int = SESSION_TTL_DAYS) -> tuple[str, AuthSession]:
    """新建会话，返回 (明文 token, 会话行)。明文 token 只出现在 Cookie 里，不入库。"""
    token = secrets.token_urlsafe(32)
    now = _utc_now()
    session = AuthSession(
        user_id=user.id,
        token_hash=_token_hash(token),
        csrf_token=secrets.token_urlsafe(32),
        created_at=_iso(now),
        expires_at=_iso(now + timedelta(days=ttl_days)),
        last_seen_at=_iso(now),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, session


def get_valid_session(db: Session, token: str) -> AuthSession | None:
    """按明文 token 找会话；已吊销或已过期返回 None"""
    if not token:
        return None
    session = db.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).first()
    if not session or session.revoked_at:
        return None
    try:
        expires = datetime.fromisoformat(session.expires_at)
    except (TypeError, ValueError):
        return None
    if expires <= _utc_now():
        return None
    return session


def touch_session(db: Session, session: AuthSession, ttl_days: int = SESSION_TTL_DAYS) -> None:
    """更新 last_seen；剩余有效期不足一半时滑动续期（避免每个请求都写库）"""
    now = _utc_now()
    session.last_seen_at = _iso(now)
    try:
        expires = datetime.fromisoformat(session.expires_at)
    except (TypeError, ValueError):
        expires = now
    if expires - now < timedelta(days=ttl_days / 2):
        session.expires_at = _iso(now + timedelta(days=ttl_days))
    db.commit()


def revoke_session(db: Session, session: AuthSession) -> None:
    session.revoked_at = _iso(_utc_now())
    db.commit()


def revoke_all_sessions(db: Session, user_id: int) -> int:
    """吊销某用户全部会话（改密码等场景用）"""
    rows = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .all()
    )
    now = _iso(_utc_now())
    for row in rows:
        row.revoked_at = now
    db.commit()
    return len(rows)


# === Cookie ===

def cookie_secure(request: Request) -> bool:
    """Cookie 的 Secure 策略

    auto（默认）：按请求协议判定，并识别反向代理的 X-Forwarded-Proto，
    这样本地 http 开发能正常带上 Cookie，生产 https 又不会被降级为明文传输。
    """
    mode = COOKIE_SECURE_MODE
    if mode in ("1", "true", "yes", "on"):
        return True
    if mode in ("0", "false", "no", "off"):
        return False
    if request.url.scheme == "https":
        return True
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return forwarded == "https"


def set_session_cookies(response: Response, request: Request, token: str, csrf_token: str, ttl_days: int = SESSION_TTL_DAYS) -> None:
    """写入会话 Cookie（HttpOnly）与 CSRF Cookie（需被前端 JS 读取，故非 HttpOnly）"""
    max_age = int(timedelta(days=ttl_days).total_seconds())
    secure = cookie_secure(request)
    common = {"path": "/", "samesite": COOKIE_SAMESITE, "secure": secure}
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, max_age=max_age, **common)
    response.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=False, max_age=max_age, **common)


def clear_session_cookies(response: Response, request: Request) -> None:
    secure = cookie_secure(request)
    common = {"path": "/", "samesite": COOKIE_SAMESITE, "secure": secure}
    response.delete_cookie(SESSION_COOKIE_NAME, httponly=True, **common)
    response.delete_cookie(CSRF_COOKIE_NAME, httponly=False, **common)


def ensure_csrf_cookie(response: Response, request: Request) -> str:
    """给匿名访问者发放 CSRF 令牌（登录/注册这类写请求也要防护）"""
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    token = existing or secrets.token_urlsafe(32)
    if not existing:
        max_age = int(timedelta(days=1).total_seconds())
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            httponly=False,
            max_age=max_age,
            path="/",
            samesite=COOKIE_SAMESITE,
            secure=cookie_secure(request),
        )
    return token


# === CSRF ===

def csrf_ok(request: Request, db: Session) -> bool:
    """双重提交 + 会话绑定校验

    1) header 必须存在，且与 CSRF cookie 一致（跨站请求无法读取该 cookie，因此伪造不出 header）；
    2) 若带有效会话，header 还必须等于会话里保存的同步器令牌 —— 防止攻击者用自己的
       CSRF cookie 覆盖受害者的（cookie 注入）。
    """
    header = request.headers.get(CSRF_HEADER_NAME, "")
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        return False

    session_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if session_token:
        session = get_valid_session(db, session_token)
        if session and not hmac.compare_digest(header, session.csrf_token):
            return False
    return True


async def csrf_middleware(request: Request, call_next):
    """对所有 /api 下的写请求强制 CSRF 校验"""
    if request.method in MUTATING_METHODS and request.url.path.startswith("/api/"):
        db = SessionLocal()
        try:
            passed = csrf_ok(request, db)
        finally:
            db.close()
        if not passed:
            return JSONResponse(
                {"detail": "CSRF 校验失败：请刷新页面后重试"},
                status_code=status.HTTP_403_FORBIDDEN,
            )
    return await call_next(request)


# === FastAPI 依赖 ===

def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    """有有效会话就返回用户，否则 None（不抛错）"""
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return None
    session = get_valid_session(db, token)
    if not session:
        return None
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        return None
    touch_session(db, session)
    return user


def require_user(user: User | None = Depends(current_user_optional)) -> User:
    """受保护接口的依赖：未登录直接 401"""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return user


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """管理接口依赖：未配置 ADMIN_TOKEN 时一律拒绝（默认不对公众开放）"""
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="管理接口未启用（未配置 ADMIN_TOKEN）")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="管理令牌无效")