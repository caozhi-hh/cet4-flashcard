/**
 * Serwist CLI 配置 — 生成 sw.js 并注入预缓存清单
 *
 * 用法：在 next build 之后执行 `npm run build:sw`
 * （package.json 的 build 脚本已经把两者串起来了）
 */
/** @type {import("@serwist/cli").SerwistConfig} */
module.exports = {
  swSrc: "src/sw.ts",
  swDest: "out/sw.js",
  globDirectory: "out",

  // 刻意不含 html：静态导出的页面文件是 study.html，而浏览器地址是 /study，
  // 预缓存按精确 URL 匹配，"/*.html" 的清单对导航毫无用处（已实测）。
  // 页面路由改在 src/sw.ts 里按真实地址显式声明。
  globPatterns: ["**/*.{js,css,png,svg,ico,webmanifest}"],

  // sw.js 自己不能进清单；sourcemap 也没必要预缓存
  globIgnores: ["**/sw.js", "**/*.map"],

  injectionPoint: "self.__SW_MANIFEST",
};