/**
 * 每日新词量的统一数据契约
 *
 * 规则（唯一权威，所有写入都必须走这里）：
 *   1. 已登录且有服务端计划 → **服务端是权威**，本机只做镜像缓存；
 *   2. 已登录但还没有计划 → 用本机原有偏好，学习流程照常可用（不会因为"空计划"学不了）；
 *   3. 未登录 → 用本机偏好（本模块只在有会话时才被自动调用，读失败也不会清掉用户偏好）；
 *   4. 任何一次失败都**不写本机值**，并如实返回错误 —— 绝不把"新设置"伪装成"已保存"。
 *
 * 之所以要收敛到一个模块：计划页、首页快捷按钮都会改这个数字，
 * 学习页又按它取词。写入路径分散就会重新出现"计划页显示 25、学习页学 20"。
 */

import { planApi } from "@/lib/api";
import type { StudyPlan } from "@/lib/types";
import { getDailyGoal, isValidDailyGoal, setDailyGoal } from "@/lib/settings";

/** 最近一次从服务端读到的计划（内存缓存，避免每次写入都多一次 GET） */
let cachedPlan: StudyPlan | null = null;
let planLoaded = false;

export function getCachedPlan(): StudyPlan | null {
  return cachedPlan;
}

/** 记录已知的服务端计划（计划页保存成功后调用，避免首页再发一次 GET） */
export function setCachedPlan(plan: StudyPlan | null): void {
  cachedPlan = plan;
  planLoaded = true;
}

/** 退出登录/切换账号时清掉上一个用户的计划缓存 */
export function resetPlanCache(): void {
  cachedPlan = null;
  planLoaded = false;
}

export interface GoalResult {
  ok: boolean;
  /** 是否使用了服务端计划（true 表示这次写的是服务端权威值） */
  hasPlan: boolean;
  /** 操作后的实际生效值（失败时是**未变**的旧值） */
  goal: number;
  message?: string;
}

/**
 * 从服务端拉取计划，并把每日新词量镜像到本机缓存。
 * 没有计划时**不覆盖**本机偏好（保留用户原有设置）。
 */
export async function syncPlanGoal(): Promise<GoalResult> {
  try {
    const { has_plan, plan } = await planApi.get();
    setCachedPlan(plan ?? null);

    if (has_plan && plan) {
      if (!setDailyGoal(plan.daily_new_words)) {
        return {
          ok: false,
          hasPlan: true,
          goal: getDailyGoal(),
          message: `服务端计划中的每日新词量超出有效范围（${plan.daily_new_words}），本机设置未改动`,
        };
      }
      return { ok: true, hasPlan: true, goal: getDailyGoal() };
    }
    return { ok: true, hasPlan: false, goal: getDailyGoal() };
  } catch (err) {
    // 读不到就保持本机现值，并明确报告失败（不假装同步成功）
    return {
      ok: false,
      hasPlan: planLoaded && cachedPlan !== null,
      goal: getDailyGoal(),
      message: err instanceof Error ? err.message : "读取学习计划失败",
    };
  }
}

/**
 * 统一的写入路径：有服务端计划就写服务端（同时镜像本机），否则只写本机。
 * 学习页与首页因此永远看到同一个数字。
 */
export async function applyDailyGoal(n: number): Promise<GoalResult> {
  if (!isValidDailyGoal(n)) {
    return {
      ok: false,
      hasPlan: cachedPlan !== null,
      goal: getDailyGoal(),
      message: "每日新词量需在 1-200 之间",
    };
  }

  // 缓存是冷的：先问一次服务端，否则"明明有计划却只改了本机"就又分歧了
  if (!planLoaded) {
    const synced = await syncPlanGoal();
    if (!synced.ok) {
      return {
        ok: false,
        hasPlan: false,
        goal: getDailyGoal(),
        message: synced.message ?? "无法确认学习计划，未修改每日新词量",
      };
    }
  }

  if (!cachedPlan) {
    const applied = setDailyGoal(n);
    return {
      ok: applied,
      hasPlan: false,
      goal: getDailyGoal(),
      message: applied ? undefined : "本机设置写入失败",
    };
  }

  try {
    const res = await planApi.save({
      goal_type: cachedPlan.goal_type,
      wordbook_key: cachedPlan.wordbook_key,
      target_date: cachedPlan.target_date,
      daily_new_words: n,
    });
    setCachedPlan(res.plan);
    setDailyGoal(res.plan.daily_new_words);
    return { ok: true, hasPlan: true, goal: getDailyGoal() };
  } catch (err) {
    // 服务端没写成功 → 本机值保持不动，并把失败原因交回给页面显示
    return {
      ok: false,
      hasPlan: true,
      goal: getDailyGoal(),
      message: err instanceof Error ? err.message : "保存失败",
    };
  }
}