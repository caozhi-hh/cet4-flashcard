/**
 * 用户设置 — localStorage 持久化
 */

const GOAL_KEY = "cet4_daily_goal";
export const DEFAULT_GOAL = 20;
export const GOAL_OPTIONS = [10, 20, 30, 50];

/** 获取每日学习目标 */
export function getDailyGoal(): number {
  if (typeof window === "undefined") return DEFAULT_GOAL;
  const v = Number(localStorage.getItem(GOAL_KEY));
  return GOAL_OPTIONS.includes(v) ? v : DEFAULT_GOAL;
}

/** 设置每日学习目标 */
export function setDailyGoal(n: number): void {
  if (typeof window === "undefined") return;
  if (GOAL_OPTIONS.includes(n)) {
    localStorage.setItem(GOAL_KEY, String(n));
    window.dispatchEvent(new Event("goal-changed"));
  }
}

/** 订阅目标变化 */
export function onGoalChange(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("goal-changed", cb);
  return () => window.removeEventListener("goal-changed", cb);
}
