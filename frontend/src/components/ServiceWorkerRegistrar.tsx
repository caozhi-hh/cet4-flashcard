"use client";

import { useEffect } from "react";

/**
 * 注册 Service Worker（离线可用）
 *
 * - 只在生产构建里注册：开发服务器由 Next 自己管理，注册 SW 会干扰热更新。
 * - 注册失败不阻塞页面（console.warn 即可）：没有离线能力也不该影响正常使用。
 * - 作用域是根路径（sw.js 由后端从 static/ 根目录提供），因此能拦截所有页面导航。
 */
export default function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;

    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch((err) => {
        console.warn("Service Worker 注册失败（不影响正常使用）:", err);
      });
    };

    if (document.readyState === "complete") {
      register();
      return;
    }
    window.addEventListener("load", register);
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}