"use client";
import type { InputHTMLAttributes } from "react";
import { tokens } from "../../config/theme/tokens";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, ...props }: InputProps) {
  return (
    <div style={{ marginBottom: tokens.space[3] }}>
      {label && <label style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, display: "block", marginBottom: tokens.space[1] }}>{label}</label>}
      <input
        style={{
          width: "100%",
          padding: `${tokens.space[2]} ${tokens.space[3]}`,
          borderRadius: tokens.radius.md,
          border: `1px solid ${tokens.color.border}`,
          background: tokens.color.bg,
          color: tokens.color.text,
          fontSize: tokens.font.sizeLg,
          boxSizing: "border-box",
        }}
        {...props}
      />
    </div>
  );
}
