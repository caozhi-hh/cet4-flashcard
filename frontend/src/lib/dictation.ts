/**
 * 默写的量化统计（借鉴 qwerty-learner 的"速度 / 正确率"反馈）
 *
 * 抽成纯函数是为了能真测：正确率、平均用时、CPM、WPM 都直接在这里断言，
 * 而不是靠界面截图估。
 */

/** 归一化输入：忽略大小写与首尾空白（默写不该因为多打空格算错） */
export function normalizeAnswer(input: string): string {
  return input.trim().toLowerCase();
}

/** 判断一次输入是否正确 */
export function isCorrect(input: string, expected: string): boolean {
  return normalizeAnswer(input) === normalizeAnswer(expected);
}

export interface WordAttempt {
  wordId: number;
  /** 正确答案 */
  word: string;
  /** 尝试次数（第一次就对 = 1） */
  attempts: number;
  /** 最终是否答对 */
  correct: boolean;
  /** 该词用时（毫秒） */
  elapsedMs: number;
  /** 该词输入过的字符数（含打错重来的） */
  typedChars: number;
}

export interface DictationStats {
  total: number;
  /** 一次就对的词数 */
  firstTryCorrect: number;
  /** 最终答对的词数 */
  correct: number;
  /** 正确率（一次就对 / 总数），0-100 */
  accuracy: number;
  elapsedMs: number;
  typedChars: number;
  /** 字符/分钟 */
  cpm: number;
  /** 词/分钟，按业界标准"5 字符 = 1 词"折算 */
  wpm: number;
  /** 平均每词用时（秒） */
  avgSecondsPerWord: number;
  /** 答错的词 */
  wrong: string[];
}

const round1 = (n: number) => Math.round(n * 10) / 10;

export function computeStats(attempts: WordAttempt[]): DictationStats {
  const total = attempts.length;
  const firstTryCorrect = attempts.filter((a) => a.correct && a.attempts === 1).length;
  const correct = attempts.filter((a) => a.correct).length;
  const elapsedMs = attempts.reduce((sum, a) => sum + a.elapsedMs, 0);
  const typedChars = attempts.reduce((sum, a) => sum + a.typedChars, 0);

  const minutes = elapsedMs / 60000;
  // 用时不可能是 0（否则除零）；极短用时按最小值兜底，避免算出天文数字的速度
  const safeMinutes = Math.max(minutes, 1 / 60);

  return {
    total,
    firstTryCorrect,
    correct,
    accuracy: total === 0 ? 0 : round1((firstTryCorrect / total) * 100),
    elapsedMs,
    typedChars,
    cpm: round1(typedChars / safeMinutes),
    wpm: round1(typedChars / 5 / safeMinutes),
    avgSecondsPerWord: total === 0 ? 0 : round1(elapsedMs / total / 1000),
    wrong: attempts.filter((a) => !a.correct).map((a) => a.word),
  };
}

/** 把毫秒格式化成 mm:ss */
export function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 历史成绩（存 localStorage，用于进度页展示量化反馈） */
export interface DictationHistory {
  sessions: number;
  lastAt: string | null;
  lastAccuracy: number;
  lastCpm: number;
  bestAccuracy: number;
  bestCpm: number;
}

const HISTORY_KEY = "cet4_dictation_stats_v1";

export const EMPTY_HISTORY: DictationHistory = {
  sessions: 0,
  lastAt: null,
  lastAccuracy: 0,
  lastCpm: 0,
  bestAccuracy: 0,
  bestCpm: 0,
};

export function readHistory(): DictationHistory {
  if (typeof window === "undefined") return EMPTY_HISTORY;
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return EMPTY_HISTORY;
    const parsed = JSON.parse(raw) as Partial<DictationHistory>;
    return { ...EMPTY_HISTORY, ...parsed };
  } catch {
    // 数据坏了就当没有，不能因为一段历史把页面搞崩
    return EMPTY_HISTORY;
  }
}

/** 记录一次默写成绩，返回更新后的历史 */
export function recordHistory(stats: {
  accuracy: number;
  cpm: number;
}): DictationHistory {
  const prev = readHistory();
  const next: DictationHistory = {
    sessions: prev.sessions + 1,
    lastAt: new Date().toISOString(),
    lastAccuracy: stats.accuracy,
    lastCpm: stats.cpm,
    bestAccuracy: Math.max(prev.bestAccuracy, stats.accuracy),
    bestCpm: Math.max(prev.bestCpm, stats.cpm),
  };
  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    } catch {
      // 隐私模式/超额时写不进去也不该影响默写本身
    }
  }
  return next;
}