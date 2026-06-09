"use client";
import type { InputHTMLAttributes } from "react";
import { tokens } from "../../config/theme/tokens";

interface CodeInputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: string;
}

export function CodeInput({ error, style, ...props }: CodeInputProps) {
  return (
    <div style={{ marginBottom: tokens.space[2] }}>
      <input
        style={{
          width: "100%",
          padding: 14,
          borderRadius: tokens.radius.md,
          border: `1px solid ${error ? tokens.color.danger : tokens.color.border}`,
          background: tokens.color.bg,
          color: tokens.color.text,
          fontSize: 20,
          fontFamily: tokens.font.mono,
          textAlign: "center",
          letterSpacing: 4,
          boxSizing: "border-box",
          ...style,
        }}
        {...props}
      />
      {error && (
        <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginBottom: tokens.space[2], textAlign: "center" }}>
          {error}
        </div>
      )}
    </div>
  );
}
