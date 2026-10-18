"use client";

/**
 * 底部抽屉（shadcn 风格的 Sheet，基于 Radix Dialog）
 *
 * 借用 Radix 的行为：焦点陷阱、Esc 关闭、aria-modal、打开时锁定背景滚动。
 * 视觉沿用项目现有配色。
 *
 * 用途：生词本里"释义被 truncate 截断、看不到全文"的问题——
 * 点一条词打开抽屉看完整释义/例句，而不是把列表撑成一大片。
 */

import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** 给屏幕阅读器用的标题；不显示在界面上 */
  description?: string;
  children: ReactNode;
}

export function Sheet({ open, onOpenChange, title, description, children }: SheetProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[70] bg-cocoa/40 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          className="fixed z-[80] left-0 right-0 bottom-0 mx-auto w-full max-w-md rounded-t-3xl border-t-2 border-honey bg-milk p-5 pb-8 max-h-[85vh] overflow-y-auto shadow-2xl animate-slide-up"
          style={{ paddingBottom: "calc(2rem + env(safe-area-inset-bottom))" }}
        >
          {/* 拖拽把手（视觉提示，实际关闭用 Esc / 遮罩 / 右上角按钮） */}
          <div className="w-10 h-1.5 rounded-full bg-honey mx-auto mb-4" aria-hidden />

          <div className="flex items-start gap-3">
            <DialogPrimitive.Title className="flex-1 text-lg font-extrabold text-cocoa min-w-0 break-words">
              {title}
            </DialogPrimitive.Title>
            <DialogPrimitive.Close
              aria-label="关闭"
              className="shrink-0 w-8 h-8 rounded-full text-cocoa-soft hover:bg-cream-deep transition-colors flex items-center justify-center"
            >
              ✕
            </DialogPrimitive.Close>
          </div>

          {description && (
            <DialogPrimitive.Description className="sr-only">{description}</DialogPrimitive.Description>
          )}

          <div className="mt-3">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}