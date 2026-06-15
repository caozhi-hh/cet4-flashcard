"use client";

import { useEffect, useMemo, useState } from "react";
import { progressApi } from "@/lib/api";
import type { ProgressOverview, DailyProgress } from "@/lib/types";
import { getSelectedWordbook, onWordbookChange } from "@/lib/wordbook";
import { evaluateAchievements, countUnlocked, type AchievementExtra } from "@/lib/achievements";

export default function ProgressPage() {
  const [overview, setOverview] = useState<ProgressOverview | null>(null);
  const [calendar, setCalendar] = useState<DailyProgress[]>([]);
  const [extra] = useState<AchievementExtra>(() => ({
    createdAiWordbook: typeof window !== "undefined" && localStorage.getItem("cet4_ai_created") === "1",
    quizPerfect: typeof window !== "undefined" && localStorage.getItem("cet4_quiz_perfect") === "1",
  }));

  useEffect(() => {
    const load = () => {
      progressApi.getOverview(getSelectedWordbook()).then(setOverview).catch(() => {});
      progressApi.getCalendar(30).then(setCalendar).catch(() => {});
    };
    load();
    const unsub = onWordbookChange(load);
    return unsub;
  }, []);

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-extrabold text-cocoa text-center">📊 学习进度</h2>

      {/* 成就徽章 */}
      {overview && (
        <Achievements overview={overview} extra={extra} />
      )}

      {/* 总览 */}
      {overview && (
        <div className="grid grid-cols-3 gap-3">
          <MiniStat icon="📚" label="总词数" value={overview.total_words} delay={0} />
          <MiniStat icon="📖" label="已学" value={overview.learned_words} delay={50} />
          <MiniStat icon="✅" label="已掌握" value={overview.known_words} delay={100} />
          <MiniStat icon="🌱" label="今日新学" value={overview.today_new} color="caramel" delay={150} />
          <MiniStat icon="🔄" label="今日复习" value={overview.today_reviewed} color="caramel" delay={200} />
          <MiniStat icon="🔥" label="连续天数" value={`${overview.streak_days}天`} color="berry" delay={250} />
        </div>
      )}

      {/* 环形进度 */}
      {overview && (
        <div className="bg-milk-warm rounded-3xl p-6 border-2 border-honey/50 text-center shadow-sm shadow-caramel/10">
          <div className="relative w-36 h-36 mx-auto mb-3">
            <svg className="w-36 h-36 -rotate-90" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="50" fill="none" stroke="#F5DEB3" strokeWidth="12" />
              <circle
                cx="60" cy="60" r="50" fill="none" stroke="#E8A87C" strokeWidth="12"
                strokeDasharray={`${(overview.learned_words / overview.total_words) * 314} 314`}
                strokeLinecap="round"
                className="transition-all duration-1000"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-extrabold text-cocoa">
                {Math.round((overview.learned_words / overview.total_words) * 100)}%
              </span>
              <span className="text-xs text-cocoa-soft">完成度</span>
            </div>
          </div>
          <p className="text-sm text-cocoa-soft font-medium">
            🎯 已学习 <span className="text-caramel font-bold">{overview.learned_words}</span> / {overview.total_words} 个词汇
          </p>
        </div>
      )}

      {/* 学习日历 */}
      {calendar.length > 0 && (
        <div className="bg-milk-warm rounded-3xl p-5 border-2 border-honey/50 shadow-sm shadow-caramel/10">
          <h3 className="font-bold text-cocoa mb-4">📅 近期学习记录</h3>
          <div className="space-y-3">
            {calendar.slice(-14).reverse().map((day) => {
              const total = day.new_words + day.reviewed_words;
              return (
                <div key={day.date} className="flex items-center gap-3 text-sm">
                  <span className="text-cocoa-soft w-20 font-medium">{day.date.slice(5)}</span>
                  <div className="flex-1 bg-honey/30 rounded-full h-3.5 overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-honey via-caramel to-milktea h-3.5 rounded-full transition-all duration-700 shimmer-bar"
                      style={{ width: `${Math.min((total / 30) * 100, 100)}%` }}
                    />
                  </div>
                  <span className="text-cocoa-soft w-20 text-right text-xs">
                    <span className="text-caramel font-bold">+{day.new_words}</span> / 复{day.reviewed_words}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function MiniStat({ icon, label, value, color, delay }: { icon: string; label: string; value: string | number; color?: string; delay: number }) {
  const valueColor =
    color === "caramel" ? "text-caramel"
    : color === "berry" ? "text-berry-deep"
    : "text-cocoa";
  return (
    <div
      className="bg-milk-warm rounded-2xl p-3 border-2 border-honey/50 text-center shadow-sm shadow-caramel/10 hover:-translate-y-0.5 transition-all animate-bounce-in"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="text-xl mb-0.5 inline-block">{icon}</div>
      <div className={`text-xl font-extrabold ${valueColor}`}>{value}</div>
      <div className="text-xs text-cocoa-soft">{label}</div>
    </div>
  );
}

function Achievements({ overview, extra }: { overview: ProgressOverview; extra: AchievementExtra }) {
  const list = useMemo(() => evaluateAchievements(overview, extra), [overview, extra]);
  const unlockedCount = countUnlocked(list);

  return (
    <div className="bg-milk-warm rounded-3xl p-4 border-2 border-honey/50 shadow-sm shadow-caramel/10">
      <div className="flex items-center justify-between mb-3 px-1">
        <h3 className="font-bold text-cocoa flex items-center gap-1.5">
          <span>🏆</span> 成就徽章
        </h3>
        <span className="text-xs font-bold text-caramel bg-honey/30 px-2.5 py-1 rounded-full">
          已解锁 {unlockedCount}/{list.length}
        </span>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2.5">
        {list.map((a, i) => (
          <div
            key={a.id}
            title={`${a.name}：${a.desc}`}
            className={`relative aspect-square flex flex-col items-center justify-center p-2 rounded-2xl border-2 transition-all animate-bounce-in ${
              a.unlocked
                ? "bg-gradient-to-br from-honey/40 to-milk-warm border-milktea shadow-sm"
                : "bg-cream border-honey/30 opacity-50 grayscale"
            }`}
            style={{ animationDelay: `${i * 40}ms` }}
          >
            <span className={`text-3xl mb-1 ${a.unlocked ? "" : "opacity-40"}`}>
              {a.unlocked ? a.icon : "🔒"}
            </span>
            <span className="text-[10px] font-bold text-cocoa text-center leading-tight">{a.name}</span>
            {!a.unlocked && a.threshold && (
              <span className="text-[9px] text-cocoa-soft mt-0.5">
                {a.threshold.current(overview)}/{a.threshold.target}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
