"use client";
import type { TextareaHTMLAttributes } from "react";
import { tokens } from "../../config/theme/tokens";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export function Textarea({ label, error, style, ...props }: TextareaProps) {
  return (
    <div style={{ marginBottom: tokens.space[2] }}>
      {label && (
        <label style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, display: "block", marginBottom: tokens.space[1] }}>
          {label}
        </label>
      )}
      <textarea
        style={{
          width: "100%",
          padding: tokens.space[3],
          borderRadius: tokens.radius.md,
          border: `1px solid ${error ? tokens.color.danger : tokens.color.border}`,
          background: tokens.color.bg,
          color: tokens.color.text,
          fontSize: tokens.font.sizeLg,
          resize: "vertical",
          boxSizing: "border-box",
          fontFamily: "inherit",
          ...style,
        }}
        {...props}
      />
      {error && (
        <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginTop: tokens.space[1] }}>
          {error}
        </div>
      )}
    </div>
  );
}
