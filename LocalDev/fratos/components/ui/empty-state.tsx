"use client";
import type { ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

interface EmptyStateProps {
  message: string;
  children?: ReactNode;
}

export function EmptyState({ message, children }: EmptyStateProps) {
  return (
    <div style={{
      background: tokens.color.surface,
      borderRadius: tokens.radius.lg,
      border: `1px solid ${tokens.color.border}`,
      padding: tokens.space[10],
      textAlign: "center",
      color: tokens.color.textMuted,
    }}>
      <div style={{ fontSize: tokens.font.sizeMd }}>{message}</div>
      {children}
    </div>
  );
}
