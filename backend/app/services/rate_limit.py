"""轻量内存限流

为什么需要：AI 接口有真实成本，仅靠"必须登录"挡不住单个账号刷调用。
上线前先加一道最简闸门 —— 不引入 Redis、不加中间件、不改架构：
    - 按（桶名 + 用户）在内存里滑窗计数；
    - 进程重启即清零；多副本部署时按副本各算一份（对当前单实例部署足够）。
"""

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, status

from ..auth import require_user
from ..models import User

# 桶 → 时间戳队列
_windows: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """超过 limit 次 / window_seconds 抛 429（带 Retry-After）"""
    if limit <= 0:
        return
    now = time.monotonic()
    queue = _windows[key]
    while queue and now - queue[0] > window_seconds:
        queue.popleft()
    if len(queue) >= limit:
        retry_after = int(window_seconds - (now - queue[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"请求过于频繁，请 {retry_after} 秒后再试",
            headers={"Retry-After": str(retry_after)},
        )
    queue.append(now)


def reset_rate_limits() -> None:
    """清空计数（测试用）"""
    _windows.clear()


def ai_rate_limit(bucket: str, limit: int, window_seconds: int = 3600):
    """生成一个依赖：对当前登录用户在该桶上限流

    用法：@router.post("/x", dependencies=[Depends(ai_rate_limit("x", 20))])
    """
    def _dependency(user: User = Depends(require_user)) -> None:
        check_rate_limit(f"{bucket}:{user.id}", limit, window_seconds)

    return _dependency