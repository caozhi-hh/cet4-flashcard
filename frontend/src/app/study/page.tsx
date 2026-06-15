"use client";

import { useEffect, useState } from "react";
import FlashCard from "@/components/FlashCard";
import Confetti from "@/components/Confetti";
import { studyApi } from "@/lib/api";
import type { FlashCard as FlashCardType } from "@/lib/types";
import { getSelectedWordbook } from "@/lib/wordbook";
import { getDailyGoal } from "@/lib/settings";

export default function StudyPage() {
  const [cards, setCards] = useState<FlashCardType[]>([]);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    studyApi.getToday(getSelectedWordbook(), getDailyGoal())
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
        <span className="text-5xl inline-block animate-float">📚</span>
        <p className="mt-4 font-medium">加载今日单词中...</p>
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
          <a
            href="/quiz"
            className="inline-block mt-4 px-8 py-3 bg-gradient-to-r from-milktea to-caramel text-white rounded-2xl font-bold shadow-lg shadow-caramel/30 hover:shadow-xl transition-all active:scale-95"
          >
            ✏️ 去做测验
          </a>
        </div>
      </>
    );
  }

  const card = cards[index];

  return (
    <div className="space-y-5">
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

      <FlashCard
        key={card.word.id}
        card={card}
        onKnown={() => handleSubmit(true)}
        onUnknown={() => handleSubmit(false)}
      />
    </div>
  );
}
