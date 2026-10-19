/** API 类型定义 */

/** 当前登录用户（后端只返回这些字段，绝不包含密码哈希） */
export interface AuthUser {
  id: number;
  email: string;
  created_at: string | null;
}

export interface Word {
  id: number;
  word: string;
  phonetic_us: string | null;
  phonetic_uk: string | null;
  definition: string;
  pos: string | null;
  example: string | null;
  example_cn: string | null;
  /** ECDICT 考试标签，空格分隔，如 "gk cet4 cet6 ky" */
  tags?: string | null;
  /** COCA 语料词频序号（越小越高频） */
  frq?: number | null;
}

export interface FlashCard {
  word: Word;
  status: "new" | "learning" | "known";
  mnemonic?: string | null;
}

/** FSRS 四档评分：1 重来 / 2 困难 / 3 良好 / 4 简单 */
export type Rating = 1 | 2 | 3 | 4;

export interface StudyResponse {
  word_id: number;
  rating: number;
  status: string;
  know_count: number;
  next_review_at: string | null;
  interval_days: number;
  fsrs_state: number;
}

/** 某一档评分对应的排程预览 */
export interface RatingPreview {
  rating: number;
  label: string;
  interval_days: number;
  due: string;
  fsrs_state: number;
}

export interface QuizQuestion {
  word_id: number;
  word: string;
  quiz_type: "choice" | "fill" | "listen" | "spell";
  question: string;
  options?: string[];
  correct_answer: string;
  hint?: string;
}

export interface QuizResult {
  score: number;
  total: number;
  wrong_words: Word[];
}

export interface ProgressOverview {
  total_words: number;
  learned_words: number;
  known_words: number;
  today_new: number;
  today_reviewed: number;
  streak_days: number;
}

export interface DailyProgress {
  date: string;
  new_words: number;
  reviewed_words: number;
}

/** 单词书 */
export interface Wordbook {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  word_count: number;
  is_custom?: boolean;
  query_text?: string;
}

/** 生词本/错题本条目 */
export interface StarredWord extends Word {
  starred_type: "star" | "hard";
}
