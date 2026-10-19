"use client";

/**
 * 认证状态（客户端）
 *
 * 会话凭证只存在 HttpOnly Cookie 里，前端**不保存任何长期凭证**（不进 localStorage）。
 * 前端只持有"当前用户是谁"这份展示态，且每次都以服务端 /api/auth/me 为准。
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, UNAUTHORIZED_EVENT, authApi } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

interface AuthContextValue {
  user: AuthUser | null;
  /** 首次会话探测是否进行中（决定是否显示加载态，避免闪一下登录页） */
  loading: boolean;
  refresh: () => Promise<AuthUser | null>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
      return me;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // 未登录 / 会话过期：正常状态，不是错误
        setUser(null);
      }
      // 其它错误（后端不可用）：保持现状，避免把已登录用户误判成登出
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const me = await authApi.login(email, password);
    setUser(me);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const me = await authApi.register(email, password);
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // 服务端吊销失败也要本地登出，否则用户会"点了没反应"
    }
    setUser(null);
  }, []);

  // 任何请求收到 401（会话过期/被吊销）都会广播事件，这里统一把状态置为未登录，
  // 由 AuthGate 决定跳转，避免每个页面各写一遍处理。
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  // 启动时探测一次会话（顺带拿到 CSRF 令牌）
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ user, loading, refresh, login, register, logout }),
    [user, loading, refresh, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 <AuthProvider> 内使用");
  return ctx;
}