"use client";
import type { InputHTMLAttributes } from "react";
import { T } from "../../lib/theme";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, ...props }: InputProps) {
  return (
    <div style={{ marginBottom: 12 }}>
      {label && <label style={{ fontSize: 12, color: T.txm, display: "block", marginBottom: 4 }}>{label}</label>}
      <input
        style={{
          width: "100%",
          padding: "8px 12px",
          borderRadius: 8,
          border: `1px solid ${T.bd}`,
          background: T.bg,
          color: T.tx,
          fontSize: 14,
          boxSizing: "border-box",
        }}
        {...props}
      />
    </div>
  );
}
