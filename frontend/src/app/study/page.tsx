"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import FlashCard from "@/components/FlashCard";
import Confetti from "@/components/Confetti";
import { studyApi } from "@/lib/api";
import type { FlashCard as FlashCardType, Rating } from "@/lib/types";
import { getSelectedWordbook } from "@/lib/wordbook";
import { getDailyGoal } from "@/lib/settings";

export default function StudyPage() {
  const [cards, setCards] = useState<FlashCardType[]>([]);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 请求进行中守卫：手机上连点两次"认识"会对同一个词重复记账
  // （后端 review_count/know_count 各 +1，连续认识阈值会被提前触发、当日统计错位）
  const submittingRef = useRef(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    studyApi
      .getToday(getSelectedWordbook(), getDailyGoal())
      .then((data) => {
        setCards(data.words);
        setLoading(false);
      })
      .catch((e: Error) => {
        // 不再静默吞掉：区分"真的没有新词"和"服务不可用"
        setError(e.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSubmit = async (rating: Rating) => {
    const card = cards[index];
    if (!card || submittingRef.current) return;
    submittingRef.current = true;

    try {
      await studyApi.submit(card.word.id, rating);
    } catch (e) {
      // 记录没写成功就停在这张卡上，让用户重试，而不是悄悄跳过丢记录
      setError(e instanceof Error ? e.message : "提交失败，请重试");
      submittingRef.current = false;
      return;
    }
    submittingRef.current = false;
    setError(null);

    const next = index + 1;
    if (next >= cards.length) {
      setDone(true);
    } else {
      setIndex(next);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-20 text-cocoa-soft">
        <span className="text-5xl inline-block animate-float">📚</span>
        <p className="mt-4 font-medium">加载今日单词中...</p>
      </div>
    );
  }

  // 加载失败且没有可学内容 → 明确报错 + 重试，不要显示成"今天没有新词"
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

  if (done || cards.length === 0) {
    return (
      <>
        {done && <Confetti />}
        <div className="text-center py-20 space-y-4 animate-bounce-in">
          <div className="text-7xl inline-block animate-float">{cards.length === 0 ? "🌼" : "🎉"}</div>
          <h2 className="text-2xl font-extrabold text-cocoa">
            {cards.length === 0 ? "今天没有新词啦" : "今日学习完成！"}
          </h2>
          <p className="text-cocoa-soft font-medium">
            {cards.length === 0 ? "休息一下，明天再来吧 ☕" : `太棒了！完成了 ${cards.length} 个单词 🌟`}
          </p>
          <div className="flex flex-col items-center gap-3 mt-4">
            <Link
              href="/quiz"
              className="px-8 py-3 bg-gradient-to-r from-milktea to-caramel text-white rounded-2xl font-bold shadow-lg shadow-caramel/30 hover:shadow-xl transition-all active:scale-95"
            >
              ✏️ 去做测验
            </Link>
            {/* 学完立刻默写的闭环（借鉴 qwerty-learner 的"是否默写本章"） */}
            {done && cards.length > 0 && (
              <Link
                href="/dictation"
                className="px-8 py-3 bg-milk text-cocoa rounded-2xl font-bold border border-honey hover:border-cocoa-soft transition-all active:scale-95"
              >
                ✍️ 默写本章（{cards.length} 词）
              </Link>
            )}
          </div>
        </div>
      </>
    );
  }

  const card = cards[index];

  return (
    <div className="space-y-5">
      {/* 提交失败提示（保留当前卡片，可直接重试） */}
      {error && (
        <div className="bg-berry/10 border-2 border-berry/30 rounded-xl px-3 py-2 text-sm text-cocoa">
          ⚠️ {error}
        </div>
      )}

      {/* 进度条 */}
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-honey/30 rounded-full h-3 overflow-hidden">
          <div
            className="bg-gradient-to-r from-milktea to-caramel h-3 rounded-full transition-all duration-500 shimmer-bar"
            style={{ width: `${((index + 1) / cards.length) * 100}%` }}
          />
        </div>
        <span className="text-sm text-cocoa-soft whitespace-nowrap font-bold">
          {index + 1}/{cards.length}
        </span>
      </div>

      <FlashCard key={card.word.id} card={card} onRate={handleSubmit} />
    </div>
  );
}