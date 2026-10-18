/** API 调用封装 */

// 合并部署：前端和后端同源，API 用相对路径 /api/...
// 本地 dev（前端3000 后端8000 跨端口）才需要 NEXT_PUBLIC_API_URL
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// 单次请求超时：后端没启动时不要让页面无限转圈
const TIMEOUT_MS = 15000;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(TIMEOUT_MS),
      ...options,
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
    throw new Error(detail || `请求失败（HTTP ${res.status}）`);
  }
  return res.json();
}

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
  submit: (answers: { word_id: number; answer: string; correct_answer: string }[]) =>
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
import type { FlashCard, StudyResponse, Rating, RatingPreview, QuizQuestion, QuizResult, ProgressOverview, DailyProgress, Wordbook, StarredWord } from "./types";
