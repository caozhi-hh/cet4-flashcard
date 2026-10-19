"use client";

/**
 * 分级英语阅读
 *
 * 静态导出下没有动态路由，所以列表与阅读视图放在**同一页面**，
 * 用查询参数 ?slug= 表示当前文章（客户端读写 window.location，避免 useSearchParams 的 CSR 约束）。
 *
 * 数据链路：/api/reading/articles（列表）→ /api/reading/articles/{slug}（正文分词）
 *          → /api/reading/lookup（点词精确查义）→ /api/reading/attempts（服务端判分）
 *          → /api/reading/progress（完成情况与历史）
 *
 * 单词分段与"重叠消解 + 掌握状态"的行为契约参考 Lute（MIT），见 backend/app/reading/textitems.py。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { readingApi, starredApi } from "@/lib/api";
import type {
  ReadingArticleDetail,
  ReadingArticleSummary,
  ReadingAttemptResult,
  ReadingProgress,
  ReadingToken,
} from "@/lib/types";

type PopupState = {
  loading: boolean;
  word: string;
  found: boolean;
  headword?: string;
  definition?: string;
  phonetic?: string | null;
  status?: string;
  wordId?: number;
  starred?: boolean;
  message?: string;
} | null;

const LEVEL_LABEL: Record<string, string> = { A1: "入门 A1", A2: "基础 A2", B1: "进阶 B1" };
const STATUS_LABEL: Record<string, string> = {
  unknown: "词库未收录",
  new: "未学",
  learning: "学习中",
  known: "已掌握",
};

/** 掌握状态的视觉区分：已掌握变淡、学习中画实线、未收录画虚线（都在现有配色内） */
function statusClass(status: ReadingToken["status"], level: string): string {
  if (level === "known") return "text-cocoa/55";
  if (status === "learning") return "underline decoration-caramel decoration-2 underline-offset-2";
  if (status === "unknown") return "underline decoration-dashed decoration-berry/50 underline-offset-2";
  return "";
}

export default function ReadingPage() {
  const [articles, setArticles] = useState<ReadingArticleSummary[]>([]);
  const [levels, setLevels] = useState<string[]>(["A1", "A2", "B1"]);
  const [level, setLevel] = useState<string>("");
  const [progress, setProgress] = useState<ReadingProgress | null>(null);
  const [detail, setDetail] = useState<ReadingArticleDetail | null>(null);
  const [result, setResult] = useState<ReadingAttemptResult | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [popup, setPopup] = useState<PopupState>(null);
  const [showZh, setShowZh] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingArticle, setLoadingArticle] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef<number>(0);

  const loadList = useCallback(async (lv: string) => {
    try {
      const data = await readingApi.list(lv || undefined);
      setArticles(data.articles);
      setLevels(data.levels);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "文章列表加载失败");
    }
  }, []);

  const loadProgress = useCallback(async () => {
    try {
      setProgress(await readingApi.progress());
    } catch {
      // 进度是辅助信息，失败不阻塞阅读
      setProgress(null);
    }
  }, []);

  const openArticle = useCallback(async (slug: string) => {
    setLoadingArticle(true);
    setError(null);
    setResult(null);
    setAnswers({});
    setPopup(null);
    try {
      const data = await readingApi.detail(slug);
      setDetail(data);
      startedAt.current = Date.now();
      if (typeof window !== "undefined") {
        window.history.replaceState(null, "", `/reading?slug=${encodeURIComponent(slug)}`);
        window.scrollTo({ top: 0 });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "文章加载失败");
      setDetail(null);
    } finally {
      setLoadingArticle(false);
    }
  }, []);

  const backToList = useCallback(() => {
    setDetail(null);
    setResult(null);
    setPopup(null);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", "/reading");
      window.scrollTo({ top: 0 });
    }
  }, []);

  // 首屏：并行拉列表与进度；若 URL 带 ?slug= 直接进阅读视图（可分享/可刷新）
  useEffect(() => {
    const boot = async () => {
      const slug =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("slug")
          : null;
      await Promise.all([loadList(""), loadProgress()]);
      if (slug) await openArticle(slug);
      setLoading(false);
    };
    void boot();
  }, [loadList, loadProgress, openArticle]);

  const changeLevel = async (lv: string) => {
    setLevel(lv);
    setLoading(true);
    await loadList(lv);
    setLoading(false);
  };

  const openWord = async (token: ReadingToken) => {
    const word = token.text;
    // 先给词库里的本地释义（详情里已经带上了），避免点一次等一次
    setPopup({
      loading: !token.term,
      word,
      found: !!token.term,
      headword: token.term?.headword,
      definition: token.term?.definition,
      phonetic: token.term?.phonetic,
      status: token.status,
      wordId: token.term?.word_id,
      starred: token.term?.starred,
      message: token.term ? undefined : "词库暂未收录该词，可先加入生词本稍后复习",
    });
    // 未收录的词再问一次服务端（保持"以服务端为准"），收录的直接用本地数据
    if (!token.term) {
      try {
        const found = await readingApi.lookup(word);
        setPopup((prev) =>
          prev && prev.word === word
            ? {
                loading: false,
                word,
                found: found.found,
                headword: found.headword,
                definition: found.definition,
                phonetic: found.phonetic,
                status: found.status,
                message: found.message,
              }
            : prev
        );
      } catch {
        setPopup((prev) => (prev ? { ...prev, loading: false } : prev));
      }
    }
  };

  const addToWordbook = async () => {
    if (!popup?.wordId) return;
    try {
      await starredApi.add(popup.wordId, "star");
      setPopup((prev) => (prev ? { ...prev, starred: true } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入生词本失败");
    }
  };

  const submit = async () => {
    if (!detail || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const seconds = startedAt.current ? Math.round((Date.now() - startedAt.current) / 1000) : 0;
      const payload = detail.article.questions
        .filter((q) => answers[q.id] !== undefined)
        .map((q) => ({ question_id: q.id, choice: answers[q.id] }));
      const res = await readingApi.submit(detail.article.slug, payload, seconds);
      setResult(res);
      setPopup(null);
      await loadProgress();
      if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  const completed = new Set(progress?.completed_slugs ?? []);
  const detailOf = (qid: string) => result?.details.find((d) => d.question_id === qid);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-cocoa-soft">
        <span className="text-4xl inline-block animate-float">📖</span>
        <p className="mt-3 font-medium text-sm">正在加载文章…</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="text-center pt-2 pb-1">
        <h1 className="text-2xl font-bold text-cocoa tracking-tight">
          {detail ? "分级阅读" : "分级阅读"}
        </h1>
        <p className="text-cocoa-soft mt-1.5 text-sm">
          {detail ? "点任意单词查看释义" : "按难度选一篇，读完做题"}
        </p>
      </div>

      {error && (
        <div role="alert" className="bg-berry/10 border-2 border-berry/30 rounded-xl px-3 py-2 text-sm text-cocoa">
          ⚠️ {error}
        </div>
      )}

      {/* === 阅读视图 === */}
      {detail ? (
        <>
          <div className="flex items-center justify-between gap-2">
            <button
              onClick={backToList}
              className="text-sm text-cocoa-soft hover:text-cocoa transition-colors"
            >
              ← 返回列表
            </button>
            <button
              onClick={() => setShowZh((v) => !v)}
              className={`text-xs px-3 py-1.5 rounded-lg border-2 transition-colors ${
                showZh ? "border-cocoa bg-cocoa text-milk" : "border-honey text-cocoa-soft"
              }`}
            >
              {showZh ? "隐藏译文" : "显示译文"}
            </button>
          </div>

          <div className="bg-milk rounded-2xl border border-honey p-5 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs px-2 py-0.5 rounded-md bg-cocoa text-milk font-medium">
                {LEVEL_LABEL[detail.article.level] ?? detail.article.level}
              </span>
              <span className="text-xs text-cocoa-soft">{detail.article.topic}</span>
            </div>
            <h2 className="text-xl font-bold text-cocoa">{detail.article.title}</h2>
            <p className="text-sm text-cocoa-soft">{detail.article.title_zh}</p>
            <p className="text-xs text-cocoa-soft">
              约 {detail.article.minutes} 分钟 · {detail.article.word_count} 词 ·{" "}
              {detail.article.question_count} 道理解题
            </p>
          </div>

          <div className="bg-milk rounded-2xl border border-honey p-5 space-y-4 leading-8 text-[15px] text-cocoa">
            {detail.tokens.map((para, pi) => (
              <p key={pi} className="whitespace-pre-wrap">
                {para.map((t) =>
                  t.is_word ? (
                    <span
                      key={t.span_id}
                      role="button"
                      tabIndex={0}
                      onClick={() => void openWord(t)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          void openWord(t);
                        }
                      }}
                      title={t.term?.definition || "词库未收录"}
                      className={`cursor-pointer rounded transition-colors hover:bg-honey/50 ${statusClass(
                        t.status,
                        t.status
                      )}`}
                    >
                      {t.text}
                    </span>
                  ) : (
                    <span key={t.span_id}>{t.text}</span>
                  )
                )}
                {showZh && detail.article.paragraphs[pi]?.zh && (
                  <span className="block mt-1.5 text-sm leading-6 text-cocoa-soft border-l-2 border-honey pl-3">
                    {detail.article.paragraphs[pi].zh}
                  </span>
                )}
              </p>
            ))}
            <p className="text-[11px] text-cocoa-soft border-t border-honey pt-2">
              {detail.article.source} · 下划线：学习中（实线）/ 未收录（虚线）；已掌握的词显示为浅色
            </p>
          </div>

          {/* 理解题 */}
          <div className="bg-milk rounded-2xl border border-honey p-5 space-y-4">
            <h3 className="font-bold text-cocoa text-sm">阅读理解</h3>
            {detail.article.questions.map((q, qi) => {
              const d = detailOf(q.id);
              return (
                <div key={q.id} className="space-y-2">
                  <p className="text-sm text-cocoa font-medium">
                    {qi + 1}. {q.prompt}
                  </p>
                  <div className="space-y-1.5">
                    {q.options.map((opt, oi) => {
                      const chosen = answers[q.id] === oi;
                      const isCorrect = d && d.correct_choice === oi;
                      const isWrongChoice = d && d.chosen === oi && !d.correct;
                      return (
                        <button
                          key={oi}
                          type="button"
                          disabled={!!result}
                          onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: oi }))}
                          className={`w-full text-left text-sm px-3 py-2 rounded-xl border-2 transition-all ${
                            isCorrect
                              ? "border-honey bg-milk-warm text-cocoa"
                              : isWrongChoice
                                ? "border-berry/50 bg-berry/10 text-cocoa"
                                : chosen
                                  ? "border-cocoa bg-cream text-cocoa"
                                  : "border-honey text-cocoa-soft hover:border-cocoa-soft"
                          }`}
                        >
                          {String.fromCharCode(65 + oi)}. {opt}
                          {isCorrect && " ✓"}
                          {isWrongChoice && " ✗"}
                        </button>
                      );
                    })}
                  </div>
                  {d && (
                    <p className="text-xs text-cocoa-soft bg-cream rounded-lg px-3 py-2">
                      {d.correct ? "答对了。" : `正确答案是 ${String.fromCharCode(65 + d.correct_choice)}。`}
                      {d.explanation}
                    </p>
                  )}
                </div>
              );
            })}

            {result ? (
              <div className="space-y-3 border-t border-honey pt-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-cocoa">
                    得分 {result.score} / {result.total}
                  </span>
                  <span
                    className={`text-xs px-2 py-1 rounded-lg ${
                      result.passed ? "bg-cocoa text-milk" : "bg-berry/15 text-cocoa"
                    }`}
                  >
                    {result.passed ? "已完成" : "再读一遍会更好"}
                  </span>
                </div>
                <p className="text-xs text-cocoa-soft">
                  作答 {result.answered} / {result.total} 题 · 用时 {result.duration_seconds} 秒 ·
                  成绩已保存到你的阅读记录
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => void openArticle(result.slug)}
                    className="flex-1 py-2.5 rounded-xl border-2 border-honey text-cocoa text-sm font-medium hover:border-cocoa-soft"
                  >
                    再做一次
                  </button>
                  <button
                    onClick={backToList}
                    className="flex-1 py-2.5 rounded-xl bg-cocoa text-milk text-sm font-bold hover:bg-caramel"
                  >
                    换一篇
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => void submit()}
                disabled={submitting || Object.keys(answers).length === 0}
                className="w-full py-3.5 rounded-xl bg-cocoa text-milk font-bold transition-all hover:bg-caramel active:scale-95 disabled:opacity-50"
              >
                {submitting
                  ? "提交中…"
                  : `提交答案（${Object.keys(answers).length}/${detail.article.questions.length}）`}
              </button>
            )}
          </div>
        </>
      ) : loadingArticle ? (
        <div className="text-center py-16 text-cocoa-soft">正在打开文章…</div>
      ) : (
        <>
          {/* === 进度概览 === */}
          {progress && (
            <div className="bg-milk rounded-2xl border border-honey p-4 space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-cocoa font-medium">阅读进度</span>
                <span className="text-cocoa-soft tabular-nums">
                  已读 {progress.completed_articles} / {progress.total_articles} 篇
                </span>
              </div>
              <div className="flex gap-2">
                {progress.by_level.map((lv) => (
                  <div key={lv.level} className="flex-1 text-center bg-cream rounded-xl border border-honey py-2">
                    <div className="text-sm font-bold text-cocoa tabular-nums">
                      {lv.completed}/{lv.total}
                    </div>
                    <div className="text-[11px] text-cocoa-soft mt-0.5">{lv.level}</div>
                  </div>
                ))}
              </div>
              {progress.history.length > 0 && (
                <div className="space-y-1 border-t border-honey pt-2">
                  <p className="text-[11px] text-cocoa-soft">最近记录</p>
                  {progress.history.slice(0, 3).map((h, i) => (
                    <button
                      key={`${h.slug}-${i}`}
                      onClick={() => void openArticle(h.slug)}
                      className="w-full flex items-center justify-between text-xs text-cocoa-soft hover:text-cocoa transition-colors"
                    >
                      <span className="truncate">{h.title}</span>
                      <span className="tabular-nums shrink-0 ml-2">
                        {h.score}/{h.total} · {h.duration_seconds}s
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* === 难度筛选 + 列表 === */}
          <div className="flex gap-2">
            {[{ v: "", label: "全部" }, ...levels.map((l) => ({ v: l, label: LEVEL_LABEL[l] ?? l }))].map(
              (opt) => (
                <button
                  key={opt.v || "all"}
                  onClick={() => void changeLevel(opt.v)}
                  aria-pressed={level === opt.v}
                  className={`flex-1 py-2 rounded-xl text-xs font-medium border-2 transition-colors ${
                    level === opt.v ? "border-cocoa bg-cocoa text-milk" : "border-honey text-cocoa-soft"
                  }`}
                >
                  {opt.label}
                </button>
              )
            )}
          </div>

          {articles.length === 0 ? (
            <p className="text-center text-sm text-cocoa-soft py-10">该难度下还没有文章</p>
          ) : (
            <div className="space-y-3">
              {articles.map((a) => (
                <button
                  key={a.slug}
                  onClick={() => void openArticle(a.slug)}
                  className="w-full text-left bg-milk rounded-2xl border border-honey p-4 hover:border-cocoa-soft transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] px-2 py-0.5 rounded-md bg-cream-deep text-cocoa font-medium">
                          {a.level}
                        </span>
                        <span className="text-[11px] text-cocoa-soft">{a.topic}</span>
                        {completed.has(a.slug) && (
                          <span className="text-[11px] px-2 py-0.5 rounded-md bg-cocoa text-milk">
                            已完成
                          </span>
                        )}
                      </div>
                      <h3 className="font-bold text-cocoa mt-1.5 truncate">{a.title}</h3>
                      <p className="text-xs text-cocoa-soft truncate">{a.title_zh}</p>
                      <p className="text-[11px] text-cocoa-soft mt-1">
                        约 {a.minutes} 分钟 · {a.word_count} 词 · {a.question_count} 题
                      </p>
                    </div>
                    <span className="text-cocoa-soft shrink-0">›</span>
                  </div>
                </button>
              ))}
            </div>
          )}

          <div className="text-center">
            <Link href="/study" className="text-sm text-cocoa-soft hover:text-cocoa">
              去背单词 →
            </Link>
          </div>
        </>
      )}

      {/* === 点词弹窗（底部卡片，移动端友好）=== */}
      {popup && (
        <div className="fixed inset-x-0 bottom-0 z-40 px-4 pb-20 md:pb-6">
          <div className="max-w-2xl mx-auto bg-milk border-2 border-honey rounded-2xl shadow-lg p-4 space-y-2 animate-bounce-in">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="text-lg font-bold text-cocoa">{popup.headword ?? popup.word}</span>
                  {popup.phonetic && (
                    <span className="text-xs text-cocoa-soft">{popup.phonetic}</span>
                  )}
                  {popup.status && (
                    <span className="text-[11px] px-2 py-0.5 rounded-md bg-cream-deep text-cocoa-soft">
                      {STATUS_LABEL[popup.status] ?? popup.status}
                    </span>
                  )}
                </div>
                <p className="text-sm text-cocoa mt-1">
                  {popup.loading
                    ? "查询中…"
                    : popup.found
                      ? popup.definition
                      : popup.message ?? "词库暂未收录该词"}
                </p>
              </div>
              <button
                onClick={() => setPopup(null)}
                aria-label="关闭"
                className="text-cocoa-soft hover:text-cocoa text-lg leading-none shrink-0"
              >
                ✕
              </button>
            </div>
            <div className="flex gap-2 pt-1">
              {popup.wordId ? (
                <button
                  onClick={() => void addToWordbook()}
                  disabled={popup.starred}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border-2 transition-colors ${
                    popup.starred ? "border-honey text-cocoa-soft" : "border-cocoa text-cocoa"
                  }`}
                >
                  {popup.starred ? "★ 已在生词本" : "☆ 加入生词本"}
                </button>
              ) : (
                <span className="text-xs text-cocoa-soft">该词不在词库中，无法加入生词本</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}