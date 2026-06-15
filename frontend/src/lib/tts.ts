/**
 * 单词发音 — 用浏览器内置 Web Speech API（零成本，无需后端）
 */

let cachedVoices: SpeechSynthesisVoice[] = [];

/** 加载英语语音列表（部分浏览器异步加载） */
function loadVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !window.speechSynthesis) return [];
  if (cachedVoices.length === 0) {
    cachedVoices = window.speechSynthesis.getVoices();
  }
  return cachedVoices;
}

if (typeof window !== "undefined" && window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {
    cachedVoices = window.speechSynthesis.getVoices();
  };
}

/**
 * 朗读英文文本
 * @param text 要朗读的英文（单词或句子）
 * @param rate 语速 0.5-2，默认 0.9（单词稍慢清晰）
 */
export function speak(text: string, rate = 0.9): void {
  if (typeof window === "undefined" || !window.speechSynthesis) {
    console.warn("当前浏览器不支持语音合成");
    return;
  }
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

  window.speechSynthesis.speak(utter);
}

/** 是否支持语音合成 */
export function ttsAvailable(): boolean {
  return typeof window !== "undefined" && !!window.speechSynthesis;
}
