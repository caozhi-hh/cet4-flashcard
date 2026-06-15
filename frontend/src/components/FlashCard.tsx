"use client";

import { useState } from "react";
import type { FlashCard as FlashCardType } from "@/lib/types";
import { aiApi, starredApi } from "@/lib/api";
import { speak } from "@/lib/tts";

interface Props {
  card: FlashCardType;
  onKnown: () => void;
  onUnknown: () => void;
}

export default function FlashCard({ card, onKnown, onUnknown }: Props) {
  const [flipped, setFlipped] = useState(false);
  const [mnemonic, setMnemonic] = useState<string | null>(null);
  const [loadingAI, setLoadingAI] = useState(false);
  const [starred, setStarred] = useState(false);
  const { word } = card;

  const handleMnemonic = async () => {
    if (mnemonic) return;
    setLoadingAI(true);
    try {
      const res = await aiApi.getMnemonic(word.id);
      setMnemonic(res.mnemonic);
    } catch {
      setMnemonic("生成失败，请稍后重试");
    } finally {
      setLoadingAI(false);
    }
  };

  const toggleStar = (e: React.MouseEvent) => {
    e.stopPropagation();
    const next = !starred;
    setStarred(next);
    (next ? starredApi.add(word.id, "star") : starredApi.remove(word.id, "star")).catch(() =>
      setStarred(!next)
    );
  };

  return (
    <div className="w-full max-w-md mx-auto animate-slide-up">
      <p className="text-center text-xs text-cocoa-soft mb-3 tracking-wide">
        {card.status === "new" ? "NEW · 新词" : card.status === "learning" ? "LEARNING · 学习中" : "MASTERED · 已掌握"}
      </p>

      {/* 卡片主体 */}
      <div
        onClick={() => setFlipped(!flipped)}
        className="relative cursor-pointer"
        style={{ perspective: "1200px" }}
      >
        <div
          className="relative w-full min-h-[280px] transition-transform duration-500"
          style={{
            transformStyle: "preserve-3d",
            transform: flipped ? "rotateY(180deg)" : "rotateY(0)",
          }}
        >
          {/* 正面 */}
          <div
            className="absolute inset-0 rounded-2xl shadow-md p-8 flex flex-col items-center justify-center border border-honey bg-milk"
            style={{ backfaceVisibility: "hidden" }}
          >
            <button
              onClick={toggleStar}
              className="absolute top-4 right-5 text-xl text-cocoa-soft hover:text-caramel transition-colors active:scale-90"
              title={starred ? "取消收藏" : "加入生词本"}
              aria-label="收藏"
            >
              {starred ? "★" : "☆"}
            </button>

            <p className="text-4xl font-bold text-cocoa mb-2 tracking-tight">
              {word.word}
            </p>
            <button
              onClick={(e) => { e.stopPropagation(); speak(word.word); }}
              className="text-cocoa-soft hover:text-caramel transition-colors active:scale-90 mb-2"
              title="朗读"
              aria-label="朗读单词"
            >
              🔊
            </button>
            <p className="text-cocoa-soft text-sm">{word.phonetic_us || word.phonetic_uk}</p>
            {word.pos && (
              <span className="mt-3 px-2.5 py-0.5 rounded-md bg-cream-deep text-cocoa-soft text-xs">
                {word.pos}
              </span>
            )}
            <p className="text-xs text-cocoa-soft/60 mt-6">点击翻转查看释义</p>
          </div>

          {/* 反面 */}
          <div
            className="absolute inset-0 rounded-2xl shadow-md p-8 flex flex-col items-center justify-center border border-honey bg-milk"
            style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <p className="text-2xl font-bold text-cocoa mb-2">{word.word}</p>
            <p className="text-base text-cocoa text-center mb-3 leading-relaxed">{word.definition}</p>
            {word.example && (
              <div className="text-sm text-cocoa-soft space-y-1.5 mt-2 px-2 max-w-full">
                <p className="italic leading-relaxed flex items-start gap-1.5 justify-center">
                  <span className="flex-1">“{word.example}”</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); speak(word.example!, 0.85); }}
                    className="text-cocoa-soft hover:text-caramel transition-colors active:scale-90 shrink-0"
                    title="朗读例句"
                  >
                    🔊
                  </button>
                </p>
                {word.example_cn && <p className="text-cocoa-soft/70">{word.example_cn}</p>}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 记忆口诀 */}
      <div className="mt-4 text-center">
        <button
          onClick={handleMnemonic}
          disabled={loadingAI}
          className="text-sm font-medium text-caramel hover:text-cocoa disabled:text-cocoa-soft/50 transition-colors active:scale-95"
        >
          {loadingAI ? "AI 思考中..." : mnemonic ? "查看记忆口诀" : "💡 生成记忆口诀"}
        </button>
        {mnemonic && (
          <div className="mt-2 p-4 bg-cream-deep rounded-xl text-sm text-cocoa text-left whitespace-pre-line border border-honey">
            {mnemonic}
          </div>
        )}
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-3 mt-6">
        <button
          onClick={onUnknown}
          className="flex-1 py-3.5 rounded-xl bg-cream-deep text-berry-deep font-semibold hover:bg-honey transition-all active:scale-95"
        >
          不认识
        </button>
        <button
          onClick={onKnown}
          className="flex-1 py-3.5 rounded-xl bg-cocoa text-milk font-semibold hover:bg-caramel transition-all active:scale-95"
        >
          认识
        </button>
      </div>
    </div>
  );
}
