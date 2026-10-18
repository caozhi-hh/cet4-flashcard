/**
 * 交互测试的 jsdom 引导脚本
 *
 * 必须在导入被测组件之前建立浏览器全局（React DOM 在模块求值时就会读 document）。
 * 用法：node tests/interaction/run.mjs
 */

import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "https://example.com/",
  pretendToBeVisual: true,
});

// Node 21+ 的 globalThis.navigator 是只读 getter，必须用 defineProperty 覆盖
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.window = dom.window;
// 浏览器里 self === window；组件/第三方代码会用裸 self 取 requestIdleCallback 等
globalThis.self = dom.window;
globalThis.document = dom.window.document;
globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
// localStorage 只挂在 window 上，组件里直接用的全局未必存在
if (dom.window.localStorage) globalThis.localStorage = dom.window.localStorage;
if (dom.window.sessionStorage) globalThis.sessionStorage = dom.window.sessionStorage;

// 把 jsdom 提供的浏览器类搬到 global 上（Radix 会用到 MutationObserver 做滚动锁/FocusScope）。
// 必须**强制覆盖**而不是"缺失才补"：Node 24 自带 Event/CustomEvent/EventTarget，
// 但它们和 jsdom 不是同一个 realm，jsdom 的 dispatchEvent 会以"参数不是 Event"拒绝。
for (const key of [
  "EventTarget",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLButtonElement",
  "Element",
  "Node",
  "DocumentFragment",
  "Event",
  "CustomEvent",
  "MouseEvent",
  "PointerEvent",
  "KeyboardEvent",
  "FocusEvent",
  "InputEvent",
  "MutationObserver",
  "NodeFilter",
  "TreeWalker",
  "DOMRect",
  "Range",
  "Selection",
  "SVGElement",
]) {
  if (dom.window[key]) globalThis[key] = dom.window[key];
}

for (const fn of ["requestIdleCallback", "cancelIdleCallback", "requestAnimationFrame", "cancelAnimationFrame"]) {
  if (typeof dom.window[fn] === "function") globalThis[fn] = dom.window[fn].bind(dom.window);
}

// Radix 的 Toast/Dialog 会用到这些 jsdom 没有的 API
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub;
dom.window.ResizeObserver = ResizeObserverStub;
dom.window.matchMedia = (query) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
  dispatchEvent: () => false,
});
globalThis.matchMedia = dom.window.matchMedia;

// React 19 的 act 需要这个标记，否则会告警并且不 flush 副作用
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

await import("./.tmp/toast.test.js");