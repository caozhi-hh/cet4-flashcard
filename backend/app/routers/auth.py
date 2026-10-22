"""认证路由 — 注册 / 登录 / 退出 / 当前用户 / CSRF 令牌"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import (
    SESSION_COOKIE_NAME,
    clear_session_cookies,
    create_session,
    current_user_optional,
    ensure_csrf_cookie,
    get_valid_session,
    hash_password,
    normalize_email,
    password_needs_rehash,
    require_user,
    revoke_session,
    set_session_cookies,
    validate_email,
    validate_password,
    verify_password,
)
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 用户不存在时也跑一次哈希校验，拉平响应时间，避免通过耗时差异枚举已注册邮箱
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class CredentialsIn(BaseModel):
    email: str
    password: str


def _user_out(user: User) -> dict:
    """只暴露必要字段：绝不返回 password_hash"""
    return {"id": user.id, "email": user.email, "created_at": user.created_at}


@router.get("/csrf")
def get_csrf(request: Request, response: Response):
    """发放 CSRF 令牌（前端启动时调用一次；同时种下 cookie）"""
    return {"csrf_token": ensure_csrf_cookie(response, request)}


@router.post("/register")
def register(req: CredentialsIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """注册并直接登录"""
    email = normalize_email(req.email)
    try:
        validate_email(email)
        validate_password(req.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册")

    user = User(email=email, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token, session = create_session(db, user)
    set_session_cookies(response, request, token, session.csrf_token)
    return _user_out(user)


@router.post("/login")
def login(req: CredentialsIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """登录：校验通过后签发服务端会话"""
    email = normalize_email(req.email)
    user = db.query(User).filter(User.email == email).first()

    if user is None:
        verify_password(_DUMMY_HASH, req.password)  # 拉平耗时
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码不正确")
    if not verify_password(user.password_hash, req.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码不正确")

    # 参数升级（例如以后调高 Argon2 强度）时顺手重算哈希
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
    from datetime import datetime, timezone

    user.last_login_at = datetime.now(timezone.utc).isoformat()
    db.commit()

    token, session = create_session(db, user)
    set_session_cookies(response, request, token, session.csrf_token)
    return _user_out(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """退出：服务端吊销会话 + 清除 Cookie（前端只清本地状态）"""
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    session = get_valid_session(db, token)
    if session:
        revoke_session(db, session)
    clear_session_cookies(response, request)
    return {"message": "已退出登录"}


@router.get("/me")
def me(
    request: Request,
    response: Response,
    user: User | None = Depends(current_user_optional),
):
    """当前登录用户；未登录返回 401"""
    # 顺带确保前端手里有 CSRF 令牌（否则首次写请求会被拦）
    ensure_csrf_cookie(response, request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return _user_out(user)