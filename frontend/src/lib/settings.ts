/**
 * 用户设置 — localStorage 持久化
 *
 * 每日新词量的**权威来源是服务端学习计划**（见 lib/planGoal.ts）：
 * 这里的 localStorage 只是它的本地缓存，用于同步读取（学习页取词、首页进度条）。
 * 合法范围与后端 PUT /api/plan 的校验保持一致（1-200）；
 * 否则服务端存了 25、本机却因为"不在选项里"退回 20，两处数字就不一致了。
 */

const GOAL_KEY = "cet4_daily_goal";
export const DEFAULT_GOAL = 20;

/** 快捷选项（只是 UI 便利，不是合法范围） */
export const GOAL_OPTIONS = [10, 20, 30, 50];

/** 合法范围：与后端 plan_service.MIN/MAX_DAILY_NEW_WORDS 一致 */
export const MIN_DAILY_GOAL = 1;
export const MAX_DAILY_GOAL = 200;

export function isValidDailyGoal(n: unknown): n is number {
  return typeof n === "number" && Number.isInteger(n) && n >= MIN_DAILY_GOAL && n <= MAX_DAILY_GOAL;
}

/** 读取本地缓存的每日新词量；非法/缺失时返回默认值 */
export function getDailyGoal(): number {
  if (typeof window === "undefined") return DEFAULT_GOAL;
  const v = Number(localStorage.getItem(GOAL_KEY));
  return isValidDailyGoal(v) ? v : DEFAULT_GOAL;
}

/**
 * 写入本地缓存。
 * 返回是否写入；只有**有效值**才落盘，且仅当可见数值真的变化时才广播
 * （避免"同步到同一个值"引发学习页无谓重取）。
 */
export function setDailyGoal(n: number): boolean {
  if (typeof window === "undefined") return false;
  if (!isValidDailyGoal(n)) return false;

  const raw = localStorage.getItem(GOAL_KEY);
  if (raw === String(n)) return true;

  const before = getDailyGoal();
  localStorage.setItem(GOAL_KEY, String(n));
  if (before !== n) {
    window.dispatchEvent(new Event("goal-changed"));
  }
  return true;
}

/** 订阅目标变化 */
export function onGoalChange(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("goal-changed", cb);
  return () => window.removeEventListener("goal-changed", cb);
}