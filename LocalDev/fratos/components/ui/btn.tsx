"use client";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

type BtnVariant = "primary" | "danger" | "success" | "ghost";

const VARIANT_STYLES: Record<BtnVariant, Record<string, string>> = {
  primary: { background: tokens.color.accent, color: "#fff" },
  danger: { background: tokens.color.danger, color: "#fff" },
  success: { background: tokens.color.success, color: "#fff" },
  ghost: { background: tokens.color.surfaceHover, color: tokens.color.text, border: `1px solid ${tokens.color.border}` },
};

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: BtnVariant;
}

export function Btn({ children, variant = "primary", style = {}, ...props }: BtnProps) {
  return (
    <button
      style={{
        padding: `${tokens.space[2]} ${tokens.space[4]}`,
        borderRadius: tokens.radius.md,
        border: "none",
        cursor: "pointer",
        fontWeight: 600,
        fontSize: tokens.font.sizeMd,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        transition: `opacity ${tokens.transition.fast}`,
        ...VARIANT_STYLES[variant],
        ...style,
      }}
      {...props}
    >
      {children}
    </button>
  );
}
