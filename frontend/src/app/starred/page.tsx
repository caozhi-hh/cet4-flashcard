"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { starredApi } from "@/lib/api";
import type { StarredWord } from "@/lib/types";
import { speak } from "@/lib/tts";
import { useToast } from "@/components/ui/toast";
import { parseTags, tagLabel } from "@/lib/tags";
import WordDetailSheet from "@/components/WordDetailSheet";

type Tab = "star" | "hard";

export default function StarredPage() {
  const [tab, setTab] = useState<Tab>("star");
  const [words, setWords] = useState<StarredWord[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<StarredWord | null>(null);
  // 每个标签各自记数量：避免加载中显示上一个标签的数字（标签在 "(N)" 与 "()" 之间跳）
  const [counts, setCounts] = useState<Record<Tab, number | null>>({ star: null, hard: null });
  // 请求序号：慢响应回来时若已被更新的请求取代，直接丢弃，避免旧列表覆盖新列表
  const reqSeq = useRef(0);
  const { toast } = useToast();

  const load = useCallback(
    async (which: Tab) => {
      const seq = ++reqSeq.current;
      setLoading(true);
      try {
        const data = await starredApi.list(which);
        if (seq !== reqSeq.current) return;
        setWords(data.words);
        setCounts((prev) => ({ ...prev, [which]: data.total ?? data.words.length }));
      } catch (e) {
        if (seq !== reqSeq.current) return;
        toast({
          variant: "error",
          title: "加载失败",
          description: e instanceof Error ? e.message : "请确认后端服务在运行",
        });
      } finally {
        if (seq === reqSeq.current) setLoading(false);
      }
    },
    [toast]
  );

  useEffect(() => {
    load(tab);
  }, [tab, load]);

  const handleRemove = async (id: number) => {
    const index = words.findIndex((w) => w.id === id);
    const removed = words[index];
    if (!removed) return;

    // 乐观更新：先从列表移除，失败再插回原位（原先失败是静默吞掉，刷新后词会"复活"）
    setWords((prev) => prev.filter((w) => w.id !== id));
    setDetail(null);

    try {
      await starredApi.remove(id, tab);
      setCounts((prev) => ({ ...prev, [tab]: Math.max((prev[tab] ?? 1) - 1, 0) }));
    } catch (e) {
      setWords((prev) => {
        if (prev.some((w) => w.id === id)) return prev;
        const next = [...prev];
        next.splice(Math.min(index, next.length), 0, removed);
        return next;
      });
      toast({
        variant: "error",
        title: "移除失败",
        description: e instanceof Error ? e.message : "词还在，请重试",
      });
    }
  };

  const tabCountLabel = (which: Tab) => (counts[which] === null ? "" : ` (${counts[which]})`);

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
          ⭐ 生词本{tabCountLabel("star")}
        </button>
        <button
          onClick={() => setTab("hard")}
          className={`flex-1 py-2.5 rounded-xl font-bold text-sm transition-all ${
            tab === "hard"
              ? "bg-gradient-to-r from-berry to-berry-deep text-white shadow-md"
              : "text-cocoa-soft hover:text-cocoa"
          }`}
        >
          🍓 错题本{tabCountLabel("hard")}
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
        <>
          <p className="text-xs text-cocoa-soft text-center">点任意一条查看完整释义与例句</p>
          <div className="space-y-2.5">
            {words.map((w, i) => {
              const tags = parseTags(w.tags);
              return (
                <div
                  key={w.id}
                  className="bg-milk-warm rounded-2xl p-4 border-2 border-honey/50 shadow-sm shadow-caramel/10 flex items-start gap-3 animate-bounce-in"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  {/* 点内容区打开详情抽屉（原先释义被 truncate 截断且无处展开） */}
                  <button
                    onClick={() => setDetail(w)}
                    className="flex-1 min-w-0 text-left active:scale-[0.995] transition-transform"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-cocoa text-lg break-words">{w.word}</span>
                      {w.phonetic_us && <span className="text-xs text-cocoa-soft">{w.phonetic_us}</span>}
                      {tags.slice(0, 3).map((t) => (
                        <span key={t} className="px-1.5 py-0.5 rounded bg-cream-deep text-cocoa-soft text-[10px]">
                          {tagLabel(t)}
                        </span>
                      ))}
                    </div>
                    {/* 列表只显示两行摘要，全文在抽屉里 */}
                    <p className="text-sm text-cocoa-soft mt-1 line-clamp-2">{w.definition}</p>
                    {w.example && (
                      <p className="text-xs text-cocoa-soft/80 mt-1 italic line-clamp-2">“{w.example}”</p>
                    )}
                  </button>

                  <div className="shrink-0 flex flex-col items-center gap-1">
                    <button
                      onClick={() => speak(w.word)}
                      className="w-8 h-8 rounded-full text-milktea hover:text-caramel hover:bg-cream-deep transition-colors flex items-center justify-center active:scale-90"
                      title="朗读"
                      aria-label="朗读单词"
                    >
                      🔊
                    </button>
                    <button
                      onClick={() => handleRemove(w.id)}
                      className="w-8 h-8 rounded-full text-cocoa-soft hover:bg-berry/20 hover:text-berry-deep transition-colors flex items-center justify-center"
                      title="移除"
                      aria-label="移除"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      <WordDetailSheet
        word={detail}
        open={detail !== null}
        onOpenChange={(open) => {
          if (!open) setDetail(null);
        }}
        onRemove={detail ? () => handleRemove(detail.id) : undefined}
        removeLabel={tab === "star" ? "从生词本移除" : "从错题本移除"}
      />
    </div>
  );
}
