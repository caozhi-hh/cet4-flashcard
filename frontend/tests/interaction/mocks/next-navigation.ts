/**
 * next/navigation 的最小替身（仅用于交互测试）
 *
 * 真实 useRouter/usePathname 依赖 Next 运行时上下文，在 jsdom 里不可用。
 * 这里记录跳转调用，供断言"登录守卫把用户送到了哪里"。
 */

let currentPath = "/";
const calls: string[] = [];
const listeners: Array<(path: string) => void> = [];

export function __setPathname(path: string): void {
  currentPath = path;
  listeners.forEach((fn) => fn(path));
}

export function __navigationCalls(): string[] {
  return [...calls];
}

export function __resetNavigation(path = "/"): void {
  calls.length = 0;
  currentPath = path;
}

function go(kind: string, path: string): void {
  calls.push(`${kind}:${path}`);
  __setPathname(path);
}

export function useRouter() {
  return {
    replace: (path: string) => go("replace", path),
    push: (path: string) => go("push", path),
    back: () => {},
    forward: () => {},
    refresh: () => {},
    prefetch: () => {},
  };
}

export function usePathname(): string {
  return currentPath;
}

export function useSearchParams(): URLSearchParams {
  return new URLSearchParams();
}

export function useParams(): Record<string, string> {
  return {};
}

export function redirect(): void {}
export function notFound(): never {
  throw new Error("notFound");
}