"use client";
import type { CSSProperties, ReactNode } from "react";
import { T } from "../../lib/theme";

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
        background: T.sf,
        borderRadius: 12,
        border: `1px solid ${T.bd}`,
        padding: 20,
        transition: "border-color 0.2s",
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
