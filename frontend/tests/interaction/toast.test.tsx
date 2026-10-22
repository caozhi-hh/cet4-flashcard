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
import LoginPage from "@/app/login/page";
import PlanPage from "@/app/plan/page";
import HomePage from "@/app/page";
import ReadingPage from "@/app/reading/page";
import AuthGate from "@/components/AuthGate";
import { AuthProvider } from "@/components/AuthProvider";
import { ToastProvider } from "@/components/ui/toast";
import { computeStats, isCorrect, type WordAttempt } from "@/lib/dictation";
import type { FlashCard as CardType } from "@/lib/types";
// 与 --alias:next/navigation=... 指向同一个文件，因此共享跳转记录
import { __navigationCalls, __resetNavigation } from "./mocks/next-navigation";

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

  // === 用例 8：未登录访问受保护页 → 引导登录，且不渲染受保护内容 ===
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  __resetNavigation("/study");
  (globalThis as any).fetch = async (input: any) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/api/auth/me")) return json({ detail: "未登录" }, 401);
    if (url.includes("/api/auth/csrf")) return json({ csrf_token: "t" });
    return json({});
  };
  const gateHost = document.createElement("div");
  document.body.appendChild(gateHost);
  const gateRoot = createRoot(gateHost);
  await act(async () => {
    gateRoot.render(
      <ToastProvider>
        <AuthProvider>
          <AuthGate>
            <div>受保护内容</div>
          </AuthGate>
        </AuthProvider>
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  const gateCalls = __navigationCalls();
  check("未登录被引导到 /login", gateCalls.some((c) => c.endsWith(":/login")), gateCalls.join(" | "));
  check("未登录不渲染受保护内容", !document.body.textContent?.includes("受保护内容"), "");
  check("记住了原目标路径", sessionStorage.getItem("cet4_next_path") === "/study", String(sessionStorage.getItem("cet4_next_path")));
  await act(async () => gateRoot.unmount());
  gateHost.remove();

  // === 用例 9：已登录访问 /login → 直接回首页 ===
  __resetNavigation("/login");
  (globalThis as any).fetch = async (input: any) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/api/auth/me")) return json({ id: 1, email: "a@b.com", created_at: null });
    return json({});
  };
  const backHost = document.createElement("div");
  document.body.appendChild(backHost);
  const backRoot = createRoot(backHost);
  await act(async () => {
    backRoot.render(
      <ToastProvider>
        <AuthProvider>
          <AuthGate>
            <div>应用内容</div>
          </AuthGate>
        </AuthProvider>
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  check("已登录访问 /login 回首页", __navigationCalls().some((c) => c === "replace:/"), __navigationCalls().join(" | "));
  await act(async () => backRoot.unmount());
  backHost.remove();

  // === 用例 10：登录失败要显示后端给的原因 ===
  __resetNavigation("/login");
  (globalThis as any).fetch = async (input: any, init?: any) => {
    const url = typeof input === "string" ? input : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes("/api/auth/me")) return json({ detail: "未登录" }, 401);
    if (url.includes("/api/auth/csrf")) return json({ csrf_token: "t" });
    if (url.includes("/api/auth/login") && method === "POST") return json({ detail: "邮箱或密码不正确" }, 401);
    return json({});
  };
  const loginHost = document.createElement("div");
  document.body.appendChild(loginHost);
  const loginRoot = createRoot(loginHost);
  await act(async () => {
    loginRoot.render(
      <ToastProvider>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
  });

  /** 受控 input 要改值必须走原生 setter + input 事件，直接赋 value 不会触发 React onChange */
  const setInput = async (el: HTMLInputElement, value: string) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(el, value);
    await act(async () => {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  const submitOf = (host: HTMLElement) =>
    [...host.querySelectorAll("button")].find((b) => b.getAttribute("type") === "submit");

  const emailInput = loginHost.querySelector('input[type="email"]') as HTMLInputElement;
  const pwdInput = loginHost.querySelector('input[type="password"]') as HTMLInputElement;
  check("登录页渲染邮箱与密码输入", !!emailInput && !!pwdInput, "");
  await setInput(emailInput, "a@b.com");
  await setInput(pwdInput, "password123");
  const submitBtn = submitOf(loginHost);
  if (submitBtn) await click(submitBtn);
  check(
    "登录失败显示后端原因",
    (loginHost.textContent || "").includes("邮箱或密码不正确"),
    (loginHost.textContent || "").replace(/\s+/g, " ").slice(-70)
  );
  await act(async () => loginRoot.unmount());
  loginHost.remove();

  // === 用例 11：登录成功后跳回之前记住的目标路径 ===
  __resetNavigation("/login");
  sessionStorage.setItem("cet4_next_path", "/progress");
  (globalThis as any).fetch = async (input: any, init?: any) => {
    const url = typeof input === "string" ? input : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes("/api/auth/me")) return json({ detail: "未登录" }, 401);
    if (url.includes("/api/auth/csrf")) return json({ csrf_token: "t" });
    if (url.includes("/api/auth/login") && method === "POST") return json({ id: 1, email: "a@b.com", created_at: null });
    return json({});
  };
  const okHost = document.createElement("div");
  document.body.appendChild(okHost);
  const okRoot = createRoot(okHost);
  await act(async () => {
    okRoot.render(
      <ToastProvider>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
  });
  await setInput(okHost.querySelector('input[type="email"]') as HTMLInputElement, "a@b.com");
  await setInput(okHost.querySelector('input[type="password"]') as HTMLInputElement, "password123");
  const submit2 = submitOf(okHost);
  if (submit2) await click(submit2);
  const okCalls = __navigationCalls();
  check("登录后跳回原目标（且是最后一次跳转）", okCalls[okCalls.length - 1] === "replace:/progress", okCalls.join(" | "));
  check("跳转后清掉记住的路径", sessionStorage.getItem("cet4_next_path") === null, String(sessionStorage.getItem("cet4_next_path")));
  await act(async () => okRoot.unmount());
  okHost.remove();

  // === 用例 12：写请求必须带上 CSRF 头（前后端契约）===
  document.cookie = "cet4_csrf=test-token-abc";
  let starHeaders: Record<string, string> = {};
  (globalThis as any).fetch = async (input: any, init?: any) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/api/study/preview")) return json({ word_id: CARD.word.id, ratings: [] });
    if (url.includes("/api/starred")) {
      starHeaders = (init?.headers ?? {}) as Record<string, string>;
      return json({ message: "已添加" });
    }
    return json({});
  };
  const csrfHost = document.createElement("div");
  document.body.appendChild(csrfHost);
  const csrfRoot = createRoot(csrfHost);
  await act(async () => {
    csrfRoot.render(
      <ToastProvider>
        <AuthProvider>
          <FlashCard card={CARD} onRate={() => {}} />
        </AuthProvider>
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
  });
  await click(starButton(csrfHost));
  check(
    "写请求带 X-CSRF-Token 且与 cookie 一致",
    starHeaders["X-CSRF-Token"] === "test-token-abc",
    JSON.stringify(starHeaders)
  );
  await act(async () => csrfRoot.unmount());
  document.cookie = "cet4_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";

  // === 用例 13：学习计划页 —— 选目标/词书后保存，载荷正确且同步本机设置 ===
  let savedBody: any = null;
  const BOOKS = [
    { id: "exam_cet4", name: "四级考纲标注词", word_count: 3394, is_custom: false },
    { id: "exam_cet6", name: "六级拓展词", word_count: 3290, is_custom: false },
  ];
  const GOALS = [
    { goal_type: "cet4", name: "四级 CET-4", description: "大学英语四级", default_wordbook: "exam_cet4" },
    { goal_type: "cet6", name: "六级 CET-6", description: "大学英语六级", default_wordbook: "exam_cet6" },
  ];
  (globalThis as any).fetch = async (input: any, init?: any) => {
    const url = typeof input === "string" ? input : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes("/api/plan/options"))
      return json({ goals: GOALS, daily_new_words_range: { min: 1, max: 200 } });
    if (url.includes("/api/wordbooks")) return json(BOOKS);
    if (url.includes("/api/plan/forecast"))
      return json({
        has_plan: true,
        plan: null,
        wordbook: { key: "exam_cet6", name: "六级拓展词", total_words: 3290 },
        learned_words: 10,
        remaining_new_words: 3280,
        days_to_finish: 164,
        estimated_finish_date: "2027-04-01",
        target: null,
        due: {
          overdue: 0,
          today: 2,
          next_7_days: [{ date: "2026-10-19", count: 2 }],
          total_pending: 2,
          scope: "wordbook",
          as_of: "2026-10-19T00:00:00+00:00",
        },
        estimate_note: "估算不是保证",
        generated_at: "2026-10-19T00:00:00+00:00",
      });
    if (url.includes("/api/plan") && method === "PUT") {
      savedBody = JSON.parse(init.body);
      return json({ has_plan: true, plan: { ...savedBody, goal_name: "六级 CET-6", created_at: null, updated_at: null } });
    }
    if (url.includes("/api/plan")) return json({ has_plan: false, plan: null });
    return json({});
  };

  localStorage.removeItem("cet4_wordbook_id");
  const planHost = document.createElement("div");
  document.body.appendChild(planHost);
  const planRoot = createRoot(planHost);
  await act(async () => {
    planRoot.render(
      <ToastProvider>
        <PlanPage />
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

  const planText = () => (planHost.textContent || "").replace(/\s+/g, " ");
  check("计划页渲染学习目标", planText().includes("四级 CET-4") && planText().includes("六级 CET-6"), planText().slice(0, 80));
  check("计划页提示沿用了本机设置", planText().includes("本机原有的设置"), "");
  check("预测面板显示剩余新词与预计天数", planText().includes("3280") && planText().includes("164 天"), planText().slice(-90));

  const goalButtons = [...planHost.querySelectorAll("button[aria-pressed]")].filter((b) =>
    (b.textContent || "").includes("六级")
  );
  check("找到六级目标按钮", goalButtons.length === 1, String(goalButtons.length));
  if (goalButtons[0]) await click(goalButtons[0]);

  // 切目标后，词书应跟着换到该目标的默认词书
  const select = planHost.querySelector("select") as HTMLSelectElement;
  check("切目标后词书跟随默认值", select?.value === "exam_cet6", select?.value ?? "无 select");

  const saveBtn = [...planHost.querySelectorAll("button")].find((b) =>
    (b.textContent || "").includes("保存计划")
  );
  if (saveBtn) await click(saveBtn);
  check("保存请求载荷正确", savedBody?.goal_type === "cet6" && savedBody?.wordbook_key === "exam_cet6", JSON.stringify(savedBody));
  check("保存后同步本机词书（学习页跟随计划）", localStorage.getItem("cet4_wordbook_id") === "exam_cet6", String(localStorage.getItem("cet4_wordbook_id")));
  check("保存后提示已保存", planText().includes("计划已保存"), planText().slice(0, 60));

  // 关键验收：计划设成 25（非快捷选项）后，学习页必须按 25 取词 —— 两处数字必须一致
  const customInput = planHost.querySelector("#daily-new-words") as HTMLInputElement;
  check("计划页提供自定义数量输入", !!customInput, "");
  if (customInput) await setInput(customInput, "25");
  const saveBtn2 = [...planHost.querySelectorAll("button")].find((b) =>
    (b.textContent || "").includes("保存计划")
  );
  if (saveBtn2) await click(saveBtn2);
  check("自定义 25 写入服务端载荷", savedBody?.daily_new_words === 25, JSON.stringify(savedBody));
  check(
    "本机缓存同步为 25（不再被选项白名单丢弃）",
    localStorage.getItem("cet4_daily_goal") === "25",
    String(localStorage.getItem("cet4_daily_goal"))
  );
  await act(async () => planRoot.unmount());
  planHost.remove();

  let studyUrl = "";
  (globalThis as any).fetch = async (input: any) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/api/study/today")) {
      studyUrl = url;
      return json({ type: "new", words: [], total: 0 });
    }
    return json({});
  };
  const planStudyHost = document.createElement("div");
  document.body.appendChild(planStudyHost);
  const planStudyRoot = createRoot(planStudyHost);
  await act(async () => {
    planStudyRoot.render(
      <ToastProvider>
        <StudyPage />
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  check("学习页按计划里的 25 取词", studyUrl.includes("limit=25"), studyUrl);
  await act(async () => planStudyRoot.unmount());
  planStudyHost.remove();

  // === 用例 14：首页快捷按钮也要写回服务端（否则又是两处数字不一致）===
  const PLAN = {
    goal_type: "cet6",
    goal_name: "六级 CET-6",
    wordbook_key: "exam_cet6",
    target_date: "2027-01-01",
    daily_new_words: 20,
    created_at: null,
    updated_at: null,
  };
  let homeSaved: any = null;
  let homeSaveFails = false;
  (globalThis as any).fetch = async (input: any, init?: any) => {
    const url = typeof input === "string" ? input : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes("/api/auth/me")) return json({ id: 1, email: "a@b.com", created_at: null });
    if (url.includes("/api/progress/overview"))
      return json({ total_words: 100, learned_words: 5, known_words: 1, today_new: 2, today_reviewed: 0, streak_days: 3 });
    if (url.includes("/api/wordbooks"))
      return json({ id: "exam_cet6", name: "六级拓展词", word_count: 3290, is_custom: false });
    if (url.includes("/api/plan") && method === "PUT") {
      if (homeSaveFails) return json({ detail: "服务器开小差了" }, 500);
      homeSaved = JSON.parse(init.body);
      return json({ has_plan: true, plan: { ...PLAN, ...homeSaved } });
    }
    if (url.includes("/api/plan")) return json({ has_plan: true, plan: PLAN });
    return json({});
  };

  localStorage.setItem("cet4_daily_goal", "20");
  const homeHost = document.createElement("div");
  document.body.appendChild(homeHost);
  const homeRoot = createRoot(homeHost);
  await act(async () => {
    homeRoot.render(
      <ToastProvider>
        <AuthProvider>
          <HomePage />
        </AuthProvider>
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

  const goalBtn = (label: string) =>
    [...homeHost.querySelectorAll("button")].find((b) => (b.textContent || "").trim() === label);
  const btn50 = goalBtn("50");
  check("首页有 50 快捷按钮", !!btn50, "");
  if (btn50) await click(btn50);
  check(
    "首页改数量写回服务端并保留其他字段",
    homeSaved?.daily_new_words === 50 &&
      homeSaved?.goal_type === "cet6" &&
      homeSaved?.wordbook_key === "exam_cet6" &&
      homeSaved?.target_date === "2027-01-01",
    JSON.stringify(homeSaved)
  );
  check("首页本机缓存同步为 50", localStorage.getItem("cet4_daily_goal") === "50", String(localStorage.getItem("cet4_daily_goal")));

  // 服务端失败：必须明确报错，且不能把新值当成已保存
  homeSaveFails = true;
  const btn30 = goalBtn("30");
  if (btn30) await click(btn30);
  check(
    "保存失败时显示错误",
    (homeHost.textContent || "").includes("服务器开小差了"),
    (homeHost.textContent || "").replace(/\s+/g, " ").slice(-70)
  );
  check(
    "保存失败时数值未被改动（没伪装成已保存）",
    localStorage.getItem("cet4_daily_goal") === "50",
    String(localStorage.getItem("cet4_daily_goal"))
  );
  await act(async () => homeRoot.unmount());
  homeHost.remove();

  // === 用例 15：分级阅读完整流程（选文章 → 分词渲染 → 点词 → 答题 → 服务端判分结果）===
  const SUMMARY = {
    slug: "a1-my-morning-routine",
    title: "My Morning Routine",
    title_zh: "我的早晨习惯",
    level: "A1",
    topic: "日常生活",
    goals: ["general"],
    minutes: 3,
    word_count: 120,
    question_count: 2,
    source: "原创示例（非官方真题）",
  };
  const termOf = (id: number, headword: string, definition: string, status: string) => ({
    word_id: id,
    headword,
    definition,
    phonetic: "/x/",
    tags: "cet4",
    frq: 500,
    status,
    starred: false,
  });
  const TOKENS = [
    [
      { text: "I", index: 0, span_id: "ID-0-0", is_word: true, sentence: 0, paragraph: 0, status: "known", term: termOf(1, "I", "pron. 我", "known") },
      { text: " ", index: 1, span_id: "ID-0-1", is_word: false, sentence: 0, paragraph: 0, status: "unknown", term: null },
      { text: "drink", index: 2, span_id: "ID-0-2", is_word: true, sentence: 0, paragraph: 0, status: "learning", term: termOf(2, "drink", "v. 喝", "learning") },
      { text: " ", index: 3, span_id: "ID-0-3", is_word: false, sentence: 0, paragraph: 0, status: "unknown", term: null },
      { text: "zzz", index: 4, span_id: "ID-0-4", is_word: true, sentence: 0, paragraph: 0, status: "unknown", term: null },
      { text: ".", index: 5, span_id: "ID-0-5", is_word: false, sentence: 0, paragraph: 0, status: "unknown", term: null },
    ],
  ];
  const QUESTIONS = [
    { id: "q1", prompt: "What does the writer drink?", options: ["Tea", "Coffee"] },
    { id: "q2", prompt: "How does he go to school?", options: ["By bus", "By bike"] },
  ];
  let submitted: any = null;
  let lookupUrl = "";
  (globalThis as any).fetch = async (input: any, init?: any) => {
    const url = typeof input === "string" ? input : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes("/api/reading/articles/"))
      return json({
        article: {
          ...SUMMARY,
          paragraphs: [{ en: "I drink zzz.", zh: "我喝 zzz。" }],
          questions: QUESTIONS,
        },
        tokens: TOKENS,
      });
    if (url.includes("/api/reading/articles"))
      return json({ articles: [SUMMARY], total: 1, levels: ["A1", "A2", "B1"] });
    if (url.includes("/api/reading/lookup")) {
      lookupUrl = url;
      return json({ found: false, word: "zzz", message: "词库暂未收录该词，可先加入生词本稍后复习" });
    }
    if (url.includes("/api/reading/attempts") && method === "POST") {
      submitted = JSON.parse(init.body);
      return json({
        slug: SUMMARY.slug,
        title: SUMMARY.title,
        level: "A1",
        score: 1,
        total: 2,
        answered: 2,
        passed: false,
        duration_seconds: 42,
        completed_at: "2026-10-19T00:00:00+00:00",
        details: [
          { question_id: "q1", chosen: 0, correct_choice: 0, correct: true, explanation: "第一段说喝的是茶。" },
          { question_id: "q2", chosen: 1, correct_choice: 0, correct: false, explanation: "第三段说是坐公交车。" },
        ],
      });
    }
    if (url.includes("/api/reading/progress"))
      return json({
        total_articles: 1,
        completed_articles: 0,
        passed_articles: 0,
        completed_slugs: [],
        pass_ratio: 0.6,
        by_level: [{ level: "A1", total: 1, completed: 0 }],
        articles: [{ ...SUMMARY, attempts: 0, best_score: null, best_total: null, last_completed_at: null }],
        history: [],
      });
    return json({});
  };

  // jsdom 没实现 scrollTo，页面里会调用它，这里兜一下避免噪声
  (window as any).scrollTo = () => {};

  const readingHost = document.createElement("div");
  document.body.appendChild(readingHost);
  const readingRoot = createRoot(readingHost);
  await act(async () => {
    readingRoot.render(
      <ToastProvider>
        <ReadingPage />
      </ToastProvider>
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });

  const rdText = () => (readingHost.textContent || "").replace(/\s+/g, " ");
  check("阅读页显示文章列表", rdText().includes("My Morning Routine") && rdText().includes("A1"), rdText().slice(0, 90));
  check("阅读页显示难度筛选", rdText().includes("全部") && rdText().includes("入门 A1"), "");
  check("阅读页显示进度概览", rdText().includes("已读 0 / 1"), rdText().slice(-80));

  const articleBtn = [...readingHost.querySelectorAll("button")].find((b) =>
    (b.textContent || "").includes("My Morning Routine")
  );
  if (articleBtn) await click(articleBtn);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  check("进入阅读视图并渲染正文", rdText().includes("I drink zzz"), rdText().slice(0, 90));
  check("带出中英对照开关", rdText().includes("显示译文"), "");
  check("显示原创示例标注", rdText().includes("原创示例"), rdText().slice(-120));

  // 点词 → 弹窗给出释义与掌握状态
  const wordSpans = [...readingHost.querySelectorAll('span[role="button"]')];
  const drinkSpan = wordSpans.find((s) => (s.textContent || "") === "drink");
  check("正文里的词是可点击的分段项", !!drinkSpan, String(wordSpans.length));
  if (drinkSpan) await click(drinkSpan);
  check("点词弹出释义", rdText().includes("v. 喝"), rdText().slice(-120));
  check("弹窗显示掌握状态", rdText().includes("学习中"), "");
  check("命中词库的词不必再请求服务端", lookupUrl === "", lookupUrl);

  // 未收录词 → 明确反馈
  const zzzSpan = [...readingHost.querySelectorAll('span[role="button"]')].find(
    (s) => (s.textContent || "") === "zzz"
  );
  if (zzzSpan) await click(zzzSpan);
  await act(async () => {
    await Promise.resolve();
  });
  check("未收录词给出明确反馈", rdText().includes("词库暂未收录该词"), rdText().slice(-110));
  check("未收录词确实问了服务端", lookupUrl.includes("word=zzz"), lookupUrl);
  check("未收录词不能加入生词本", rdText().includes("无法加入生词本"), "");

  // 答题 → 提交（客户端不传分数）→ 服务端结果
  const optButtons = [...readingHost.querySelectorAll("button")].filter((b) =>
    /^[AB]\. /.test((b.textContent || "").trim())
  );
  check("渲染出选项按钮", optButtons.length === 4, String(optButtons.length));
  const tea = optButtons.find((b) => (b.textContent || "").includes("Tea"));
  const bike = optButtons.find((b) => (b.textContent || "").includes("By bike"));
  if (tea) await click(tea);
  if (bike) await click(bike);

  const submitReading = [...readingHost.querySelectorAll("button")].find((b) =>
    (b.textContent || "").includes("提交答案")
  );
  check(
    "有提交按钮且显示已答数量",
    !!submitReading && (submitReading.textContent || "").includes("2/2"),
    submitReading?.textContent ?? ""
  );
  if (submitReading) await click(submitReading);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

  check(
    "提交的是题号与选项，不含任何分数",
    submitted?.answers?.length === 2 &&
      submitted.answers.every((a: any) => typeof a.question_id === "string" && typeof a.choice === "number") &&
      submitted.score === undefined &&
      submitted.total === undefined,
    JSON.stringify(submitted)
  );
  check("显示服务端判分结果", rdText().includes("得分 1 / 2"), rdText().slice(0, 120));
  check("显示答案与解析", rdText().includes("第三段说是坐公交车"), "");
  check("标记是否通过", rdText().includes("再读一遍会更好"), "");
  await act(async () => readingRoot.unmount());
  readingHost.remove();

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