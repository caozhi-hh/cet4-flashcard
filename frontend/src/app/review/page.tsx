"use client";

import { useEffect, useState } from "react";
import FlashCard from "@/components/FlashCard";
import Confetti from "@/components/Confetti";
import { studyApi } from "@/lib/api";
import type { FlashCard as FlashCardType } from "@/lib/types";

export default function ReviewPage() {
  const [cards, setCards] = useState<FlashCardType[]>([]);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    studyApi.getReview()
      .then((data) => {
        setCards(data.words);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleSubmit = async (known: boolean) => {
    const card = cards[index];
    if (!card) return;

    try {
      await studyApi.submit(card.word.id, known);
    } catch {}

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
      <h2 className="text-lg font-bold text-cocoa-soft text-center">
        🔄 待复习：<span className="text-caramel">{cards.length}</span> 个词
      </h2>
      <FlashCard
        key={card.word.id}
        card={card}
        onKnown={() => handleSubmit(true)}
        onUnknown={() => handleSubmit(false)}
      />
    </div>
  );
}
