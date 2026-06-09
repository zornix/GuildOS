"use client";
import type { ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

type BadgeColor = "green" | "red" | "yellow" | "blue" | "purple" | "gray";

const COLOR_MAP: Record<BadgeColor, [string, string]> = {
  green: ["#10b98122", "#059669"],
  red: ["#ef444422", "#dc2626"],
  yellow: ["#f59e0b22", "#b45309"],
  blue: ["#3b82f622", "#2563eb"],
  purple: ["#6c5ce722", tokens.color.accentMuted],
  gray: [tokens.color.border, tokens.color.textMuted],
};

interface BadgeProps {
  children: ReactNode;
  color?: BadgeColor;
}

export function Badge({ children, color = "gray" }: BadgeProps) {
  const [bg, tx] = COLOR_MAP[color];
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: tokens.radius.pill,
        fontSize: tokens.font.sizeSm,
        fontWeight: 600,
        background: bg,
        color: tx,
        textTransform: "uppercase",
        letterSpacing: 0.5,
      }}
    >
      {children}
    </span>
  );
}
