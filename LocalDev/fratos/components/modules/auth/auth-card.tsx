"use client";
import type { ReactNode } from "react";
import { tokens } from "../../../config/theme/tokens";

interface AuthCardProps {
  subtitle: string;
  children: ReactNode;
}

export function AuthCard({ subtitle, children }: AuthCardProps) {
  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "100vh",
      background: tokens.color.bg,
      fontFamily: tokens.font.sans,
      padding: tokens.space[5],
    }}>
      <div style={{
        background: tokens.color.surface,
        borderRadius: tokens.radius.xl,
        padding: tokens.space[8],
        maxWidth: tokens.layout.authCardMaxWidth,
        width: "100%",
        border: `1px solid ${tokens.color.border}`,
      }}>
        <div style={{ textAlign: "center", marginBottom: tokens.space[6] }}>
          <div style={{ fontSize: 22, fontWeight: 800, color: tokens.color.text }}>
            <span style={{ color: tokens.color.accent }}>Fraternity</span>OS
          </div>
          <p style={{ color: tokens.color.textMuted, fontSize: 13, marginTop: 4 }}>{subtitle}</p>
        </div>
        {children}
      </div>
    </div>
  );
}
