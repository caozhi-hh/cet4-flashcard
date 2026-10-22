/** API 调用封装 */

// 合并部署：前端和后端同源，API 用相对路径 /api/...
// 本地 dev（前端3000 后端8000 跨端口）才需要 NEXT_PUBLIC_API_URL
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// 单次请求超时：后端没启动时不要让页面无限转圈
const TIMEOUT_MS = 15000;

// 与后端 app/config.py 保持一致（Cookie 名 / CSRF 头名）
const CSRF_COOKIE = "cet4_csrf";
const CSRF_HEADER = "X-CSRF-Token";
/** 会话失效（401）时广播，由 AuthGate 统一处理跳转，避免每页各写一遍 */
export const UNAUTHORIZED_EVENT = "cet4:unauthorized";

/** 带 HTTP 状态码的错误：401 需要被单独识别（会话过期/未登录） */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function readCookie(name: string): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

/** 取 CSRF 令牌；没有就先领一个（令牌会随登录/注册轮换，所以每次都重新读 cookie） */
async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  try {
    await fetch(`${API_BASE}/api/auth/csrf`, { credentials: "include" });
  } catch {
    // 领不到就返回空串，让后端以 403 明确拒绝，而不是在这里抛网络错误
  }
  return readCookie(CSRF_COOKIE);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options?.headers as Record<string, string>) ?? {}),
  };

  // 写请求必须带 CSRF 头（后端对所有 /api 写请求强制校验）
  if (method !== "GET" && method !== "HEAD") {
    const token = await ensureCsrfToken();
    if (token) headers[CSRF_HEADER] = token;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      // Cookie 会话认证：同源与本地跨端口 dev 都必须带上凭证
      credentials: "include",
      signal: AbortSignal.timeout(TIMEOUT_MS),
      ...options,
      headers,
    });
  } catch (err) {
    // 网络层失败（服务没启动 / 断网 / 超时）：抛出可读原因。
    // 否则各页面只能看到"空数据"，会把"服务挂了"显示成"今天没有新词啦"。
    const timeout = err instanceof Error && err.name === "TimeoutError";
    throw new Error(timeout ? "请求超时，请确认后端服务在运行" : "无法连接后端服务，请确认服务已启动");
  }

  if (!res.ok) {
    // 透出 FastAPI 的 {"detail": ...}，让失败原因直接可见
    let detail = "";
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // 响应不是 JSON：下面用状态码兜底
    }
    if (res.status === 401 && typeof window !== "undefined") {
      // 会话过期/未登录：广播出去，由 AuthGate 统一引导到登录页
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(detail || `请求失败（HTTP ${res.status}）`, res.status);
  }
  return res.json();
}

/** 认证 */
export const authApi = {
  /** 当前登录用户；未登录时抛 ApiError(401) */
  me: () => request<AuthUser>("/api/auth/me"),
  /** 领取 CSRF 令牌（页面启动时调用一次即可） */
  csrf: () => request<{ csrf_token: string }>("/api/auth/csrf"),
  login: (email: string, password: string) =>
    request<AuthUser>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string) =>
    request<AuthUser>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ message: string }>("/api/auth/logout", { method: "POST" }),
};

/** 学习计划 */
export const planApi = {
  /** 可选学习目标（含各自默认词书）与每日新词量范围 */
  options: () =>
    request<{ goals: GoalOption[]; daily_new_words_range: { min: number; max: number } }>(
      "/api/plan/options"
    ),
  /** 当前用户的计划；未设置时 has_plan=false */
  get: () => request<{ has_plan: boolean; plan: StudyPlan | null }>("/api/plan"),
  save: (payload: {
    goal_type: string;
    wordbook_key: string | null;
    target_date: string | null;
    daily_new_words: number;
  }) =>
    request<{ has_plan: boolean; plan: StudyPlan }>("/api/plan", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  forecast: () => request<PlanForecast>("/api/plan/forecast"),
};

/** 分级阅读 */
export const readingApi = {
  /** 文章列表（可按难度与学习目标筛选；公共内容） */
  list: (level?: string, goal?: string) => {
    const params = new URLSearchParams();
    if (level) params.set("level", level);
    if (goal) params.set("goal", goal);
    const qs = params.toString();
    return request<{ articles: ReadingArticleSummary[]; total: number; levels: string[] }>(
      `/api/reading/articles${qs ? `?${qs}` : ""}`
    );
  },
  /** 文章详情（含分词渲染项；**不含正确答案**） */
  detail: (slug: string) => request<ReadingArticleDetail>(`/api/reading/articles/${slug}`),
  /** 点词查义：服务端只做精确匹配 */
  lookup: (word: string) =>
    request<{
      found: boolean;
      word: string;
      headword?: string;
      definition?: string;
      phonetic?: string | null;
      tags?: string | null;
      status?: string;
      message?: string;
    }>(`/api/reading/lookup?word=${encodeURIComponent(word)}`),
  /** 提交作答：分数由服务端判定，客户端不传分数 */
  submit: (
    slug: string,
    answers: { question_id: string; choice: number }[],
    durationSeconds: number
  ) =>
    request<ReadingAttemptResult>("/api/reading/attempts", {
      method: "POST",
      body: JSON.stringify({ slug, answers, duration_seconds: durationSeconds }),
    }),
  /** 当前用户的阅读进度与历史 */
  progress: () => request<ReadingProgress>("/api/reading/progress"),
};

/** 学习 */
export const studyApi = {
  getToday: (wordbook?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (wordbook) params.set("wordbook", wordbook);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    return request<{ type: string; words: FlashCard[]; total: number }>(
      `/api/study/today${qs ? `?${qs}` : ""}`
    );
  },
  getReview: () => request<{ type: string; words: FlashCard[]; total: number }>("/api/study/review"),
  /** 预览四档评分各自的下次间隔（只读，供卡片按钮显示提示） */
  preview: (wordId: number) =>
    request<{ word_id: number; ratings: RatingPreview[] }>(`/api/study/preview?word_id=${wordId}`),
  /** 默写本章：取今天学过的词（当天没学过则回落到今日新词） */
  getDictation: (limit = 20) =>
    request<{ type: string; words: FlashCard[]; total: number }>(`/api/study/dictation?limit=${limit}`),
  /** 提交四档评分。rating: 1 重来 / 2 困难 / 3 良好 / 4 简单 */
  submit: (wordId: number, rating: Rating) =>
    request<StudyResponse>("/api/study/record", {
      method: "POST",
      body: JSON.stringify({ word_id: wordId, rating }),
    }),
};

/** 测验 */
export const quizApi = {
  getDaily: () => request<{ questions: QuizQuestion[]; total: number }>("/api/quiz/daily"),
  // 只提交题号与作答：正确答案在服务端，前端不再传递、也无法影响判分
  submit: (answers: { word_id: number; answer: string }[]) =>
    request<QuizResult>("/api/quiz/submit", {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
};

/** 进度 */
export const progressApi = {
  getOverview: (wordbook?: string) =>
    request<ProgressOverview>(`/api/progress/overview${wordbook ? `?wordbook=${wordbook}` : ""}`),
  getCalendar: (days = 30) => request<DailyProgress[]>(`/api/progress/calendar?days=${days}`),
};

/** 单词书 */
export const wordbookApi = {
  list: () => request<Wordbook[]>("/api/wordbooks"),
  get: (id: string) => request<Wordbook>(`/api/wordbooks/${id}`),
  aiGenerate: (query: string) =>
    request<Wordbook>("/api/wordbooks/ai-generate", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  remove: (id: string) =>
    request<{ message: string }>(`/api/wordbooks/${id}`, { method: "DELETE" }),
};

/** AI */
export const aiApi = {
  getMnemonic: (wordId: number) =>
    request<{ word_id: number; word: string; mnemonic: string }>("/api/ai/mnemonic", {
      method: "POST",
      body: JSON.stringify({ word_id: wordId }),
    }),
};

/** 生词本/错题本 */
export const starredApi = {
  list: (type?: "star" | "hard") =>
    request<{ words: StarredWord[]; total: number }>(
      `/api/starred${type ? `?type=${type}` : ""}`
    ),
  add: (wordId: number, type: "star" | "hard" = "star") =>
    request<{ message: string }>("/api/starred", {
      method: "POST",
      body: JSON.stringify({ word_id: wordId, type }),
    }),
  remove: (wordId: number, type: "star" | "hard" = "star") =>
    request<{ message: string }>(`/api/starred/${wordId}?type=${type}`, { method: "DELETE" }),
  ids: () => request<{ stars: number[]; hards: number[] }>("/api/starred/ids"),
};

/** 类型导入 */
import type { AuthUser, FlashCard, StudyResponse, Rating, RatingPreview, QuizQuestion, QuizResult, ProgressOverview, DailyProgress, Wordbook, StarredWord, GoalOption, StudyPlan, PlanForecast, ReadingArticleSummary, ReadingArticleDetail, ReadingAttemptResult, ReadingProgress } from "./types";