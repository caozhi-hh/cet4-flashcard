/**
 * 单词书选择 — localStorage 持久化
 * 用户选择的单词书 ID 存在 localStorage，全应用共享
 */

const STORAGE_KEY = "cet4_wordbook_id";
const DEFAULT_WORDBOOK = "core1000";

/** 获取当前选中的单词书 ID */
export function getSelectedWordbook(): string {
  if (typeof window === "undefined") return DEFAULT_WORDBOOK;
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_WORDBOOK;
}

/** 设置选中的单词书 ID */
export function setSelectedWordbook(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, id);
  // 触发自定义事件，让其他组件感知变化
  window.dispatchEvent(new Event("wordbook-changed"));
}

/** 订阅单词书变化 */
export function onWordbookChange(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("wordbook-changed", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("wordbook-changed", callback);
    window.removeEventListener("storage", callback);
  };
}
