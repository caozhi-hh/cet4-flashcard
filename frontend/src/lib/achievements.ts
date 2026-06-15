/**
 * 成就徽章系统 — 基于学习数据计算，纯前端无需后端
 */
import type { ProgressOverview } from "./types";

export interface Achievement {
  id: string;
  icon: string;
  name: string;
  desc: string;
  /** 判定函数：当前进度是否解锁 */
  unlocked: (p: ProgressOverview, extra?: AchievementExtra) => boolean;
  /** 解锁阈值，用于显示进度 */
  threshold?: { current: (p: ProgressOverview) => number; target: number };
}

export interface AchievementExtra {
  createdAiWordbook?: boolean; // 是否创建过 AI 词书
  quizPerfect?: boolean;       // 是否测验满分过
}

export const ACHIEVEMENTS: Achievement[] = [
  // 词汇量里程碑
  { id: "seed", icon: "🌱", name: "初心萌芽", desc: "学会第 1 个单词", unlocked: (p) => p.learned_words >= 1, threshold: { current: (p) => p.learned_words, target: 1 } },
  { id: "sprout", icon: "🌿", name: "小有所成", desc: "学会 50 个单词", unlocked: (p) => p.learned_words >= 50, threshold: { current: (p) => p.learned_words, target: 50 } },
  { id: "scholar", icon: "📖", name: "勤学者", desc: "学会 200 个单词", unlocked: (p) => p.learned_words >= 200, threshold: { current: (p) => p.learned_words, target: 200 } },
  { id: "century", icon: "🎯", name: "百词斩", desc: "学会 500 个单词", unlocked: (p) => p.learned_words >= 500, threshold: { current: (p) => p.learned_words, target: 500 } },
  { id: "master", icon: "🏆", name: "千词通", desc: "学会 1000 个单词", unlocked: (p) => p.learned_words >= 1000, threshold: { current: (p) => p.learned_words, target: 1000 } },

  // 掌握度
  { id: "known10", icon: "⭐", name: "初掌握", desc: "掌握 10 个单词", unlocked: (p) => p.known_words >= 10, threshold: { current: (p) => p.known_words, target: 10 } },
  { id: "known100", icon: "💎", name: "精通百词", desc: "掌握 100 个单词", unlocked: (p) => p.known_words >= 100, threshold: { current: (p) => p.known_words, target: 100 } },
  { id: "known500", icon: "👑", name: "词汇王者", desc: "掌握 500 个单词", unlocked: (p) => p.known_words >= 500, threshold: { current: (p) => p.known_words, target: 500 } },

  // 坚持打卡
  { id: "streak3", icon: "🔥", name: "三日之约", desc: "连续学习 3 天", unlocked: (p) => p.streak_days >= 3, threshold: { current: (p) => p.streak_days, target: 3 } },
  { id: "streak7", icon: "🔥", name: "一周坚持", desc: "连续学习 7 天", unlocked: (p) => p.streak_days >= 7, threshold: { current: (p) => p.streak_days, target: 7 } },
  { id: "streak30", icon: "🌟", name: "月度达人", desc: "连续学习 30 天", unlocked: (p) => p.streak_days >= 30, threshold: { current: (p) => p.streak_days, target: 30 } },

  // 特殊成就
  { id: "ai_explore", icon: "🤖", name: "AI 探索者", desc: "创建第一本 AI 词书", unlocked: (_p, e) => !!e?.createdAiWordbook },
  { id: "quiz_perfect", icon: "✍️", name: "测验达人", desc: "测验获得满分", unlocked: (_p, e) => !!e?.quizPerfect },
];

/** 计算所有徽章的解锁状态 */
export function evaluateAchievements(p: ProgressOverview, extra?: AchievementExtra) {
  return ACHIEVEMENTS.map((a) => {
    const unlocked = a.unlocked(p, extra);
    const progress = a.threshold
      ? Math.min(a.threshold.current(p) / a.threshold.target, 1)
      : unlocked
        ? 1
        : 0;
    return { ...a, unlocked, progress };
  });
}

/** 统计已解锁数 */
export function countUnlocked(list: ReturnType<typeof evaluateAchievements>): number {
  return list.filter((a) => a.unlocked).length;
}
