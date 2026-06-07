"use client";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { T } from "../../lib/theme";

type BtnVariant = "primary" | "danger" | "success" | "ghost";

const VARIANT_STYLES: Record<BtnVariant, Record<string, string>> = {
  primary: { background: T.ac, color: "#fff" },
  danger: { background: T.err, color: "#fff" },
  success: { background: T.ok, color: "#fff" },
  ghost: { background: T.sfh, color: T.tx, border: `1px solid ${T.bd}` },
};

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: BtnVariant;
}

export function Btn({ children, variant = "primary", style = {}, ...props }: BtnProps) {
  return (
    <button
      style={{
        padding: "8px 16px",
        borderRadius: 8,
        border: "none",
        cursor: "pointer",
        fontWeight: 600,
        fontSize: 13,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        transition: "opacity 0.2s",
        ...VARIANT_STYLES[variant],
        ...style,
      }}
      {...props}
    >
      {children}
    </button>
  );
}
