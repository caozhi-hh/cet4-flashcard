"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { starredApi, studyApi } from "@/lib/api";
import type { FlashCard as CardType } from "@/lib/types";
import { speak } from "@/lib/tts";
import { useToast } from "@/components/ui/toast";
import {
  computeStats,
  formatDuration,
  isCorrect,
  recordHistory,
  type DictationStats,
  type WordAttempt,
} from "@/lib/dictation";

/** 同一个词最多试几次；试满仍不对就公布答案并记为错 */
const MAX_ATTEMPTS = 3;

export default function DictationPage() {
  const [cards, setCards] = useState<CardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [input, setInput] = useState("");
  const [attempts, setAttempts] = useState(0);
  const [typedChars, setTypedChars] = useState(0);
  const [shake, setShake] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [log, setLog] = useState<WordAttempt[]>([]);
  const [finished, setFinished] = useState<DictationStats | null>(null);
  const [tick, setTick] = useState(0);

  const wordStartRef = useRef<number>(Date.now());
  const inputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    studyApi
      .getDictation(20)
      .then((data) => {
        setCards(data.words);
        setIndex(0);
        setLog([]);
        setFinished(null);
        setAttempts(0);
        setInput("");
        setTypedChars(0);
        setRevealed(false);
        wordStartRef.current = Date.now();
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 实时计时：让"用时/速度"是活的，而不是只在结束时才算（qwerty-learner 的量化反馈思路）
  useEffect(() => {
    if (finished || loading || cards.length === 0) return;
    const timer = setInterval(() => setTick((n) => n + 1), 500);
    return () => clearInterval(timer);
  }, [finished, loading, cards.length]);

  const completedMs = useMemo(() => log.reduce((sum, a) => sum + a.elapsedMs, 0), [log]);
  const completedChars = useMemo(() => log.reduce((sum, a) => sum + a.typedChars, 0), [log]);
  const liveElapsedMs = useMemo(() => {
    if (finished) return completedMs;
    void tick; // 依赖 tick：每次刷新都重算
    return completedMs + (Date.now() - wordStartRef.current);
  }, [finished, completedMs, tick]);
  const liveChars = completedChars + typedChars;
  const liveCorrect = log.filter((a) => a.correct && a.attempts === 1).length;
  const liveMinutes = Math.max(liveElapsedMs / 60000, 1 / 60);

  const card = cards[index];

  /** 收尾当前词：记账 → 回写错题/FSRS → 进入下一词或结算 */
  const commit = useCallback(
    async (current: CardType, attemptsUsed: number, correct: boolean) => {
      const entry: WordAttempt = {
        wordId: current.word.id,
        word: current.word.word,
        attempts: attemptsUsed,
        correct,
        elapsedMs: Date.now() - wordStartRef.current,
        typedChars: typedChars + input.trim().length,
      };
      const nextLog = [...log, entry];
      setLog(nextLog);

      // 只有"试满仍没写对"才回写 FSRS——打错一个字母就降级排程会毁掉复习质量。
      // 改对了（attempts>=2）只进错题本，不动排程。
      if (!correct) {
        try {
          await studyApi.submit(current.word.id, 1); // 1 = 重来
        } catch (e) {
          toast({
            variant: "error",
            title: "排程更新失败",
            description: e instanceof Error ? e.message : undefined,
          });
        }
      }
      if (!correct || attemptsUsed >= 2) {
        try {
          await starredApi.add(current.word.id, "hard");
        } catch {
          // 错题本收录失败不阻塞默写，最后统一提示
        }
      }

      setAttempts(0);
      setInput("");
      setTypedChars(0);
      setRevealed(false);

      if (index + 1 >= cards.length) {
        const stats = computeStats(nextLog);
        setFinished(stats);
        const history = recordHistory({ accuracy: stats.accuracy, cpm: stats.cpm });
        toast({
          variant: "success",
          title: `默写完成：正确率 ${stats.accuracy}%`,
          description:
            history.sessions > 1
              ? `历史最佳 正确率 ${history.bestAccuracy}% · 速度 ${history.bestCpm} 字符/分`
              : `平均 ${stats.avgSecondsPerWord} 秒/词 · ${stats.cpm} 字符/分`,
        });
      } else {
        setIndex(index + 1);
        wordStartRef.current = Date.now();
        inputRef.current?.focus();
      }
    },
    [cards.length, index, input, log, toast, typedChars]
  );

  const handleSubmit = (event?: React.FormEvent) => {
    event?.preventDefault();
    if (!card || revealed) return;

    const typed = input.trim();
    if (!typed) return;

    const used = attempts + 1;
    const ok = isCorrect(typed, card.word.word);
    setTypedChars((c) => c + typed.length);

    if (ok) {
      void commit(card, used, true);
      return;
    }
    if (used >= MAX_ATTEMPTS) {
      setAttempts(used);
      setRevealed(true);
      // 公布答案 1.2 秒后自动记账，让用户有时间看一眼正确拼写
      setTimeout(() => void commit(card, used, false), 1200);
      return;
    }
    setAttempts(used);
    setInput("");
    setShake(true);
    setTimeout(() => setShake(false), 400);
  };

  if (loading) {
    return (
      <div className="text-center py-20 text-cocoa-soft">
        <span className="text-5xl inline-block animate-float">✍️</span>
        <p className="mt-4 font-medium">准备默写词表中...</p>
      </div>
    );
  }

  if (cards.length === 0 && error) {
    return (
      <div className="text-center py-20 space-y-4 animate-bounce-in">
        <div className="text-6xl inline-block">⚠️</div>
        <h2 className="text-xl font-extrabold text-cocoa">加载失败</h2>
        <p className="text-cocoa-soft font-medium">{error}</p>
        <button
          onClick={load}
          className="inline-block mt-2 px-8 py-3 bg-cocoa text-milk rounded-2xl font-bold transition-all hover:bg-caramel active:scale-95"
        >
          🔄 重试
        </button>
      </div>
    );
  }

  if (cards.length === 0) {
    return (
      <div className="text-center py-20 space-y-4 animate-bounce-in">
        <div className="text-7xl inline-block animate-float">🌼</div>
        <h2 className="text-2xl font-extrabold text-cocoa">今天还没有可默写的词</h2>
        <p className="text-cocoa-soft font-medium">先去学几个词，回来默写巩固 ✍️</p>
        <Link
          href="/study"
          className="inline-block mt-4 px-8 py-3 bg-gradient-to-r from-milktea to-caramel text-white rounded-2xl font-bold shadow-lg shadow-caramel/30 active:scale-95"
        >
          📖 去学习
        </Link>
      </div>
    );
  }

  // === 结算页 ===
  if (finished) {
    const isGreat = finished.accuracy >= 80;
    return (
      <div className="space-y-6 animate-bounce-in">
        <div className="text-center space-y-2">
          <div className="text-6xl inline-block animate-float">{isGreat ? "🏆" : "💪"}</div>
          <h1 className="text-2xl font-extrabold text-cocoa">默写完成</h1>
          <p className="text-5xl font-extrabold text-caramel tabular-nums">
            {finished.accuracy}
            <span className="text-2xl text-cocoa-soft">% 正确率</span>
          </p>
          <p className="text-cocoa-soft text-sm">
            一次写对 {finished.firstTryCorrect}/{finished.total} 词
          </p>
        </div>

        {/* 量化反馈：速度 / 用时 / 输入量 */}
        <div className="grid grid-cols-3 gap-3">
          <Stat label="打字速度" value={finished.cpm} unit="字符/分" />
          <Stat label="词速" value={finished.wpm} unit="词/分" />
          <Stat label="平均用时" value={finished.avgSecondsPerWord} unit="秒/词" />
        </div>
        <p className="text-center text-xs text-cocoa-soft">
          总用时 {formatDuration(finished.elapsedMs)} · 输入 {finished.typedChars} 字符
        </p>

        {finished.wrong.length > 0 && (
          <div className="space-y-2">
            <h3 className="font-bold text-cocoa">🍓 没写对的词（已进错题本）</h3>
            <div className="flex flex-wrap gap-1.5">
              {finished.wrong.map((w) => (
                <span key={w} className="px-2.5 py-1 rounded-lg bg-berry/10 border border-berry/30 text-cocoa text-sm">
                  {w}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-2.5">
          <button
            onClick={load}
            className="w-full py-4 bg-gradient-to-r from-milktea to-caramel text-white rounded-2xl font-bold shadow-lg shadow-caramel/30 hover:shadow-xl transition-all active:scale-95"
          >
            🔄 再默写一遍
          </button>
          <div className="grid grid-cols-2 gap-2.5">
            <Link
              href="/quiz"
              className="block py-3.5 bg-milk text-center rounded-xl font-semibold text-cocoa border border-honey hover:border-cocoa-soft transition-colors active:scale-[0.98]"
            >
              去做测验
            </Link>
            <Link
              href="/progress"
              className="block py-3.5 bg-milk text-center rounded-xl font-semibold text-cocoa border border-honey hover:border-cocoa-soft transition-colors active:scale-[0.98]"
            >
              看学习进度
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // === 默写进行中 ===
  return (
    <div className="space-y-5">
      {/* 实时量化条 */}
      <div className="flex items-center justify-between text-xs text-cocoa-soft tabular-nums">
        <span>
          {index + 1}/{cards.length}
        </span>
        <span>⏱ {formatDuration(liveElapsedMs)}</span>
        <span>
          正确率 {log.length === 0 ? "—" : `${Math.round((liveCorrect / log.length) * 100)}%`}
        </span>
        <span>{Math.round(liveChars / liveMinutes)} 字符/分</span>
      </div>

      <div className="bg-milk rounded-2xl border border-honey p-6 space-y-4 min-h-[260px] flex flex-col justify-center">
        {/* 提示：释义 + 音标（音标旁就是发音按钮） */}
        <div className="text-center space-y-2">
          <p className="text-base text-cocoa leading-relaxed" style={{ overflowWrap: "anywhere" }}>
            {card.word.definition}
          </p>
          <div className="flex items-center justify-center gap-2">
            <span className="text-cocoa-soft text-sm">{card.word.phonetic_us || card.word.phonetic_uk || "（无音标）"}</span>
            <button
              onClick={() => speak(card.word.word)}
              className="w-9 h-9 flex items-center justify-center rounded-full text-cocoa-soft hover:text-caramel hover:bg-cream-deep transition-colors active:scale-90"
              title="朗读单词"
              aria-label="朗读单词"
            >
              🔊
            </button>
          </div>
          {card.word.pos && (
            <span className="inline-block px-2.5 py-0.5 rounded-md bg-cream-deep text-cocoa-soft text-xs">
              {card.word.pos}
            </span>
          )}
        </div>

        {/* 公布答案（试满 3 次后） */}
        {revealed && (
          <div className="text-center bg-berry/10 border-2 border-berry/30 rounded-xl py-3">
            <p className="text-xs text-cocoa-soft">正确拼写</p>
            <p className="text-2xl font-extrabold text-cocoa tracking-wide">{card.word.word}</p>
          </div>
        )}

        {/* 输入区 */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            ref={inputRef}
            autoFocus
            type="text"
            value={input}
            disabled={revealed}
            onChange={(e) => setInput(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            placeholder="拼写这个单词…"
            aria-label="默写输入框"
            className={`w-full p-3.5 rounded-xl text-lg text-center tracking-widest font-mono bg-cream text-cocoa border-2 transition-colors focus:outline-none ${
              shake ? "border-berry" : "border-honey focus:border-cocoa"
            }`}
          />
          <button
            type="submit"
            disabled={revealed || !input.trim()}
            className="w-full py-3.5 rounded-xl bg-cocoa text-milk font-bold transition-all hover:bg-caramel active:scale-95 disabled:opacity-50"
          >
            {attempts > 0 ? `再试一次（已试 ${attempts}/${MAX_ATTEMPTS}）` : "确认"}
          </button>
        </form>
        <p className="text-center text-[11px] text-cocoa-soft">
          回车即可提交 · 试满 {MAX_ATTEMPTS} 次会公布答案
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div className="bg-milk rounded-xl border border-honey p-3 text-center">
      <div className="text-xl font-extrabold text-cocoa tabular-nums">{value}</div>
      <div className="text-[11px] text-cocoa-soft">{unit}</div>
      <div className="text-[11px] text-cocoa-soft mt-0.5">{label}</div>
    </div>
  );
}