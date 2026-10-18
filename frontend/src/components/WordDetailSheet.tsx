"use client";

/**
 * 单词详情抽屉 —— 解决"生词本里释义被 truncate 截断、看不到全文"的问题
 *
 * 列表里只显示两行摘要，点开这里看完整的释义、例句、考试标签与词频，并能朗读。
 */

import { Sheet } from "@/components/ui/sheet";
import type { Word } from "@/lib/types";
import { parseTags, tagLabel } from "@/lib/tags";
import { speak } from "@/lib/tts";

interface Props {
  word: Word | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 传入则显示"移除"按钮（生词本/错题本用） */
  onRemove?: () => void;
  removeLabel?: string;
}

export default function WordDetailSheet({ word, open, onOpenChange, onRemove, removeLabel = "移除" }: Props) {
  const tags = parseTags(word?.tags);

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title={word?.word ?? ""}
      description={word ? `${word.word} 的完整释义与例句` : undefined}
    >
      {word && (
        <div className="space-y-4">
          {/* 音标 + 发音 */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-cocoa-soft text-sm" style={{ overflowWrap: "anywhere" }}>
              {word.phonetic_us || word.phonetic_uk || "（无音标）"}
            </span>
            <button
              onClick={() => speak(word.word)}
              className="w-9 h-9 flex items-center justify-center rounded-full text-cocoa-soft hover:text-caramel hover:bg-cream-deep transition-colors active:scale-90"
              aria-label="朗读单词"
              title="朗读单词"
            >
              🔊
            </button>
            {word.pos && (
              <span className="px-2.5 py-0.5 rounded-md bg-cream-deep text-cocoa-soft text-xs">{word.pos}</span>
            )}
          </div>

          {/* 完整释义（不再截断） */}
          <div>
            <p className="text-xs text-cocoa-soft mb-1">释义</p>
            <p className="text-base text-cocoa leading-relaxed" style={{ overflowWrap: "anywhere" }}>
              {word.definition}
            </p>
          </div>

          {/* 完整例句 */}
          {word.example && (
            <div>
              <p className="text-xs text-cocoa-soft mb-1">例句</p>
              <div className="flex items-start gap-2">
                <p className="flex-1 text-sm italic text-cocoa leading-relaxed" style={{ overflowWrap: "anywhere" }}>
                  “{word.example}”
                </p>
                <button
                  onClick={() => speak(word.example!, 0.85)}
                  className="shrink-0 w-8 h-8 flex items-center justify-center rounded-full text-cocoa-soft hover:text-caramel hover:bg-cream-deep transition-colors active:scale-90"
                  aria-label="朗读例句"
                  title="朗读例句"
                >
                  🔊
                </button>
              </div>
              {word.example_cn && (
                <p className="text-sm text-cocoa-soft mt-1" style={{ overflowWrap: "anywhere" }}>
                  {word.example_cn}
                </p>
              )}
            </div>
          )}

          {/* ECDICT 富化信息 */}
          {(tags.length > 0 || word.frq) && (
            <div className="flex flex-wrap items-center gap-1.5">
              {tags.map((t) => (
                <span key={t} className="px-2 py-0.5 rounded-md bg-cream-deep text-cocoa-soft text-[11px]">
                  {tagLabel(t)}
                </span>
              ))}
              {word.frq ? (
                <span className="px-2 py-0.5 rounded-md bg-cream-deep text-cocoa-soft text-[11px] tabular-nums">
                  COCA #{word.frq}
                </span>
              ) : null}
            </div>
          )}

          {onRemove && (
            <button
              onClick={onRemove}
              className="w-full py-3 rounded-xl bg-berry/15 text-berry-deep font-semibold hover:bg-berry/25 transition-all active:scale-[0.98]"
            >
              {removeLabel}
            </button>
          )}
        </div>
      )}
    </Sheet>
  );
}