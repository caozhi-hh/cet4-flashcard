"use client";

import { useEffect, useState } from "react";
import Confetti from "@/components/Confetti";
import { quizApi, starredApi } from "@/lib/api";
import { speak } from "@/lib/tts";
import type { QuizQuestion, QuizResult } from "@/lib/types";

export default function QuizPage() {
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    quizApi.getDaily()
      .then((data) => {
        setQuestions(data.questions);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleSubmit = async () => {
    if (submitting) return;
    setSubmitting(true);

    const payload = questions.map((q) => ({
      word_id: q.word_id,
      answer: answers[q.word_id] || "",
      correct_answer: q.correct_answer,
    }));

    try {
      const res = await quizApi.submit(payload);
      setResult(res);
      // 满分标记成就
      if (res.total > 0 && res.score >= res.total) {
        localStorage.setItem("cet4_quiz_perfect", "1");
      }
      // 错题自动加入错题本（API 已去重，可重复调用）
      for (const w of res.wrong_words) {
        starredApi.add(w.id, "hard").catch(() => {});
      }
    } catch {}
    setSubmitting(false);
  };

  if (loading) {
    return (
      <div className="text-center py-20 text-cocoa-soft">
        <span className="text-5xl inline-block animate-float">✏️</span>
        <p className="mt-4 font-medium">生成测验中...</p>
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="text-center py-20 space-y-4 animate-bounce-in">
        <div className="text-7xl inline-block animate-float">📝</div>
        <h2 className="text-2xl font-extrabold text-cocoa">还没有学过单词哦</h2>
        <p className="text-cocoa-soft font-medium">先去学习一些单词再来挑战吧 🌱</p>
        <a
          href="/study"
          className="inline-block mt-4 px-8 py-3 bg-gradient-to-r from-milktea to-caramel text-white rounded-2xl font-bold shadow-lg shadow-caramel/30 active:scale-95"
        >
          📖 去学习
        </a>
      </div>
    );
  }

  if (result) {
    const isGreat = result.score >= result.total * 0.8;
    return (
      <>
        {isGreat && <Confetti />}
        <div className="space-y-6 animate-bounce-in">
          <div className="text-center space-y-3">
            <div className="text-7xl inline-block animate-float">
              {isGreat ? "🏆" : "💪"}
            </div>
            <h2 className="text-4xl font-extrabold text-cocoa">
              <span className="animate-pop inline-block text-caramel">{result.score}</span>
              <span className="text-cocoa-soft"> / {result.total}</span>
            </h2>
            <p className="text-cocoa-soft font-medium text-lg">
              {isGreat ? "太棒了，你是词汇小天才！🌟" : "继续加油，下次会更好！🌻"}
            </p>
          </div>

          {result.wrong_words.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-bold text-cocoa">🍓 错题回顾</h3>
              {result.wrong_words.map((w) => (
                <div key={w.id} className="bg-berry/10 p-4 rounded-2xl border-2 border-berry/30">
                  <span className="font-bold text-cocoa">{w.word}</span>
                  <span className="text-cocoa-soft ml-2">{w.definition}</span>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={() => { setResult(null); setAnswers({}); }}
            className="w-full py-4 bg-gradient-to-r from-milktea to-caramel text-white rounded-2xl font-bold shadow-lg shadow-caramel/30 hover:shadow-xl transition-all active:scale-95"
          >
            🔄 再测一次
          </button>
        </div>
      </>
    );
  }

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-bold text-cocoa text-center">
        ✏️ 每日测验（{questions.length} 题）
      </h2>

      {questions.map((q, i) => {
        const selected = answers[q.word_id];
        return (
          <div key={q.word_id} className="bg-milk-warm p-5 rounded-3xl border-2 border-honey/50 space-y-3 shadow-sm shadow-caramel/10 animate-bounce-in" style={{ animationDelay: `${i * 40}ms` }}>
            <p className="font-bold text-cocoa">
              <span className="text-caramel">{i + 1}.</span> {q.question}
            </p>

            {q.quiz_type === "choice" && q.options && (
              <div className="grid grid-cols-2 gap-2.5">
                {q.options.map((opt, j) => {
                  const optValue = opt.replace(/^[A-D]\.\s*/, "");
                  const isSelected = selected === optValue;
                  return (
                    <button
                      key={j}
                      onClick={() => setAnswers({ ...answers, [q.word_id]: optValue })}
                      className={`p-3 rounded-xl text-sm text-left border transition-all active:scale-95 ${
                        isSelected
                          ? "bg-cocoa text-milk border-cocoa font-medium"
                          : "bg-cream border-honey text-cocoa-soft hover:border-cocoa-soft"
                      }`}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>
            )}

            {q.quiz_type === "listen" && q.options && (
              <div className="space-y-3">
                <button
                  onClick={() => speak(q.word)}
                  className="w-full py-4 rounded-xl bg-cocoa text-milk font-medium hover:bg-caramel transition-colors active:scale-95 flex items-center justify-center gap-2"
                >
                  <span className="text-lg">🔊</span> 点击播放读音（可重复）
                </button>
                <div className="grid grid-cols-2 gap-2.5">
                  {q.options.map((opt, j) => {
                    const optValue = opt.replace(/^[A-D]\.\s*/, "");
                    const isSelected = selected === optValue;
                    return (
                      <button
                        key={j}
                        onClick={() => {
                          speak(q.word);
                          setAnswers({ ...answers, [q.word_id]: optValue });
                        }}
                        className={`p-3 rounded-xl text-sm text-left border transition-all active:scale-95 ${
                          isSelected
                            ? "bg-cocoa text-milk border-cocoa font-medium"
                            : "bg-cream border-honey text-cocoa-soft hover:border-cocoa-soft"
                        }`}
                      >
                        {opt}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {q.quiz_type === "spell" && (
              <div className="space-y-2">
                <input
                  type="text"
                  autoCapitalize="none"
                  autoCorrect="off"
                  placeholder="输入英文单词"
                  value={answers[q.word_id] || ""}
                  onChange={(e) => setAnswers({ ...answers, [q.word_id]: e.target.value })}
                  className="w-full p-3 border border-honey rounded-xl text-base focus:outline-none focus:border-cocoa bg-cream text-cocoa placeholder:text-cocoa-soft/50 transition-all tracking-wider font-mono"
                />
                <p className="text-xs text-cocoa-soft">根据上方中文释义拼写英文（区分大小写不敏感）</p>
              </div>
            )}

            {q.quiz_type === "fill" && (
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder={q.hint || "输入英文单词"}
                  value={answers[q.word_id] || ""}
                  onChange={(e) => setAnswers({ ...answers, [q.word_id]: e.target.value })}
                  className="w-full p-3 border border-honey rounded-xl text-sm focus:outline-none focus:border-cocoa bg-cream text-cocoa placeholder:text-cocoa-soft/50 transition-all"
                />
                {q.hint && <p className="text-xs text-cocoa-soft">💡 {q.hint}</p>}
              </div>
            )}

            {q.quiz_type === "fill" && (
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder={q.hint || "输入英文单词"}
                  value={answers[q.word_id] || ""}
                  onChange={(e) => setAnswers({ ...answers, [q.word_id]: e.target.value })}
                  className="w-full p-3 border-2 border-honey/50 rounded-2xl text-sm focus:outline-none focus:border-milktea focus:ring-2 focus:ring-milktea/20 bg-cream text-cocoa placeholder:text-cocoa-soft/50 transition-all"
                />
                {q.hint && <p className="text-xs text-cocoa-soft">💡 {q.hint}</p>}
              </div>
            )}
          </div>
        );
      })}

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="w-full py-4 bg-gradient-to-r from-milktea to-caramel text-white rounded-2xl font-bold shadow-lg shadow-caramel/30 hover:shadow-xl transition-all active:scale-95 disabled:opacity-60"
      >
        {submitting ? "提交中..." : "✨ 提交答案"}
      </button>
    </div>
  );
}
