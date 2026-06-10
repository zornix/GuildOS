"use client";
import { tokens } from "../../../config/theme/tokens";
import { AuthCard } from "./auth-card";

export function AuthLoading() {
  return (
    <AuthCard subtitle="Loading your workspace">
      <div style={{ display: "grid", gap: tokens.space[3] }}>
        <div style={{ height: 12, borderRadius: tokens.radius.pill, background: tokens.color.surfaceHover }} />
        <div style={{ height: 12, width: "72%", borderRadius: tokens.radius.pill, background: tokens.color.surfaceHover }} />
        <div style={{ height: 36, borderRadius: tokens.radius.md, background: tokens.color.bg, border: "1px solid " + tokens.color.border }} />
      </div>
    </AuthCard>
  );
}
