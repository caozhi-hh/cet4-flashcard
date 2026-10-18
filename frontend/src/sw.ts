/// <reference lib="webworker" />
/**
 * 四级背单词 — Service Worker（Serwist）
 *
 * 构建方式：serwist.config.js + `npm run build:sw`（在 next build 之后执行），
 * 由 @serwist/cli 用 esbuild 打包本文件，并把 out/ 里静态产物的预缓存清单
 * 注入到下面 __SW_MANIFEST 的位置。
 *
 * 离线策略：
 *   1. 页面路由（/、/study、/review …）在安装时按真实 URL 抓取并预缓存 → 断网也能打开；
 *   2. 静态资源（JS/CSS/图标）由 CLI 生成的清单预缓存；
 *   3. /api 的 GET 请求走 NetworkFirst（在线时数据新鲜，断网回落到上次缓存）；
 *   4. /api 的写请求不做任何处理 → 直接走网络。离线时应当明确报错，
 *      而不是被缓存"假成功"（前端已有失败提示，不会静默推进卡片）。
 */
import { CacheFirst, ExpirationPlugin, NetworkFirst, Serwist } from "serwist";

declare const self: ServiceWorkerGlobalScope & {
  /** 由 @serwist/cli 在构建时注入（见 serwist.config.js 的 injectionPoint） */
  __SW_MANIFEST: (string | { url: string; revision: string | null })[];
};

/**
 * 需要离线可打开的页面路由。
 *
 * 为什么不用 glob 出来的 .html：静态导出的产物文件是 `study.html`，而浏览器地址是 `/study`。
 * 预缓存是按精确 URL 匹配的，`/study` 匹配不到 `/study.html`（已实测：本版本 serwist 的
 * cleanURLs 选项对 `/study → /study.html` 不生效）。
 * 所以这里按真实访问地址声明，安装时由浏览器去抓 —— 这一步是联网的，没问题。
 */
const PAGE_ROUTES = ["/", "/study", "/review", "/dictation", "/quiz", "/progress", "/starred", "/wordbooks"];

const serwist = new Serwist({
  precacheEntries: [
    // revision 显式给 null：这些 HTML 每次安装都重新抓取，避免拿到旧页面
    ...PAGE_ROUTES.map((url) => ({ url, revision: null })),
    ...self.__SW_MANIFEST,
  ],
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    {
      // 读接口：优先走网络，保证进度/词卡数据新鲜；断网时回落到上次缓存
      matcher: ({ url, request }) => request.method === "GET" && url.pathname.startsWith("/api/"),
      handler: new NetworkFirst({
        cacheName: "cet4-api-get",
        networkTimeoutSeconds: 4,
        plugins: [new ExpirationPlugin({ maxEntries: 60, maxAgeSeconds: 7 * 24 * 60 * 60 })],
      }),
    },
    {
      // 图标等图片资源：缓存优先
      matcher: ({ request }) => request.destination === "image",
      handler: new CacheFirst({
        cacheName: "cet4-images",
        plugins: [new ExpirationPlugin({ maxEntries: 40, maxAgeSeconds: 30 * 24 * 60 * 60 })],
      }),
    },
  ],
});

serwist.addEventListeners();