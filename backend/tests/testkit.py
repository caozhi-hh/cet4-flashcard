"""测试工具：带认证的 HTTP 客户端

为什么需要它：
    引入 Cookie 会话后，所有写请求都要带 CSRF 头，且注册/登录后 CSRF 令牌会轮换。
    若在每个用例里手写 header，既啰嗦又容易漏。AuthClient 封装了"自动带 CSRF + 默认已登录"，
    用法与 TestClient 完全一致（.get/.post/.delete），既有用例几乎不用改。

注意：每个 AuthClient 有独立的 cookie jar，因此它天然代表"另一个浏览器/另一个用户"，
可用于验证 A/B 两个用户之间的数据隔离。
"""

import secrets

from fastapi.testclient import TestClient

from app.auth import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

PASSWORD = "password123"


def fresh_email(prefix: str = "u") -> str:
    """每次生成不同邮箱，避免用例之间互相撞唯一约束"""
    return f"{prefix}-{secrets.token_hex(6)}@example.com"


def ensure_csrf_token(client: TestClient) -> str:
    """读取当前 CSRF 令牌；没有就先领一个（令牌会随登录/注册轮换，所以每次都重新读）"""
    token = client.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        client.get("/api/auth/csrf")
        token = client.cookies.get(CSRF_COOKIE_NAME)
    return token or ""


def csrf_headers(client: TestClient) -> dict:
    return {CSRF_HEADER_NAME: ensure_csrf_token(client)}


def register(client: TestClient, email: str | None = None, password: str = PASSWORD) -> str:
    """注册并自动登录，返回**服务端规范化后**的邮箱"""
    email = email or fresh_email()
    res = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )
    assert res.status_code == 200, f"注册失败：{res.status_code} {res.text[:200]}"
    return res.json()["email"]


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )


def logout(client: TestClient):
    return client.post("/api/auth/logout", headers=csrf_headers(client))


class AuthClient:
    """已登录 + 自动携带 CSRF 的测试客户端"""

    def __init__(self, app, email: str | None = None, password: str = PASSWORD, do_register: bool = True):
        self._client = TestClient(app)
        self.password = password
        self.email = register(self._client, email, password) if do_register else None

    # --- 透出常用属性 ---
    @property
    def cookies(self):
        return self._client.cookies

    @property
    def raw(self) -> TestClient:
        """底层 TestClient（需要手动控制 header/cookie 时用）"""
        return self._client

    # --- 代理请求，写方法自动补 CSRF ---
    def _with_csrf(self, kwargs: dict) -> dict:
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault(CSRF_HEADER_NAME, ensure_csrf_token(self._client))
        kwargs["headers"] = headers
        return kwargs

    def get(self, url, **kwargs):
        return self._client.get(url, **kwargs)

    def post(self, url, **kwargs):
        return self._client.post(url, **self._with_csrf(kwargs))

    def put(self, url, **kwargs):
        return self._client.put(url, **self._with_csrf(kwargs))

    def patch(self, url, **kwargs):
        return self._client.patch(url, **self._with_csrf(kwargs))

    def delete(self, url, **kwargs):
        return self._client.delete(url, **self._with_csrf(kwargs))