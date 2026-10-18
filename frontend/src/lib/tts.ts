/**
 * 单词发音 — 用浏览器内置 Web Speech API（零成本，无需后端）
 *
 * 失败要能被用户看见：朗读不可用（浏览器不支持、没有可用语音、被系统拦截）时，
 * 通过 TTS_ERROR_EVENT 上报，由 UI 层统一弹提示——原先只 console.warn，
 * 用户点了没声音会以为按钮坏了。
 */

/** 朗读失败事件名；UI 层（ToastProvider）监听并提示 */
export const TTS_ERROR_EVENT = "cet4:tts-error";

let cachedVoices: SpeechSynthesisVoice[] = [];

/** 加载英语语音列表（部分浏览器异步加载） */
function loadVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !window.speechSynthesis) return [];
  if (cachedVoices.length === 0) {
    cachedVoices = window.speechSynthesis.getVoices();
  }
  return cachedVoices;
}

/** 把失败原因广播出去（不依赖 React，避免 lib 反向依赖组件） */
function notifyFailure(reason: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(TTS_ERROR_EVENT, { detail: { reason } }));
}

if (typeof window !== "undefined" && window.speechSynthesis) {
  // 用 addEventListener 而不是 onvoiceschanged = ...：赋值会覆盖掉别处挂的处理器
  window.speechSynthesis.addEventListener?.("voiceschanged", () => {
    cachedVoices = window.speechSynthesis.getVoices();
  });
}

/**
 * 朗读英文文本
 * @param text 要朗读的英文（单词或句子）
 * @param rate 语速 0.5-2，默认 0.9（单词稍慢清晰）
 * @returns 是否成功发出朗读请求（失败时也已上报原因）
 */
export function speak(text: string, rate = 0.9): boolean {
  if (typeof window === "undefined" || !window.speechSynthesis) {
    notifyFailure("当前浏览器不支持语音合成");
    return false;
  }

  try {
    // 取消正在朗读的
    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-US";
    utter.rate = rate;
    utter.pitch = 1;

    // 优先选美式英语语音
    const voices = loadVoices();
    const usVoice =
      voices.find((v) => v.lang === "en-US") ||
      voices.find((v) => v.lang.startsWith("en"));
    if (usVoice) utter.voice = usVoice;

    // 朗读中途失败（无语音、被拦截）也要反馈，否则就是"点了没反应"
    utter.onerror = (event) => {
      const code = (event as SpeechSynthesisErrorEvent).error;
      notifyFailure(code ? `朗读失败（${code}）` : "朗读失败");
    };

    window.speechSynthesis.speak(utter);
    return true;
  } catch (err) {
    notifyFailure(err instanceof Error ? err.message : "朗读失败");
    return false;
  }
}

/** 是否支持语音合成 */
export function ttsAvailable(): boolean {
  return typeof window !== "undefined" && !!window.speechSynthesis;
}