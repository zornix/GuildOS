"use client";
import type { CSSProperties, ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

interface CardProps {
  children: ReactNode;
  style?: CSSProperties;
  onClick?: () => void;
}

export function Card({ children, style = {}, onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      style={{
        background: tokens.color.surface,
        borderRadius: tokens.radius.lg,
        border: `1px solid ${tokens.color.border}`,
        padding: tokens.space[5],
        transition: `border-color ${tokens.transition.fast}`,
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
