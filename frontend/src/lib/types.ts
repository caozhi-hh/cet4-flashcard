/** API 类型定义 */

export interface Word {
  id: number;
  word: string;
  phonetic_us: string | null;
  phonetic_uk: string | null;
  definition: string;
  pos: string | null;
  example: string | null;
  example_cn: string | null;
}

export interface FlashCard {
  word: Word;
  status: "new" | "learning" | "known";
  mnemonic?: string | null;
}

export interface StudyResponse {
  word_id: number;
  status: string;
  know_count: number;
  next_review_at: string | null;
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
