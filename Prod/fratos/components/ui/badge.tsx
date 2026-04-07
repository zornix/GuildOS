"use client";
import type { ReactNode } from "react";
import { T } from "../../lib/theme";

type BadgeColor = "green" | "red" | "yellow" | "blue" | "purple" | "gray";

const COLOR_MAP: Record<BadgeColor, [string, string]> = {
  green: [T.ok + "22", "#059669"],
  red: [T.err + "22", "#dc2626"],
  yellow: [T.warn + "22", "#b45309"],
  blue: ["#3b82f622", "#2563eb"],
  purple: [T.ac + "22", T.acl],
  gray: [T.bd, T.txm],
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
        borderRadius: 999,
        fontSize: 11,
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
