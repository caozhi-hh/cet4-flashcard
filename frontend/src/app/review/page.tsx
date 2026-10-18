"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import FlashCard from "@/components/FlashCard";
import Confetti from "@/components/Confetti";
import { studyApi } from "@/lib/api";
import type { FlashCard as FlashCardType, Rating } from "@/lib/types";

export default function ReviewPage() {
  const [cards, setCards] = useState<FlashCardType[]>([]);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 同学习页：防止连点重复记账
  const submittingRef = useRef(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    studyApi
      .getReview()
      .then((data) => {
        setCards(data.words);
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

  const handleSubmit = async (rating: Rating) => {
    const card = cards[index];
    if (!card || submittingRef.current) return;
    submittingRef.current = true;

    try {
      await studyApi.submit(card.word.id, rating);
    } catch (e) {
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
        <span className="text-5xl inline-block animate-float">🔄</span>
        <p className="mt-4 font-medium">加载复习单词中...</p>
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

  if (done || cards.length === 0) {
    return (
      <>
        {done && <Confetti />}
        <div className="text-center py-20 space-y-4 animate-bounce-in">
          <div className="text-7xl inline-block animate-float">{cards.length === 0 ? "✨" : "🎉"}</div>
          <h2 className="text-2xl font-extrabold text-cocoa">
            {cards.length === 0 ? "没有需要复习的词啦" : "复习完成！"}
          </h2>
          <p className="text-cocoa-soft font-medium">
            {cards.length === 0 ? "所有单词都记住了，太棒了！🌟" : `巩固了 ${cards.length} 个单词 💪`}
          </p>
        </div>
      </>
    );
  }

  const card = cards[index];

  return (
    <div className="space-y-5">
      {error && (
        <div className="bg-berry/10 border-2 border-berry/30 rounded-xl px-3 py-2 text-sm text-cocoa">
          ⚠️ {error}
        </div>
      )}
      <h2 className="text-lg font-bold text-cocoa-soft text-center">
        🔄 待复习：<span className="text-caramel">{cards.length}</span> 个词
      </h2>
      <FlashCard key={card.word.id} card={card} onRate={handleSubmit} />
    </div>
  );
}