"use client";

/**
 * 登录守卫
 *
 * 静态导出下没有服务端中间件可用，所以守卫在客户端做：
 *   - 会话探测完成后，未登录访问非公开页 → 记住目标路径并跳转 /login；
 *   - 未登录期间**不渲染受保护内容**，避免先闪一下数据再跳走；
 *   - 已登录访问 /login → 直接回首页。
 *
 * 注意：这只是导航层面的引导；真正的访问控制在后端（未登录一律 401）。
 */

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

/** 免登录页面（目前只有登录/注册页，两者同一个路由） */
export const PUBLIC_PATHS = ["/login"];

/** 登录后要跳回的路径存在这里（静态导出下用 sessionStorage，避免依赖 useSearchParams） */
export const NEXT_PATH_KEY = "cet4_next_path";

export default function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublic) {
      try {
        sessionStorage.setItem(NEXT_PATH_KEY, pathname);
      } catch {
        // 隐私模式下写不进去也不影响跳转
      }
      router.replace("/login");
      return;
    }
    if (user && isPublic) {
      router.replace("/");
    }
  }, [user, loading, isPublic, pathname, router]);

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center py-24 text-cocoa-soft">
        <span className="text-4xl inline-block animate-float">🌰</span>
        <p className="mt-3 font-medium text-sm">正在检查登录状态…</p>
      </div>
    );
  }

  // 未登录且是受保护页：跳转进行中，先不渲染内容
  if (!user && !isPublic) return null;

  return <>{children}</>;
}