"use client";

import { useEffect, useState } from "react";

const EMOJIS = ["🎉", "🎊", "✨", "🌟", "💫", "🍯", "🌸", "⭐", "🎈", "💖"];

interface Piece {
  id: number;
  emoji: string;
  left: number;
  delay: number;
  duration: number;
}

/**
 * 撒花动画 — 从顶部散落 emoji
 * 完成任务时触发，自动消失
 */
export default function Confetti() {
  const [pieces, setPieces] = useState<Piece[]>([]);

  useEffect(() => {
    const arr: Piece[] = Array.from({ length: 18 }, (_, i) => ({
      id: i,
      emoji: EMOJIS[i % EMOJIS.length],
      left: Math.random() * 100,
      delay: Math.random() * 0.8,
      duration: 1.8 + Math.random() * 1.2,
    }));
    setPieces(arr);
    const timer = setTimeout(() => setPieces([]), 3500);
    return () => clearTimeout(timer);
  }, []);

  if (pieces.length === 0) return null;

  return (
    <div className="fixed inset-0 pointer-events-none z-40 overflow-hidden">
      {pieces.map((p) => (
        <span
          key={p.id}
          className="absolute text-3xl animate-confetti"
          style={{
            left: `${p.left}%`,
            top: "-40px",
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        >
          {p.emoji}
        </span>
      ))}
    </div>
  );
}
