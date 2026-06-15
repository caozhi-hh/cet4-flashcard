"use client";

import { useEffect, useState } from "react";
import { starredApi } from "@/lib/api";
import type { StarredWord } from "@/lib/types";
import { speak } from "@/lib/tts";

type Tab = "star" | "hard";

export default function StarredPage() {
  const [tab, setTab] = useState<Tab>("star");
  const [words, setWords] = useState<StarredWord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    starredApi.list(tab)
      .then((data) => {
        setWords(data.words);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [tab]);

  const handleRemove = async (id: number) => {
    setWords((prev) => prev.filter((w) => w.id !== id));
    try {
      await starredApi.remove(id, tab);
    } catch {}
  };

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-extrabold text-cocoa text-center pt-2 animate-bounce-in">
        📝 生词本 & 错题本
      </h1>

      {/* 切换标签 */}
      <div className="flex gap-2 bg-milk-warm rounded-2xl p-1.5 border-2 border-honey/50">
        <button
          onClick={() => setTab("star")}
          className={`flex-1 py-2.5 rounded-xl font-bold text-sm transition-all ${
            tab === "star"
              ? "bg-gradient-to-r from-milktea to-caramel text-white shadow-md"
              : "text-cocoa-soft hover:text-cocoa"
          }`}
        >
          ⭐ 生词本 ({tab === "star" ? words.length : ""})
        </button>
        <button
          onClick={() => setTab("hard")}
          className={`flex-1 py-2.5 rounded-xl font-bold text-sm transition-all ${
            tab === "hard"
              ? "bg-gradient-to-r from-berry to-berry-deep text-white shadow-md"
              : "text-cocoa-soft hover:text-cocoa"
          }`}
        >
          🍓 错题本 ({tab === "hard" ? words.length : ""})
        </button>
      </div>

      {/* 词列表 */}
      {loading ? (
        <div className="text-center py-16 text-cocoa-soft">
          <span className="text-4xl inline-block animate-float">{tab === "star" ? "⭐" : "🍓"}</span>
          <p className="mt-3 font-medium">加载中...</p>
        </div>
      ) : words.length === 0 ? (
        <div className="text-center py-16 space-y-3 animate-bounce-in">
          <div className="text-6xl inline-block animate-float">{tab === "star" ? "🌱" : "🎯"}</div>
          <h2 className="text-xl font-bold text-cocoa">
            {tab === "star" ? "还没有收藏的单词" : "还没有错题"}
          </h2>
          <p className="text-cocoa-soft font-medium">
            {tab === "star" ? "学习时点 ☆ 收藏难记的词" : "测验错的词会自动收集到这里"}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {words.map((w, i) => (
            <div
              key={w.id}
              className="bg-milk-warm rounded-2xl p-4 border-2 border-honey/50 shadow-sm shadow-caramel/10 flex items-center gap-3 animate-bounce-in"
              style={{ animationDelay: `${i * 30}ms` }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-cocoa text-lg">{w.word}</span>
                  <button
                    onClick={() => speak(w.word)}
                    className="text-milktea hover:text-caramel hover:scale-125 transition-all active:scale-90"
                    title="朗读"
                  >
                    🔊
                  </button>
                  {w.phonetic_us && <span className="text-xs text-cocoa-soft">{w.phonetic_us}</span>}
                </div>
                <p className="text-sm text-cocoa-soft mt-0.5 truncate">{w.definition}</p>
                {w.example && <p className="text-xs text-cocoa-soft/70 mt-1 italic truncate">“{w.example}”</p>}
              </div>
              <button
                onClick={() => handleRemove(w.id)}
                className="shrink-0 w-8 h-8 rounded-full text-cocoa-soft hover:bg-berry/20 hover:text-berry-deep transition-colors flex items-center justify-center"
                title="移除"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
