"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { progressApi, wordbookApi } from "@/lib/api";
import type { ProgressOverview, Wordbook } from "@/lib/types";
import { getSelectedWordbook, onWordbookChange } from "@/lib/wordbook";
import { getDailyGoal, setDailyGoal, onGoalChange, GOAL_OPTIONS } from "@/lib/settings";

export default function HomePage() {
  const [progress, setProgress] = useState<ProgressOverview | null>(null);
  const [wordbook, setWordbook] = useState<Wordbook | null>(null);
  const [selectedId, setSelectedId] = useState<string>(getSelectedWordbook());
  const [goal, setGoalState] = useState<number>(getDailyGoal());

  useEffect(() => {
    const loadAll = () => {
      const id = getSelectedWordbook();
      setSelectedId(id);
      progressApi.getOverview(id).then(setProgress).catch(() => {});
      wordbookApi.get(id).then(setWordbook).catch(() => {});
    };
    loadAll();
    const unsub = onWordbookChange(loadAll);
    const unsubGoal = onGoalChange(() => setGoalState(getDailyGoal()));
    return () => {
      unsub();
      unsubGoal();
    };
  }, []);

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div className="text-center pt-2 pb-1 animate-fade-in">
        <h1 className="text-2xl font-bold text-cocoa tracking-tight">
          腰子背单词
        </h1>
        <p className="text-cocoa-soft mt-1.5 text-sm">每天 {goal} 个词，轻松过四级</p>
      </div>

      {/* 当前单词书 */}
      {wordbook && (
        <Link
          href="/wordbooks"
          className="block bg-milk rounded-xl p-4 border border-honey hover:border-cocoa-soft transition-colors active:scale-[0.99] animate-fade-in"
        >
          <div className="flex items-center gap-3">
            <span className="text-xl shrink-0">{wordbook.icon}</span>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-cocoa-soft">当前单词书</p>
              <p className="font-semibold text-cocoa truncate">{wordbook.name}</p>
            </div>
            <span className="text-xs text-cocoa-soft shrink-0">{wordbook.word_count} 词</span>
            <span className="text-cocoa-soft text-sm">›</span>
          </div>
        </Link>
      )}

      {/* 今日目标 */}
      {progress && (
        <div className="bg-milk rounded-xl p-4 border border-honey animate-fade-in">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-cocoa">今日目标</span>
            <div className="flex gap-1.5">
              {GOAL_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => setDailyGoal(n)}
                  className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors ${
                    goal === n
                      ? "bg-cocoa text-milk"
                      : "text-cocoa-soft hover:bg-cream-deep"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-cream-deep rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-cocoa h-1.5 rounded-full transition-all duration-700"
                style={{ width: `${Math.min((progress.today_new / goal) * 100, 100)}%` }}
              />
            </div>
            <span className="text-xs text-cocoa-soft tabular-nums whitespace-nowrap">
              {progress.today_new}/{goal}
            </span>
          </div>
          {progress.today_new >= goal && (
            <p className="text-xs text-mint-deep font-medium mt-2.5">
              ✓ 今日目标已达成
            </p>
          )}
        </div>
      )}

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard label="已学单词" value={progress?.learned_words ?? "-"} />
        <StatCard label="已掌握" value={progress?.known_words ?? "-"} />
        <StatCard label="连续天数" value={`${progress?.streak_days ?? 0} 天`} />
        <StatCard label="今日新学" value={progress?.today_new ?? 0} />
      </div>

      {/* 总进度 */}
      {progress && (
        <div className="bg-milk rounded-xl p-4 border border-honey">
          <div className="flex justify-between text-sm mb-2.5">
            <span className="text-cocoa-soft">总进度</span>
            <span className="text-cocoa font-medium tabular-nums">{progress.learned_words} / {progress.total_words}</span>
          </div>
          <div className="w-full bg-cream-deep rounded-full h-2 overflow-hidden">
            <div
              className="bg-cocoa h-2 rounded-full transition-all duration-700"
              style={{ width: `${Math.max((progress.learned_words / progress.total_words) * 100, 1)}%` }}
            />
          </div>
          <p className="text-xs text-cocoa-soft mt-2.5">
            已学 {Math.round((progress.learned_words / progress.total_words) * 100)}% · 剩 {progress.total_words - progress.learned_words} 词
          </p>
        </div>
      )}

      {/* 快捷入口 */}
      <div className="space-y-2.5 pt-1">
        <Link
          href="/study"
          className="block w-full py-4 bg-cocoa text-milk text-center rounded-xl font-semibold transition-all hover:bg-caramel active:scale-[0.98]"
        >
          开始今日学习
        </Link>
        <div className="grid grid-cols-2 gap-2.5">
          <Link
            href="/wordbooks"
            className="block py-3.5 bg-milk text-center rounded-xl font-medium text-cocoa border border-honey hover:border-cocoa-soft transition-colors active:scale-[0.98]"
          >
            词书
          </Link>
          <Link
            href="/quiz"
            className="block py-3.5 bg-milk text-center rounded-xl font-semibold text-cocoa border border-honey hover:border-cocoa-soft transition-colors active:scale-[0.98]"
          >
            测验
          </Link>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-milk rounded-xl p-4 border border-honey">
      <div className="text-2xl font-bold text-cocoa tabular-nums">{value}</div>
      <div className="text-xs text-cocoa-soft mt-0.5">{label}</div>
    </div>
  );
}
