"""静态路由回归测试 — 防止子页"直达/刷新"错误返回首页

红灯背景：
    Next.js 用 output:export 静态导出时，页面产物是 static/study.html（非 trailingSlash 模式）。
    而 main.py 的兜底逻辑原先只查找 static/<route>/index.html，找不到就回落到首页，
    导致直接访问或刷新 /study、/quiz 等子页时拿到的是首页（点击导航走客户端路由才正常）。

运行方式（二选一）：
    python tests/test_static_routes.py     # 无需 pytest
    pytest tests/test_static_routes.py
"""

import json
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

# 允许用 `python tests/test_static_routes.py` 直接运行
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402  必须在 sys.path 处理之后导入

STATIC_DIR = BACKEND_DIR / "static"

# 刻意不使用 with TestClient(app)：不触发 lifespan，避免测试触碰真实数据库
client = TestClient(app)

# 需要"直达也能打开"的页面路由
PAGE_ROUTES = ["/login", "/plan", "/reading", "/study", "/review", "/dictation", "/quiz", "/progress", "/wordbooks", "/starred"]

# Service Worker 里要预缓存的页面路由（含首页），必须与 frontend/src/sw.ts 的 PAGE_ROUTES 一致
SW_PAGE_ROUTES = ["/", "/login", "/plan", "/reading", "/study", "/review", "/dictation", "/quiz", "/progress", "/starred", "/wordbooks"]

# create-next-app 留下的、项目从未引用的示例资源
SCAFFOLD_SVGS = ["next.svg", "vercel.svg", "file.svg", "globe.svg", "window.svg"]


def _get(path: str) -> bytes:
    """请求路径，断言 200，返回响应体字节"""
    res = client.get(path)
    assert res.status_code == 200, f"{path} 期望 200，实际 {res.status_code}"
    return res.content


def _expected_html(route: str) -> Path:
    """路由对应的静态页面文件，如 /study → static/study.html"""
    return STATIC_DIR / f"{route.lstrip('/')}.html"


def test_root_serves_home():
    """/ 必须仍返回首页（防兜底改动造成回归）"""
    assert _get("/") == (STATIC_DIR / "index.html").read_bytes()


def test_page_routes_serve_their_own_html():
    """每个子页直达时返回自己的 HTML，而不是首页"""
    home = (STATIC_DIR / "index.html").read_bytes()
    for route in PAGE_ROUTES:
        expected = _expected_html(route)
        assert expected.is_file(), f"缺少静态产物 {expected}"
        body = _get(route)
        assert body != home, f"{route} 返回的是首页，不是 {expected.name}"
        assert body == expected.read_bytes(), f"{route} 返回内容与 {expected.name} 不一致"


def test_page_routes_with_trailing_slash():
    """带尾斜杠同样命中正确页面"""
    for route in PAGE_ROUTES:
        expected = _expected_html(route)
        assert _get(route + "/") == expected.read_bytes(), f"{route}/ 未命中 {expected.name}"


def test_unknown_route_falls_back_to_home():
    """未知路由仍回落首页（保持原有行为，不算回归）"""
    assert _get("/no-such-page-xyz") == (STATIC_DIR / "index.html").read_bytes()


def test_next_static_asset_still_served():
    """兜底改动不能弄坏 /_next 静态资源"""
    assets = sorted((STATIC_DIR / "_next").rglob("*.css"))
    assert assets, "未找到 _next 下的 css 产物"
    target = assets[0]
    rel = target.relative_to(STATIC_DIR).as_posix()
    assert _get("/" + rel) == target.read_bytes(), f"/{rel} 未正确返回"


def test_pwa_assets_served():
    """PWA 清单与图标可访问"""
    manifest = STATIC_DIR / "manifest.webmanifest"
    assert manifest.is_file(), "缺少 manifest.webmanifest"
    assert _get("/manifest.webmanifest") == manifest.read_bytes()
    icons = sorted((STATIC_DIR / "icons").glob("*.png"))
    assert icons, "缺少 PWA 图标"
    for icon in icons:
        assert _get("/icons/" + icon.name) == icon.read_bytes(), f"/icons/{icon.name} 未正确返回"


def test_build_has_no_baked_api_host():
    """构建产物不得把 API 基址烧成绝对地址 http://localhost:8000

    红灯背景：
        前端 lib/api.ts 用 NEXT_PUBLIC_API_URL 作为 API 基址，该变量在 next build 时被内联。
        frontend/.env.local 里写着 http://localhost:8000，而 .env.local 在 production 构建时
        同样会被加载（优先级高于 .env.production），于是产物里出现 fetch(`http://localhost:8000...`)。
        后果：用 127.0.0.1 或局域网 IP 打开页面时请求打到别处——127.0.0.1 场景被 CORS 拦截、
        手机场景直接指向手机自己的 localhost:8000，表现为"页面能打开但没有任何数据"。
        合并部署（前后端同源）必须使用相对路径 /api/...，即该变量在生产构建中为空。
    """
    chunks = sorted((STATIC_DIR / "_next").rglob("*.js"))
    assert chunks, "未找到 /_next 下的 js 产物"
    offenders = [
        p.relative_to(STATIC_DIR).as_posix()
        for p in chunks
        if "localhost:8000" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"以下产物烧入了 localhost:8000（共 {len(offenders)} 个）：{offenders[:5]}"


def test_service_worker_served_and_complete():
    """Service Worker 必须被构建出来、能访问，且预缓存清单完整

    离线能力依赖三件事同时成立，缺任何一条都会"看起来装了 PWA 但断网打不开"：
      1. sw.js 存在且可访问；
      2. 预缓存清单已注入（占位符被替换）；
      3. 七个页面路由按**真实访问地址**进清单 ——
         静态导出的文件名是 study.html，而浏览器地址是 /study，
         预缓存按精确 URL 匹配，靠 .html 清单或 cleanURLs 都命不中（已实测）。
    """
    sw = STATIC_DIR / "sw.js"
    assert sw.is_file(), "构建产物缺少 sw.js：离线能力缺失"

    body = _get("/sw.js")
    assert body == sw.read_bytes(), "sw.js 返回内容与构建产物不一致"
    text = body.decode("utf-8", errors="ignore")

    assert "__SW_MANIFEST" not in text, "预缓存清单占位符没有被注入"

    # 页面路由在产物里是运行时构造的数组字面量（...vt.map(e=>({url:e,revision:null}))），
    # 所以抽出那个数组按集合比对；必须与 frontend/src/sw.ts 的 PAGE_ROUTES 保持一致。
    hit = re.search(r'\["/"[^\]]*\]', text)
    assert hit, "sw.js 里找不到页面路由数组"
    found = set(json.loads(hit.group(0)))
    assert found == set(SW_PAGE_ROUTES), (
        f"预缓存页面路由不符：缺少 {sorted(set(SW_PAGE_ROUTES) - found)}，多出 {sorted(found - set(SW_PAGE_ROUTES))}"
    )
    assert "precacheEntries:[" in text and "revision:null" in text, "页面路由没有合进 precacheEntries"

    revisions = text.count('revision:"')
    assert revisions >= 20, f"预缓存静态资源条目过少：{revisions}"

    # 运行时缓存策略：读接口回落缓存 + 图片缓存优先
    for cache_name in ("cet4-api-get", "cet4-images"):
        assert cache_name in text, f"sw.js 缺少运行时缓存 {cache_name}"


def test_page_script_registers_service_worker():
    """产物里必须带注册代码，否则 sw.js 永远不会被安装（等于没有离线）"""
    chunks = sorted((STATIC_DIR / "_next").rglob("*.js"))
    assert chunks, "未找到 js 产物"
    registrars = [
        p.name
        for p in chunks
        if "serviceWorker" in p.read_text(encoding="utf-8", errors="ignore")
        and "/sw.js" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert registrars, "没有任何产物注册 /sw.js"


def test_no_unused_scaffold_assets():
    """create-next-app 的示例 SVG 必须清掉

    它们没有任何引用，却会被打进产物、进 Service Worker 的预缓存清单，
    白白占用缓存与流量。这条断言防止它们被重新带回来。
    """
    leftovers = [name for name in SCAFFOLD_SVGS if (STATIC_DIR / name).is_file()]
    assert not leftovers, f"产物里仍有未被引用的脚手架资源：{leftovers}"


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in checks:
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL", fn.__name__, "->", exc)
        except Exception as exc:  # 环境问题也要显式暴露，不能静默
            failed += 1
            print("ERROR", fn.__name__, "->", type(exc).__name__, exc)
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)