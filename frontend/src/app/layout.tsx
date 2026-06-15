import type { Metadata, Viewport } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "腰子背单词 🌰",
  description: "AI 驱动的大学英语四级词汇学习工具",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    title: "腰子背单词",
    statusBarStyle: "default",
    capable: true,
  },
  icons: {
    icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icons/apple-icon.png", sizes: "180x180" }],
  },
};

// themeColor 必须放 viewport 导出（Next.js 14+ 废弃 metadata.themeColor）
// maximumScale=1 + userScalable=false：禁止缩放，更像原生 App
// viewportFit=cover：刘海屏铺满 + 配合安全区 env()
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAF8F5" },
    { media: "(prefers-color-scheme: dark)", color: "#1A1714" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // 防闪屏：SSR 阶段就根据 localStorage 设置 dark class
  const themeScript = `
    (function() {
      try {
        var t = localStorage.getItem('cet4_theme');
        if (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
          document.documentElement.classList.add('dark');
        }
      } catch(e) {}
    })();
  `;
  return (
    <html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full flex flex-col">
        <main className="flex-1 max-w-2xl mx-auto w-full px-4 py-6 pb-24 md:pb-8">
          {children}
        </main>
        <Navbar />
      </body>
    </html>
  );
}
