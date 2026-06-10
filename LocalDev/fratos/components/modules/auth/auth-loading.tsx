"use client";
import { tokens } from "../../../config/theme/tokens";

export function AuthLoading() {
  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      height: "100vh",
      background: tokens.color.bg,
      color: tokens.color.textMuted,
    }}>
      Loading...
    </div>
  );
}
