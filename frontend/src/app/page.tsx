"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { progressApi, wordbookApi } from "@/lib/api";
import type { ProgressOverview, Wordbook } from "@/lib/types";
import { getSelectedWordbook, onWordbookChange } from "@/lib/wordbook";
import { getDailyGoal, onGoalChange, GOAL_OPTIONS, DEFAULT_GOAL } from "@/lib/settings";
import { applyDailyGoal } from "@/lib/planGoal";
import { useAuth } from "@/components/AuthProvider";

export default function HomePage() {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [progress, setProgress] = useState<ProgressOverview | null>(null);
  const [wordbook, setWordbook] = useState<Wordbook | null>(null);
  const [selectedId, setSelectedId] = useState<string>(getSelectedWordbook());
  // 首帧用默认值：localStorage 在服务端读不到，直接拿它初始化 state 会造成 hydration 不一致
  // （服务端 20 / 客户端 30 → React 报错并整段重渲染），挂载后再同步真实值。
  const [goal, setGoalState] = useState<number>(DEFAULT_GOAL);
  const [error, setError] = useState<string | null>(null);
  const [goalError, setGoalError] = useState<string | null>(null);

  useEffect(() => {
    const loadAll = () => {
      const id = getSelectedWordbook();
      setSelectedId(id);
      setGoalState(getDailyGoal());
      progressApi.getOverview(id).then(setProgress).catch((e: Error) => setError(e.message));
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

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    // 退出后 user 变为 null，AuthGate 会自动把人送回登录页
    await logout();
  };

  // 每日新词量统一走 lib/planGoal：有服务端计划就写服务端，否则只写本机。
  // 失败时明确报错且**不改动**当前数值，不把新设置伪装成已保存。
  const pickGoal = async (n: number) => {
    setGoalError(null);
    const res = await applyDailyGoal(n);
    if (!res.ok) setGoalError(res.message ?? "每日新词量保存失败，未修改");
  };

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div className="text-center pt-2 pb-1 animate-fade-in">
        <h1 className="text-2xl font-bold text-cocoa tracking-tight">
          腰子背单词
        </h1>
        <p className="text-cocoa-soft mt-1.5 text-sm">每天 {goal} 个词，轻松过四级</p>
      </div>

      {/* 当前账号 + 退出登录 */}
      {user && (
        <div className="flex items-center justify-center gap-2 text-xs text-cocoa-soft">
          <span className="truncate max-w-[60%]" title={user.email}>
            👤 {user.email}
          </span>
          <button
            onClick={handleLogout}
            disabled={loggingOut}
            className="px-2.5 py-1 rounded-lg border border-honey hover:border-cocoa-soft hover:text-cocoa transition-colors disabled:opacity-60"
          >
            {loggingOut ? "退出中…" : "退出登录"}
          </button>
        </div>
      )}

      {/* 数据加载失败提示：不要用 "-" 和 "0 天" 把服务异常伪装成正常 */}
      {error && !progress && (
        <div className="bg-berry/10 border-2 border-berry/30 rounded-xl px-3 py-2 text-sm text-cocoa">
          ⚠️ {error}
        </div>
      )}

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
                  onClick={() => void pickGoal(n)}
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
          {goalError && (
            <p role="alert" className="text-xs text-cocoa bg-berry/10 border border-berry/30 rounded-lg px-2 py-1.5 mt-2">
              ⚠️ {goalError}
            </p>
          )}
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
          {/* 复习页此前没有任何入口，间隔重复等于白做 */}
          <Link
            href="/review"
            className="block py-3.5 bg-milk text-center rounded-xl font-semibold text-cocoa border border-honey hover:border-cocoa-soft transition-colors active:scale-[0.98]"
          >
            复习
          </Link>
          <Link
            href="/plan"
            className="block py-3.5 bg-milk text-center rounded-xl font-semibold text-cocoa border border-honey hover:border-cocoa-soft transition-colors active:scale-[0.98]"
          >
            学习计划
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
