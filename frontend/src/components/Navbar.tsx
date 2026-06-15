"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getTheme, toggleTheme, initTheme, onThemeChange, type Theme } from "@/lib/theme";

const NAV_ITEMS = [
  { href: "/", label: "首页", icon: "🏠" },
  { href: "/study", label: "学习", icon: "📖" },
  { href: "/starred", label: "生词", icon: "📝" },
  { href: "/quiz", label: "测验", icon: "✏️" },
  { href: "/progress", label: "进度", icon: "📊" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    initTheme();
    setTheme(getTheme());
    setMounted(true);
    const unsub = onThemeChange(() => setTheme(getTheme()));
    return unsub;
  }, []);

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-milk/90 backdrop-blur-md border-t border-honey md:relative md:border-t-0 md:border-b">
      <div className="max-w-2xl mx-auto flex justify-around items-center h-14 md:h-12 px-2 relative">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col md:flex-row items-center gap-0.5 md:gap-1.5 px-3 md:px-4 py-1.5 text-xs md:text-sm transition-colors ${
                active
                  ? "text-caramel font-semibold"
                  : "text-cocoa-soft hover:text-cocoa"
              }`}
            >
              <span className="text-base md:text-lg">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}

        {/* 主题切换 */}
        {mounted && (
          <button
            onClick={() => toggleTheme()}
            className="absolute top-1 right-2 md:top-1.5 md:right-2 w-8 h-8 flex items-center justify-center text-sm rounded-lg text-cocoa-soft hover:text-cocoa hover:bg-cream-deep transition-colors active:scale-90"
            title={theme === "dark" ? "切换亮色" : "切换暗色"}
            aria-label="切换主题"
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
        )}
      </div>
    </nav>
  );
}
