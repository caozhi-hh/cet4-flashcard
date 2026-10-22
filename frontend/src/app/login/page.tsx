"use client";

/**
 * 登录 / 注册页
 *
 * 视觉沿用现有米白 + 深棕体系，不引入新设计。
 * 会话凭证由后端通过 HttpOnly Cookie 下发（前端不接触也不存储任何长期凭证）。
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { NEXT_PATH_KEY } from "@/components/AuthGate";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 注意：这里**不要**再写"已登录就回首页"的 effect。
  // 已登录用户访问 /login 由 AuthGate 统一处理；在本页写会与登录成功后的
  // 「跳回原目标」冲突——effect 后执行，会把用户从目标页又推回首页。

  const goAfterAuth = () => {
    let next = "/";
    try {
      next = sessionStorage.getItem(NEXT_PATH_KEY) || "/";
      sessionStorage.removeItem(NEXT_PATH_KEY);
    } catch {
      // 读不到就用首页
    }
    router.replace(next);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting) return;

    const trimmed = email.trim();
    if (!trimmed || !password) {
      setError("请输入邮箱和密码");
      return;
    }
    if (mode === "register" && password.length < 8) {
      setError("密码至少 8 位");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(trimmed, password);
      } else {
        await register(trimmed, password);
      }
      goAfterAuth();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-sm mx-auto pt-10 space-y-6 animate-bounce-in">
      <div className="text-center space-y-2">
        <div className="text-5xl inline-block animate-float">🌰</div>
        <h1 className="text-2xl font-extrabold text-cocoa">腰子背单词</h1>
        <p className="text-cocoa-soft text-sm font-medium">
          {mode === "login" ? "登录后继续你的学习进度" : "注册一个新账号开始背单词"}
        </p>
      </div>

      {/* 登录 / 注册切换 */}
      <div className="flex gap-2 bg-milk-warm rounded-2xl p-1.5 border-2 border-honey/50">
        {(["login", "register"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => {
              setMode(m);
              setError(null);
            }}
            className={`flex-1 py-2.5 rounded-xl font-bold text-sm transition-all ${
              mode === m
                ? "bg-gradient-to-r from-milktea to-caramel text-white shadow-md"
                : "text-cocoa-soft hover:text-cocoa"
            }`}
          >
            {m === "login" ? "登录" : "注册"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="bg-milk rounded-2xl border border-honey p-5 space-y-4">
        <label className="block">
          <span className="text-xs text-cocoa-soft">邮箱</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="you@example.com"
            aria-label="邮箱"
            className="mt-1 w-full p-3 rounded-xl bg-cream text-cocoa border-2 border-honey focus:border-cocoa focus:outline-none transition-colors"
          />
        </label>

        <label className="block">
          <span className="text-xs text-cocoa-soft">密码</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder={mode === "register" ? "至少 8 位" : "输入密码"}
            aria-label="密码"
            className="mt-1 w-full p-3 rounded-xl bg-cream text-cocoa border-2 border-honey focus:border-cocoa focus:outline-none transition-colors"
          />
        </label>

        {error && (
          <p role="alert" className="bg-berry/10 border-2 border-berry/30 rounded-xl px-3 py-2 text-sm text-cocoa">
            ⚠️ {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full py-3.5 rounded-xl bg-cocoa text-milk font-bold transition-all hover:bg-caramel active:scale-95 disabled:opacity-60"
        >
          {submitting ? "处理中…" : mode === "login" ? "登录" : "注册并开始"}
        </button>
      </form>

      <p className="text-center text-xs text-cocoa-soft">
        你的学习记录、收藏与词书只属于你自己，其他账号看不到。
      </p>
    </div>
  );
}