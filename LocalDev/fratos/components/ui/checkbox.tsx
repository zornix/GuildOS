"use client";
import type { InputHTMLAttributes, ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: ReactNode;
}

export function Checkbox({ label, style, ...props }: CheckboxProps) {
  return (
    <label
      style={{
        display: "flex",
        alignItems: "center",
        gap: tokens.space[2],
        fontSize: tokens.font.sizeMd,
        color: tokens.color.text,
        marginBottom: tokens.space[4],
        cursor: "pointer",
        ...style,
      }}
    >
      <input type="checkbox" {...props} />
      {label}
    </label>
  );
}
