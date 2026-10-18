/**
 * 交互测试：操作失败必须有可见反馈（不再静默）
 *
 * 为什么要有这个测试：
 *   阶段 4 的核心修复是"把静默失败暴露出来"——收藏失败原先只是悄悄把星星弹回去，
 *   用户不知道发生了什么。这种问题用 grep 源码是验不出来的，必须在真实 DOM 里点一下。
 *
 * 运行方式：npm run test:ui（内部用 esbuild 打包本文件后交给 jsdom 跑）
 */

import { act } from "react";
import { createRoot } from "react-dom/client";
import FlashCard from "@/components/FlashCard";
import StudyPage from "@/app/study/page";
import { ToastProvider } from "@/components/ui/toast";
import { computeStats, isCorrect, type WordAttempt } from "@/lib/dictation";
import type { FlashCard as CardType } from "@/lib/types";

const CARD: CardType = {
  status: "new",
  word: {
    id: 16,
    word: "addiction",
    phonetic_us: "/əˈdɪkʃn/",
    phonetic_uk: "/əˈdɪkʃn/",
    definition: "n. 上瘾，沉溺",
    pos: "n",
    example: "She helped him fight his drug addiction.",
    example_cn: "她帮助他对抗自己的毒瘾。",
    tags: "cet4 cet6 ky",
    frq: 2182,
  },
};

let results: { name: string; ok: boolean; detail: string }[] = [];

function check(name: string, ok: boolean, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  -> " + detail : ""}`);
}

/** 装一个可控的 fetch：预览接口永远成功，收藏接口按参数决定成败 */
function installFetch(starShouldFail: boolean) {
  const calls: string[] = [];
  (globalThis as any).fetch = async (input: any, init?: any) => {
    const url = typeof input === "string" ? input : input.url;
    calls.push(`${init?.method ?? "GET"} ${url}`);
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

    if (url.includes("/api/study/preview")) return json({ word_id: 16, ratings: [] });
    if (url.includes("/api/starred")) {
      return starShouldFail ? json({ detail: "后端服务不可用" }, 500) : json({ message: "已添加" });
    }
    return json({});
  };
  return calls;
}

async function mount() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <ToastProvider>
        <FlashCard card={CARD} onRate={() => {}} />
      </ToastProvider>
    );
  });
  return { root, container };
}

function starButton(root: ParentNode): HTMLButtonElement {
  const btn = [...root.querySelectorAll("button")].find((b) => {
    const t = (b.textContent || "").trim();
    return t === "☆" || t === "★";
  });
  if (!btn) throw new Error("找不到收藏按钮");
  return btn as HTMLButtonElement;
}

async function click(el: Element) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    // 让被点出来的 Promise 链跑完（fetch stub → .catch → setState）
    await Promise.resolve();
    await Promise.resolve();
  });
}

const bodyText = () => document.body.textContent || "";

async function main() {
  // === 用例 1：收藏失败 → 必须出现错误提示，且星星回滚 ===
  installFetch(true);
  let { root, container } = await mount();
  const before = bodyText();
  check("初始不显示错误提示", !before.includes("收藏失败"), before.slice(0, 40));

  await click(starButton(container));
  const afterFail = bodyText();
  check("收藏失败时出现提示", afterFail.includes("收藏失败"), afterFail.replace(/\s+/g, " ").slice(0, 80));
  check("提示里带上后端返回的原因", afterFail.includes("后端服务不可用"), "");
  check("失败后星星回滚为未收藏", starButton(container).textContent?.trim() === "☆", "");

  await act(async () => root.unmount());
  container.remove();
  document.body.innerHTML = "";

  // === 用例 2：收藏成功 → 不许出现错误提示（防止误报）===
  installFetch(false);
  ({ root, container } = await mount());
  await click(starButton(container));
  const okText = bodyText();
  check("收藏成功时星星变实心", starButton(container).textContent?.trim() === "★", "");
  check("收藏成功时不弹错误提示", !okText.includes("收藏失败"), okText.replace(/\s+/g, " ").slice(0, 80));

  await act(async () => root.unmount());

  // === 用例 3：详情抽屉必须能完整展示被截断的释义 ===
  const { default: WordDetailSheet } = await import("@/components/WordDetailSheet");
  const sheetHost = document.createElement("div");
  document.body.appendChild(sheetHost);
  const sheetRoot = createRoot(sheetHost);
  await act(async () => {
    sheetRoot.render(
      <ToastProvider>
        <WordDetailSheet
          word={{ ...CARD.word, definition: "adj. 最优秀的，典型的，标准的；传统式样的，典雅的；n. 文学名著，经典作品" }}
          open
          onOpenChange={() => {}}
        />
      </ToastProvider>
    );
  });
  const sheetText = document.body.textContent || "";
  check("抽屉展示完整释义", sheetText.includes("传统式样的，典雅的"), sheetText.replace(/\s+/g, " ").slice(0, 60));
  check("抽屉展示考试标签", sheetText.includes("四级"), "");
  check("抽屉展示词频", sheetText.includes("COCA #2182"), "");
  await act(async () => sheetRoot.unmount());

  // === 用例 4：默写量化统计（速度/正确率公式）===
  const attempts: WordAttempt[] = [
    { wordId: 1, word: "alpha", attempts: 1, correct: true, elapsedMs: 6000, typedChars: 5 },
    { wordId: 2, word: "bravo", attempts: 2, correct: true, elapsedMs: 12000, typedChars: 14 },
    { wordId: 3, word: "charlie", attempts: 3, correct: false, elapsedMs: 30000, typedChars: 25 },
  ];
  const stats = computeStats(attempts);
  // 输入字符 5+14+25=44，用时 48s=0.8min
  check("正确率只算一次就对", stats.accuracy === 33.3, `${stats.accuracy}%`);
  check("最终答对数", stats.correct === 2, String(stats.correct));
  check("总用时累加", stats.elapsedMs === 48000, String(stats.elapsedMs));
  check("CPM = 字符/分钟", stats.cpm === 55, String(stats.cpm));
  check("WPM = 字符/5/分钟", stats.wpm === 11, String(stats.wpm));
  check("平均每题用时", stats.avgSecondsPerWord === 16, `${stats.avgSecondsPerWord}s`);
  check("错词列表只含没写对的", JSON.stringify(stats.wrong) === '["charlie"]', JSON.stringify(stats.wrong));
  check("归一化忽略大小写与空格", isCorrect("  Alpha ", "alpha"), "");
  const empty = computeStats([]);
  check("空结果不炸且不除零", empty.total === 0 && empty.cpm === 0 && empty.accuracy === 0, "");

  // === 用例 5：学完一章必须出现"默写本章"入口（闭环）===
  const studyWord = {
    id: 77, word: "closure", phonetic_us: "/ˈkloʊʒər/", phonetic_uk: null,
    definition: "n. 闭合，结束", pos: "n", example: null, example_cn: null, tags: "cet4", frq: 120,
  };
  (globalThis as any).fetch = async (input: any) => {
    const url = typeof input === "string" ? input : input.url;
    const json = (b: unknown, s = 200) =>
      new Response(JSON.stringify(b), { status: s, headers: { "Content-Type": "application/json" } });
    if (url.includes("/api/study/today")) return json({ type: "new", words: [{ word: studyWord, status: "new" }], total: 1 });
    if (url.includes("/api/study/preview")) return json({ word_id: 77, ratings: [] });
    return json({});
  };
  const studyHost = document.createElement("div");
  document.body.appendChild(studyHost);
  const studyRoot = createRoot(studyHost);
  await act(async () => {
    studyRoot.render(
      <ToastProvider>
        <StudyPage />
      </ToastProvider>
    );
  });
  const gradeBtn = [...studyHost.querySelectorAll("button")].find((b) => (b.textContent || "").includes("良好"));
  check("学习页渲染出四档评分按钮", !!gradeBtn, gradeBtn ? "找到「良好」" : "未找到");

  if (gradeBtn) await click(gradeBtn);
  const doneHtml = document.body.innerHTML;
  check("学完后出现「默写本章」入口", doneHtml.includes('href="/dictation"'), "");
  check("学完后仍保留「去做测验」入口", doneHtml.includes('href="/quiz"'), "");
  await act(async () => studyRoot.unmount());

  // === 用例 6：已收藏的词必须回读为 ★（原先恒为 ☆）===
  (globalThis as any).fetch = async (input: any) => {
    const url = typeof input === "string" ? input : input.url;
    const json = (b: unknown, s = 200) =>
      new Response(JSON.stringify(b), { status: s, headers: { "Content-Type": "application/json" } });
    if (url.includes("/api/starred/ids")) return json({ stars: [CARD.word.id], hards: [] });
    if (url.includes("/api/study/preview")) return json({ word_id: CARD.word.id, ratings: [] });
    return json({});
  };
  const starHost = document.createElement("div");
  document.body.appendChild(starHost);
  const starRoot = createRoot(starHost);
  await act(async () => {
    starRoot.render(
      <ToastProvider>
        <FlashCard card={CARD} onRate={() => {}} />
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  check("已收藏的词回读为 ★", starButton(starHost).textContent?.trim() === "★", starButton(starHost).textContent || "");

  // === 用例 7：朗读不可用要有提示（原先只 console.warn，用户以为点坏了）===
  const speakBtn = [...starHost.querySelectorAll("button")].find(
    (b) => b.getAttribute("aria-label") === "朗读单词"
  );
  check("卡片上音标旁有发音按钮", !!speakBtn, speakBtn ? "找到" : "未找到");
  if (speakBtn) await click(speakBtn);
  const ttsText = document.body.textContent || "";
  check("朗读失败时出现提示", ttsText.includes("朗读失败"), ttsText.replace(/\s+/g, " ").slice(-90));
  await act(async () => starRoot.unmount());

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  // 显式退出：Radix 会留下定时器/观察器，不退出的话 node 会一直挂着
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  console.log("ERROR", e?.stack || e?.message || e);
  // act 把内部错误包成 AggregateError，不打出来就只看到一句 AggregateError
  if (e?.errors?.length) {
    console.log("内部错误（%d 个）:", e.errors.length);
    for (const inner of e.errors) console.log("  -", inner?.stack || inner?.message || String(inner));
  }
  process.exit(1);
});