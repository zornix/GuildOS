"use client";
import { tokens } from "../../config/theme/tokens";

interface LoadingStateProps {
  message?: string;
}

export function LoadingState({ message = "Loading…" }: LoadingStateProps) {
  return (
    <div style={{ color: tokens.color.textMuted, textAlign: "center", padding: tokens.space[10] }}>
      {message}
    </div>
  );
}
