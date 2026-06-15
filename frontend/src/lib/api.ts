/** API 调用封装 */

// 合并部署：前端和后端同源，API 用相对路径 /api/...
// 本地 dev（前端3000 后端8000 跨端口）才需要 NEXT_PUBLIC_API_URL
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
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
  submit: (wordId: number, known: boolean) =>
    request<StudyResponse>("/api/study/record", {
      method: "POST",
      body: JSON.stringify({ word_id: wordId, known }),
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
import type { FlashCard, StudyResponse, QuizQuestion, QuizResult, ProgressOverview, DailyProgress, Wordbook, StarredWord } from "./types";
