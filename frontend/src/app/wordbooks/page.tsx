"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { wordbookApi } from "@/lib/api";
import type { Wordbook } from "@/lib/types";
import { getSelectedWordbook, setSelectedWordbook, onWordbookChange } from "@/lib/wordbook";

const EXAMPLES = ["和食物相关的词", "旅行出行", "情绪感受", "科技互联网", "校园生活", "高频动词"];

export default function WordbooksPage() {
  const [wordbooks, setWordbooks] = useState<Wordbook[]>([]);
  const [selected, setSelected] = useState<string>(getSelectedWordbook());
  const [loading, setLoading] = useState(true);

  // AI 生成状态
  const [query, setQuery] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  useEffect(() => {
    loadWordbooks();
    const unsub = onWordbookChange(() => setSelected(getSelectedWordbook()));
    return unsub;
  }, []);

  const loadWordbooks = () => {
    setLoading(true);
    wordbookApi.list()
      .then((data) => {
        setWordbooks(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  const handleSelect = (id: string) => {
    setSelectedWordbook(id);
    setSelected(id);
  };

  const handleGenerate = async () => {
    if (!query.trim() || generating) return;
    setGenerating(true);
    setGenError("");
    try {
      const wb = await wordbookApi.aiGenerate(query.trim());
      // 切换到新书 + 标记成就
      handleSelect(wb.id);
      localStorage.setItem("cet4_ai_created", "1");
      setQuery("");
      await loadWordbooks();
    } catch (e) {
      setGenError("生成失败，请重试 🥺");
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("删除这本单词书吗？")) return;
    try {
      await wordbookApi.remove(id);
      if (selected === id) handleSelect("core1000");
      loadWordbooks();
    } catch {}
  };

  const presetBooks = wordbooks.filter((w) => !w.is_custom);
  const customBooks = wordbooks.filter((w) => w.is_custom);

  if (loading) {
    return (
      <div className="text-center py-20 text-cocoa-soft">
        <span className="text-5xl inline-block animate-float">📚</span>
        <p className="mt-4 font-medium">加载单词书中...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center pt-2 animate-bounce-in">
        <h1 className="text-2xl font-extrabold text-cocoa">📚 选择你的单词书</h1>
        <p className="text-cocoa-soft mt-2 font-medium">选一本，或让 AI 帮你定制 🌸</p>
      </div>

      {/* ===== AI 智能生成区 ===== */}
      <div className="bg-gradient-to-br from-milk-warm to-honey/20 rounded-3xl p-5 border-2 border-honey/50 shadow-sm shadow-caramel/10 animate-bounce-in">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-2xl">🤖</span>
          <h2 className="font-bold text-cocoa">AI 智能生成单词书</h2>
        </div>
        <p className="text-xs text-cocoa-soft mb-3 leading-relaxed">
          告诉 AI 你想背什么词，它会从词库中智能筛选组成单词书
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
            placeholder="如：和食物相关的词、旅行出行、情绪感受..."
            disabled={generating}
            className="flex-1 px-4 py-3 rounded-2xl border-2 border-honey/50 bg-cream text-cocoa text-sm focus:outline-none focus:border-milktea focus:ring-2 focus:ring-milktea/20 placeholder:text-cocoa-soft/50 transition-all disabled:opacity-60"
          />
          <button
            onClick={handleGenerate}
            disabled={generating || !query.trim()}
            className="px-5 py-3 rounded-2xl bg-gradient-to-r from-milktea to-caramel text-white font-bold text-sm shadow-lg shadow-caramel/30 hover:shadow-xl transition-all active:scale-95 disabled:opacity-50 disabled:active:scale-100 whitespace-nowrap"
          >
            {generating ? "思考中" : "✨ 生成"}
          </button>
        </div>

        {/* 思考动画 */}
        {generating && (
          <div className="flex items-center justify-center gap-2 mt-3 py-2">
            <span className="text-xl animate-bounce" style={{ animationDelay: "0ms" }}>🤔</span>
            <span className="text-xl animate-bounce" style={{ animationDelay: "150ms" }}>📚</span>
            <span className="text-xl animate-bounce" style={{ animationDelay: "300ms" }}>🔍</span>
            <span className="text-sm text-cocoa-soft font-medium ml-1">AI 正在分析你的需求并筛选单词...</span>
          </div>
        )}

        {genError && <p className="text-sm text-berry-deep mt-2">{genError}</p>}

        {/* 示例标签 */}
        {!generating && (
          <div className="flex flex-wrap gap-2 mt-3">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setQuery(ex)}
                className="text-xs px-3 py-1 rounded-full bg-cream border border-honey/50 text-cocoa-soft hover:border-milktea hover:text-cocoa hover:bg-honey/20 transition-all active:scale-95"
              >
                {ex}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ===== 自定义单词书（AI 生成） ===== */}
      {customBooks.length > 0 && (
        <div className="space-y-3">
          <h2 className="font-bold text-cocoa flex items-center gap-1.5 px-1">
            <span>✨</span> 我的自定义词书
            <span className="text-xs font-normal text-cocoa-soft">({customBooks.length})</span>
          </h2>
          {customBooks.map((wb, i) => (
            <WordbookCard
              key={wb.id}
              wb={wb}
              selected={selected === wb.id}
              delay={i * 50}
              onSelect={handleSelect}
              onDelete={wb.is_custom ? (e) => handleDelete(e, wb.id) : undefined}
            />
          ))}
        </div>
      )}

      {/* ===== 预定义单词书 ===== */}
      <div className="space-y-3">
        <h2 className="font-bold text-cocoa flex items-center gap-1.5 px-1">
          <span>📖</span> 推荐单词书
        </h2>
        {presetBooks.map((wb, i) => (
          <WordbookCard
            key={wb.id}
            wb={wb}
            selected={selected === wb.id}
            delay={i * 50}
            onSelect={handleSelect}
          />
        ))}
      </div>

      {/* 开始学习 */}
      <Link
        href="/study"
        className="block w-full py-4 mt-2 bg-gradient-to-r from-milktea to-caramel text-white text-center rounded-3xl font-bold text-lg shadow-lg shadow-caramel/30 hover:shadow-xl transition-all active:scale-95"
      >
        🚀 用这本书开始学习
      </Link>
    </div>
  );
}

/** 单词书卡片 */
function WordbookCard({
  wb,
  selected,
  delay,
  onSelect,
  onDelete,
}: {
  wb: Wordbook;
  selected: boolean;
  delay: number;
  onSelect: (id: string) => void;
  onDelete?: (e: React.MouseEvent) => void;
}) {
  return (
    <button
      onClick={() => onSelect(wb.id)}
      className={`group w-full text-left p-4 rounded-3xl border-2 transition-all duration-300 animate-bounce-in active:scale-[0.98] ${
        selected
          ? "bg-gradient-to-br from-milk-warm to-honey/30 border-milktea shadow-lg shadow-caramel/20 scale-[1.02]"
          : "bg-milk-warm border-honey/50 hover:border-milktea hover:-translate-y-0.5 hover:shadow-md"
      }`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start gap-3">
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center text-3xl shrink-0 transition-transform group-hover:scale-110"
          style={{ backgroundColor: `${wb.color}30` }}
        >
          {wb.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-bold text-cocoa text-base truncate flex items-center gap-1">
              {wb.name}
              {wb.is_custom && <span className="text-xs">✨</span>}
            </h3>
            <div className="flex items-center gap-1.5 shrink-0">
              {selected && (
                <span className="text-xs font-bold text-white bg-gradient-to-r from-milktea to-caramel px-2.5 py-0.5 rounded-full">
                  ✓ 已选
                </span>
              )}
              {onDelete && (
                <span
                  onClick={onDelete}
                  className="text-xs w-6 h-6 flex items-center justify-center rounded-full text-cocoa-soft hover:bg-berry/20 hover:text-berry-deep transition-colors"
                  role="button"
                >
                  ✕
                </span>
              )}
            </div>
          </div>
          <p className="text-xs text-cocoa-soft mt-1 leading-relaxed line-clamp-2">{wb.description}</p>
          <span
            className="inline-block text-xs font-bold px-2 py-0.5 rounded-full mt-2"
            style={{ backgroundColor: `${wb.color}25`, color: wb.color }}
          >
            📖 {wb.word_count} 词
          </span>
        </div>
      </div>
    </button>
  );
}
