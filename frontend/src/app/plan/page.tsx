"use client";

/**
 * 学习计划页
 *
 * 视觉沿用现有米白 + 深棕体系。
 * 与既有 localStorage 设置的关系（兼容策略，不静默覆盖）：
 *   - 服务端已有计划 → 以服务端为准；
 *   - 服务端还没有计划 → 用本机原有设置（每日目标 + 当前词书）作为**草稿**预填，不自动保存；
 *   - 只有用户点"保存计划"时，才把每日新词量与词书回写到本机设置，
 *     让"学习"页取的词量与计划一致（原有功能不受影响，仍是同一套 localStorage 键）。
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { planApi, wordbookApi } from "@/lib/api";
import type { GoalOption, PlanForecast, Wordbook } from "@/lib/types";
import { GOAL_OPTIONS, getDailyGoal, setDailyGoal } from "@/lib/settings";
import { getSelectedWordbook, setSelectedWordbook } from "@/lib/wordbook";

interface FormState {
  goal_type: string;
  wordbook_key: string;
  target_date: string;
  daily_new_words: number;
}

export default function PlanPage() {
  const [goals, setGoals] = useState<GoalOption[]>([]);
  const [books, setBooks] = useState<Wordbook[]>([]);
  const [form, setForm] = useState<FormState>({
    goal_type: "cet4",
    wordbook_key: "exam_cet4",
    target_date: "",
    daily_new_words: 20,
  });
  const [forecast, setForecast] = useState<PlanForecast | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  /** 服务端还没有计划时，暂用本机原有设置做草稿 */
  const [draftFromLocal, setDraftFromLocal] = useState(false);

  const loadForecast = useCallback(async () => {
    try {
      setForecast(await planApi.forecast());
    } catch (err) {
      setError(err instanceof Error ? err.message : "预测加载失败");
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const [options, bookList, current] = await Promise.all([
          planApi.options(),
          wordbookApi.list(),
          planApi.get(),
        ]);
        setGoals(options.goals);
        setBooks(bookList);

        if (current.plan) {
          setForm({
            goal_type: current.plan.goal_type,
            wordbook_key: current.plan.wordbook_key,
            target_date: current.plan.target_date ?? "",
            daily_new_words: current.plan.daily_new_words,
          });
          setDraftFromLocal(false);
        } else {
          // 兼容既有设置：本机选过的词书与每日目标直接作为草稿
          setForm({
            goal_type: options.goals[0]?.goal_type ?? "cet4",
            wordbook_key: getSelectedWordbook(),
            target_date: "",
            daily_new_words: getDailyGoal(),
          });
          setDraftFromLocal(true);
        }
        await loadForecast();
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [loadForecast]);

  /** 切换目标 → 采用该目标的默认词书（下拉框是最终选择，之后可随时改） */
  const pickGoal = (goal: GoalOption) => {
    setSaved(false);
    setForm((prev) => ({
      ...prev,
      goal_type: goal.goal_type,
      wordbook_key: goal.default_wordbook,
    }));
  };

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await planApi.save({
        goal_type: form.goal_type,
        wordbook_key: form.wordbook_key || null,
        target_date: form.target_date || null,
        daily_new_words: form.daily_new_words,
      });
      // 明确保存后才同步本机设置，避免静默覆盖用户原有选择
      setDailyGoal(res.plan.daily_new_words);
      setSelectedWordbook(res.plan.wordbook_key);
      setDraftFromLocal(false);
      setSaved(true);
      await loadForecast();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  // 服务端若存了非快捷选项的每日量，也要如实显示（不能悄悄改掉用户的值）
  const dayOptions = Array.from(
    new Set([...GOAL_OPTIONS, form.daily_new_words].filter((n) => n > 0))
  ).sort((a, b) => a - b);

  const selectedBook = books.find((b) => b.id === form.wordbook_key);
  const maxDue = Math.max(1, ...(forecast?.due?.next_7_days.map((d) => d.count) ?? [1]));

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-cocoa-soft">
        <span className="text-4xl inline-block animate-float">🌰</span>
        <p className="mt-3 font-medium text-sm">正在加载学习计划…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="text-center pt-2 pb-1">
        <h1 className="text-2xl font-bold text-cocoa tracking-tight">学习计划</h1>
        <p className="text-cocoa-soft mt-1.5 text-sm">定个目标，看看还要多久</p>
      </div>

      {error && (
        <div role="alert" className="bg-berry/10 border-2 border-berry/30 rounded-xl px-3 py-2 text-sm text-cocoa">
          ⚠️ {error}
        </div>
      )}
      {draftFromLocal && (
        <p className="text-xs text-cocoa-soft bg-milk-warm border border-honey rounded-xl px-3 py-2">
          还没有已保存的计划，下面已沿用你本机原有的设置作为草稿；点「保存计划」后以服务端为准。
        </p>
      )}
      {saved && (
        <p className="text-xs text-cocoa bg-milk-warm border-2 border-honey rounded-xl px-3 py-2">
          ✅ 计划已保存
        </p>
      )}

      {/* 学习目标 */}
      <section className="bg-milk rounded-2xl border border-honey p-5 space-y-3">
        <h2 className="font-bold text-cocoa text-sm">学习目标</h2>
        <div className="grid grid-cols-2 gap-2">
          {goals.map((g) => (
            <button
              key={g.goal_type}
              type="button"
              onClick={() => pickGoal(g)}
              aria-pressed={form.goal_type === g.goal_type}
              className={`text-left px-3 py-2.5 rounded-xl border-2 transition-all ${
                form.goal_type === g.goal_type
                  ? "border-cocoa bg-gradient-to-r from-milktea to-caramel text-white shadow-md"
                  : "border-honey text-cocoa hover:border-cocoa-soft"
              }`}
            >
              <span className="block font-bold text-sm">{g.name}</span>
              <span className="block text-[11px] opacity-80">{g.description}</span>
            </button>
          ))}
        </div>
      </section>

      {/* 词书 */}
      <section className="bg-milk rounded-2xl border border-honey p-5 space-y-3">
        <h2 className="font-bold text-cocoa text-sm">对应词书</h2>
        <select
          aria-label="词书"
          value={form.wordbook_key}
          onChange={(e) => {
            setSaved(false);
            setForm((prev) => ({ ...prev, wordbook_key: e.target.value }));
          }}
          className="w-full p-3 rounded-xl bg-cream text-cocoa border-2 border-honey focus:border-cocoa focus:outline-none"
        >
          {books.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}（{b.word_count} 词）
            </option>
          ))}
        </select>
        {selectedBook && (
          <p className="text-xs text-cocoa-soft">
            共 {selectedBook.word_count} 词{selectedBook.is_custom ? "（自定义词书）" : ""}
          </p>
        )}
      </section>

      {/* 每日新词量 + 目标日期 */}
      <section className="bg-milk rounded-2xl border border-honey p-5 space-y-4">
        <div className="space-y-2">
          <h2 className="font-bold text-cocoa text-sm">每日新词量</h2>
          <div className="flex gap-2">
            {dayOptions.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => {
                  setSaved(false);
                  setForm((prev) => ({ ...prev, daily_new_words: n }));
                }}
                aria-pressed={form.daily_new_words === n}
                className={`flex-1 py-2.5 rounded-xl font-bold text-sm border-2 transition-all ${
                  form.daily_new_words === n
                    ? "border-cocoa bg-cocoa text-milk"
                    : "border-honey text-cocoa-soft hover:text-cocoa"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <h2 className="font-bold text-cocoa text-sm">目标日期（可不设）</h2>
          <div className="flex gap-2">
            <input
              type="date"
              aria-label="目标日期"
              value={form.target_date}
              onChange={(e) => {
                setSaved(false);
                setForm((prev) => ({ ...prev, target_date: e.target.value }));
              }}
              className="flex-1 p-3 rounded-xl bg-cream text-cocoa border-2 border-honey focus:border-cocoa focus:outline-none"
            />
            <button
              type="button"
              onClick={() => {
                setSaved(false);
                setForm((prev) => ({ ...prev, target_date: "" }));
              }}
              className="px-3 rounded-xl border-2 border-honey text-cocoa-soft text-sm hover:text-cocoa"
            >
              不设
            </button>
          </div>
        </div>

        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="w-full py-3.5 rounded-xl bg-cocoa text-milk font-bold transition-all hover:bg-caramel active:scale-95 disabled:opacity-60"
        >
          {saving ? "保存中…" : "保存计划"}
        </button>
      </section>

      {/* 预测 */}
      {forecast && (
        <section className="bg-milk rounded-2xl border border-honey p-5 space-y-4">
          <h2 className="font-bold text-cocoa text-sm">进度预测</h2>

          {!forecast.has_plan || !forecast.wordbook ? (
            <p className="text-sm text-cocoa-soft">
              还没有计划。先在上面选好目标与词书并保存，这里会显示剩余词汇和预计完成时间。
            </p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-cream rounded-xl border border-honey py-3">
                  <div className="text-xl font-extrabold text-cocoa">
                    {forecast.remaining_new_words}
                  </div>
                  <div className="text-[11px] text-cocoa-soft mt-1">剩余新词</div>
                </div>
                <div className="bg-cream rounded-xl border border-honey py-3">
                  <div className="text-xl font-extrabold text-cocoa">
                    {forecast.days_to_finish === null ? "—" : `${forecast.days_to_finish} 天`}
                  </div>
                  <div className="text-[11px] text-cocoa-soft mt-1">预计学完</div>
                </div>
                <div className="bg-cream rounded-xl border border-honey py-3">
                  <div className="text-xl font-extrabold text-cocoa">
                    {forecast.due?.total_pending ?? 0}
                  </div>
                  <div className="text-[11px] text-cocoa-soft mt-1">今日待复习</div>
                </div>
              </div>

              <p className="text-xs text-cocoa-soft">
                {forecast.wordbook.name} 共 {forecast.wordbook.total_words} 词，已学{" "}
                {forecast.learned_words} 词
                {forecast.estimated_finish_date && forecast.has_plan && (
                  <>，按当前节奏预计 <span className="text-cocoa font-bold">{forecast.estimated_finish_date}</span> 学完</>
                )}
              </p>

              {forecast.target && (
                <div
                  className={`rounded-xl border-2 px-3 py-2 text-sm ${
                    forecast.target.feasible === true
                      ? "border-honey bg-milk-warm text-cocoa"
                      : "border-berry/40 bg-berry/10 text-cocoa"
                  }`}
                >
                  {forecast.target.feasible === true ? "✅ " : "⚠️ "}
                  目标日期 {forecast.target.date}：
                  {forecast.target.feasible === true ? "按当前节奏来得及" : "按当前节奏来不及"}
                  <span className="block text-xs text-cocoa-soft mt-1">{forecast.target.reason}</span>
                </div>
              )}

              {forecast.due && (
                <div className="space-y-2">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-xs font-bold text-cocoa">FSRS 到期复习负担</h3>
                    <span className="text-[11px] text-cocoa-soft">
                      逾期 {forecast.due.overdue}，
                      {forecast.due.scope === "wordbook" ? "仅本词书" : "全部"}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {forecast.due.next_7_days.map((d, i) => (
                      <div key={d.date} className="flex items-center gap-2 text-[11px]">
                        <span className="w-16 text-cocoa-soft">
                          {i === 0 ? "今天" : d.date.slice(5)}
                        </span>
                        <div className="flex-1 bg-cream rounded-full h-2.5 border border-honey overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-milktea to-caramel"
                            style={{ width: `${Math.round((d.count / maxDue) * 100)}%` }}
                          />
                        </div>
                        <span className="w-12 text-right text-cocoa font-medium">{d.count} 词</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <p className="text-[11px] text-cocoa-soft border-t border-honey pt-2">
                {forecast.estimate_note}
              </p>
            </>
          )}
        </section>
      )}

      <div className="text-center">
        <Link href="/study" className="text-sm text-cocoa-soft hover:text-cocoa">
          去学习 →
        </Link>
      </div>
    </div>
  );
}