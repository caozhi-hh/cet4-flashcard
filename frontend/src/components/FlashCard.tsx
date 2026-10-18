"use client";

import { useEffect, useState } from "react";
import type { FlashCard as FlashCardType, Rating, RatingPreview } from "@/lib/types";
import { aiApi, starredApi, studyApi } from "@/lib/api";
import { speak } from "@/lib/tts";
import { parseTags, tagLabel } from "@/lib/tags";
import { useToast } from "@/components/ui/toast";

interface Props {
  card: FlashCardType;
  /** 四档评分：1 重来 / 2 困难 / 3 良好 / 4 简单 */
  onRate: (rating: Rating) => void;
}

/** 四档按钮的文案与配色（沿用现有米白+深棕体系，不引入新主题） */
const GRADES: { rating: Rating; label: string; className: string }[] = [
  { rating: 1, label: "重来", className: "bg-berry/15 text-berry-deep hover:bg-berry/25" },
  { rating: 2, label: "困难", className: "bg-cream-deep text-cocoa hover:bg-honey" },
  { rating: 3, label: "良好", className: "bg-cocoa text-milk hover:bg-caramel" },
  { rating: 4, label: "简单", className: "bg-mint/15 text-mint-deep hover:bg-mint/25" },
];

/** 长单词自动降字号：competitiveness(15 字符) 在 360px 视口下用 text-4xl 会超出卡片内宽 */
function wordSizeClass(word: string): string {
  if (word.length > 12) return "text-2xl sm:text-3xl";
  if (word.length > 9) return "text-3xl sm:text-4xl";
  return "text-4xl";
}

/** 把"天数"格式化成给人看的时间，如 1 分钟 / 3 小时 / 12 天 / 2.1 个月 */
function formatInterval(days: number): string {
  if (!Number.isFinite(days) || days <= 0) return "现在";
  if (days < 1 / 24) return `${Math.max(1, Math.round(days * 1440))} 分钟`;
  if (days < 1) return `${Math.round(days * 24)} 小时`;
  if (days < 30) return `${Math.round(days)} 天`;
  if (days < 365) return `${(days / 30).toFixed(1)} 个月`;
  return `${(days / 365).toFixed(1)} 年`;
}

export default function FlashCard({ card, onRate }: Props) {
  const [flipped, setFlipped] = useState(false);
  const [mnemonic, setMnemonic] = useState<string | null>(null);
  const [loadingAI, setLoadingAI] = useState(false);
  const [starred, setStarred] = useState(false);
  const [preview, setPreview] = useState<RatingPreview[]>([]);
  const { word } = card;
  const wordTags = parseTags(word.tags);
  const { toast } = useToast();

  // 拉取四档评分各自的间隔，展示在按钮上（Anki 的按钮也带这个提示）
  useEffect(() => {
    let alive = true;
    studyApi
      .preview(word.id)
      .then((res) => {
        if (alive) setPreview(res.ratings);
      })
      .catch(() => {
        // 预览失败不影响评分，按钮退回只显示文案
        if (alive) setPreview([]);
      });
    return () => {
      alive = false;
    };
  }, [word.id]);

  // 回读收藏状态：原先恒为 false，已收藏的词再出现仍显示 ☆，
  // 点一下反而变成"取消收藏"，显示与语义都对不上。
  useEffect(() => {
    let alive = true;
    starredApi
      .ids()
      .then((res) => {
        if (alive) setStarred(res.stars.includes(word.id));
      })
      .catch(() => {
        // 读不到就维持未收藏：这是展示态，不该弹错误打扰学习
      });
    return () => {
      alive = false;
    };
  }, [word.id]);

  const intervalFor = (rating: Rating): string | null => {
    const hit = preview.find((p) => p.rating === rating);
    return hit ? formatInterval(hit.interval_days) : null;
  };

  const handleMnemonic = async () => {
    if (mnemonic) return;
    setLoadingAI(true);
    try {
      const res = await aiApi.getMnemonic(word.id);
      setMnemonic(res.mnemonic);
    } catch {
      setMnemonic("生成失败，请稍后重试");
    } finally {
      setLoadingAI(false);
    }
  };

  const toggleStar = (e: React.MouseEvent) => {
    e.stopPropagation();
    const next = !starred;
    setStarred(next);
    (next ? starredApi.add(word.id, "star") : starredApi.remove(word.id, "star")).catch((err) => {
      // 原先这里静默回滚，用户只会看到星星"弹回去"而不知道原因
      setStarred(!next);
      toast({
        variant: "error",
        title: next ? "收藏失败" : "取消收藏失败",
        description: err instanceof Error ? err.message : undefined,
      });
    });
  };

  return (
    <div className="w-full max-w-md mx-auto animate-slide-up">
      <p className="text-center text-xs text-cocoa-soft mb-3 tracking-wide">
        {card.status === "new" ? "NEW · 新词" : card.status === "learning" ? "LEARNING · 学习中" : "MASTERED · 已掌握"}
      </p>

      {/* 卡片主体
          正反面用 grid 叠在同一格（gridArea 1/1），而不是各自 absolute inset-0：
          这样容器高度取"较高的那一面"，长单词/长例句会把卡片撑高，而不是溢出压住下方按钮。 */}
      <div
        onClick={() => setFlipped(!flipped)}
        className="relative cursor-pointer"
        style={{ perspective: "1200px" }}
      >
        <div
          className="w-full grid transition-transform duration-500"
          style={{
            transformStyle: "preserve-3d",
            transform: flipped ? "rotateY(180deg)" : "rotateY(0)",
          }}
        >
          {/* 正面 */}
          <div
            className="rounded-2xl shadow-md p-6 sm:p-8 min-h-[280px] flex flex-col items-center justify-center border border-honey bg-milk"
            style={{ gridArea: "1 / 1", backfaceVisibility: "hidden" }}
          >
            <button
              onClick={toggleStar}
              className="absolute top-4 right-5 text-xl text-cocoa-soft hover:text-caramel transition-colors active:scale-90"
              title={starred ? "取消收藏" : "加入生词本"}
              aria-label="收藏"
            >
              {starred ? "★" : "☆"}
            </button>

            <p
              className={`font-bold text-cocoa mb-2 tracking-tight text-center max-w-full ${wordSizeClass(word.word)}`}
              style={{ overflowWrap: "anywhere" }}
            >
              {word.word}
            </p>
            <div className="flex items-center gap-2 mb-2">
              <p className="text-cocoa-soft text-sm text-center" style={{ overflowWrap: "anywhere" }}>
                {word.phonetic_us || word.phonetic_uk}
              </p>
              <button
                onClick={(e) => { e.stopPropagation(); speak(word.word); }}
                className="w-9 h-9 flex items-center justify-center rounded-full text-cocoa-soft hover:text-caramel hover:bg-cream-deep transition-colors active:scale-90 shrink-0"
                title="朗读单词"
                aria-label="朗读单词"
              >
                🔊
              </button>
            </div>
            {word.pos && (
              <span className="mt-3 px-2.5 py-0.5 rounded-md bg-cream-deep text-cocoa-soft text-xs">
                {word.pos}
              </span>
            )}
            <p className="text-xs text-cocoa-soft mt-6">点击翻转查看释义</p>
          </div>

          {/* 反面 */}
          <div
            className="rounded-2xl shadow-md p-6 sm:p-8 min-h-[280px] flex flex-col items-center justify-center border border-honey bg-milk"
            style={{ gridArea: "1 / 1", backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <p
              className="text-2xl font-bold text-cocoa mb-2 text-center max-w-full"
              style={{ overflowWrap: "anywhere" }}
            >
              {word.word}
            </p>
            <p
              className="text-base text-cocoa text-center mb-3 leading-relaxed max-w-full max-h-40 overflow-y-auto"
              style={{ overflowWrap: "anywhere" }}
            >
              {word.definition}
            </p>
            {word.example && (
              // 例句最长可达 197 字符：限高 + 内部滚动，不让它把卡片撑破
              <div className="text-sm text-cocoa-soft space-y-1.5 mt-2 px-2 max-w-full max-h-32 overflow-y-auto w-full">
                <p className="italic leading-relaxed flex items-start gap-1.5 justify-center">
                  <span className="flex-1" style={{ overflowWrap: "anywhere" }}>“{word.example}”</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); speak(word.example!, 0.85); }}
                    className="text-cocoa-soft hover:text-caramel transition-colors active:scale-90 shrink-0"
                    title="朗读例句"
                  >
                    🔊
                  </button>
                </p>
                {word.example_cn && (
                  <p className="text-cocoa-soft" style={{ overflowWrap: "anywhere" }}>{word.example_cn}</p>
                )}
              </div>
            )}

            {/* ECDICT 富化信息：考试标签 + 真实语料词频（放在反面，避免变成正面的记忆提示） */}
            {(wordTags.length > 0 || word.frq) && (
              <div className="flex flex-wrap items-center justify-center gap-1.5 mt-3">
                {wordTags.map((t) => (
                  <span
                    key={t}
                    className="px-2 py-0.5 rounded-md bg-cream-deep text-cocoa-soft text-[11px]"
                  >
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
          </div>
        </div>
      </div>

      {/* 记忆口诀 */}
      <div className="mt-4 text-center">
        <button
          onClick={handleMnemonic}
          disabled={loadingAI}
          className="text-sm font-medium text-caramel hover:text-cocoa disabled:text-cocoa-soft transition-colors active:scale-95"
        >
          {loadingAI ? "AI 思考中..." : mnemonic ? "查看记忆口诀" : "💡 生成记忆口诀"}
        </button>
        {mnemonic && (
          <div className="mt-2 p-4 bg-cream-deep rounded-xl text-sm text-cocoa text-left whitespace-pre-line border border-honey">
            {mnemonic}
          </div>
        )}
      </div>

      {/* 四档评分（FSRS）：按钮上显示该档会把下次复习推到什么时候 */}
      <div className="grid grid-cols-4 gap-2 mt-6">
        {GRADES.map((g) => {
          const hint = intervalFor(g.rating);
          return (
            <button
              key={g.rating}
              onClick={() => onRate(g.rating)}
              className={`py-3 rounded-xl font-semibold transition-all active:scale-95 ${g.className}`}
            >
              <span className="block text-sm">{g.label}</span>
              <span className="block text-[11px] font-normal opacity-80 mt-0.5 h-4">
                {hint ?? ""}
              </span>
            </button>
          );
        })}
      </div>
      <p className="text-center text-[11px] text-cocoa-soft mt-2">
        按回忆难度评分，间隔由 FSRS 自动安排
      </p>
    </div>
  );
}