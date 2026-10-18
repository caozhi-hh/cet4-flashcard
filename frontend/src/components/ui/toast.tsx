"use client";

/**
 * Toast 交互原语（shadcn 风格，基于 Radix Toast）
 *
 * 只借用 Radix 的行为（自动消失、可滑动关闭、无障碍 live region、焦点管理），
 * 视觉完全沿用项目现有的米白 + 深棕配色，不引入 shadcn 的默认主题。
 *
 * 用途：把原先"静默吞掉"的失败暴露出来——收藏失败、移除失败、删除词书失败等。
 */

import * as ToastPrimitive from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { TTS_ERROR_EVENT } from "@/lib/tts";

export type ToastVariant = "default" | "success" | "error";

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
}

interface ToastItem extends ToastOptions {
  id: number;
}

interface ToastContextValue {
  toast: (options: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/** 变体样式：全部落在既有配色上（error 用 berry，success 用 mint） */
const VARIANT_CLASS: Record<ToastVariant, string> = {
  default: "bg-milk border-honey text-cocoa",
  success: "bg-mint/10 border-mint text-cocoa",
  error: "bg-berry/10 border-berry text-cocoa",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((options: ToastOptions) => {
    // 用时间戳 + 随机数做 id：同一毫秒连续弹两条也不会撞 key
    setToasts((prev) => [...prev, { ...options, id: Date.now() + Math.random() }]);
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  // 朗读失败等"库层"错误由 lib/tts 广播事件，这里统一提示——
  // 这样各页面的 🔊 按钮不用各写一遍错误处理。
  useEffect(() => {
    const onTtsError = (event: Event) => {
      const reason = (event as CustomEvent<{ reason?: string }>).detail?.reason;
      toast({ variant: "error", title: "朗读失败", description: reason });
    };
    window.addEventListener(TTS_ERROR_EVENT, onTtsError);
    return () => window.removeEventListener(TTS_ERROR_EVENT, onTtsError);
  }, [toast]);

  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider swipeDirection="down">
        {children}

        {toasts.map((t) => (
          <ToastPrimitive.Root
            key={t.id}
            duration={t.variant === "error" ? 6000 : 3500}
            onOpenChange={(open) => {
              if (!open) dismiss(t.id);
            }}
            className={`pointer-events-auto rounded-2xl border-2 px-4 py-3 shadow-lg shadow-caramel/10 ${
              VARIANT_CLASS[t.variant ?? "default"]
            }`}
          >
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <ToastPrimitive.Title className="font-bold text-sm">{t.title}</ToastPrimitive.Title>
                {t.description && (
                  <ToastPrimitive.Description className="text-xs text-cocoa-soft mt-1 break-words">
                    {t.description}
                  </ToastPrimitive.Description>
                )}
              </div>
              <ToastPrimitive.Close
                aria-label="关闭提示"
                className="shrink-0 w-6 h-6 rounded-full text-cocoa-soft hover:bg-cream-deep transition-colors flex items-center justify-center"
              >
                ✕
              </ToastPrimitive.Close>
            </div>
          </ToastPrimitive.Root>
        ))}

        {/* 底部导航是 fixed 的（56px + 安全区），提示要浮在它上方，否则会被盖住 */}
        <ToastPrimitive.Viewport className="fixed z-[60] left-0 right-0 bottom-20 md:bottom-4 mx-auto flex max-w-md flex-col gap-2 px-4 pointer-events-none outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast 必须在 <ToastProvider> 内使用");
  return ctx;
}