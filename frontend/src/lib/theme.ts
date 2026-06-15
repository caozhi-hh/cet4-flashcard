/**
 * 主题切换 — 亮/暗模式，localStorage 持久化
 */

const STORAGE_KEY = "cet4_theme";

export type Theme = "light" | "dark";

/** 获取当前主题 */
export function getTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  // 未设置时跟随系统偏好
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** 应用主题到 <html> 标签 */
export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (theme === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

/** 切换主题并持久化，返回新主题 */
export function toggleTheme(): Theme {
  const next: Theme = getTheme() === "dark" ? "light" : "dark";
  localStorage.setItem(STORAGE_KEY, next);
  applyTheme(next);
  window.dispatchEvent(new Event("theme-changed"));
  return next;
}

/** 初始化主题（在组件挂载时调用，应用已保存的偏好） */
export function initTheme(): void {
  applyTheme(getTheme());
}

/** 订阅主题变化 */
export function onThemeChange(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("theme-changed", callback);
  return () => window.removeEventListener("theme-changed", callback);
}
