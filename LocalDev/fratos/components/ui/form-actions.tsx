"use client";
import type { ReactNode, CSSProperties } from "react";
import { tokens } from "../../config/theme/tokens";

interface FormActionsProps {
  children: ReactNode;
  style?: CSSProperties;
}

export function FormActions({ children, style }: FormActionsProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: tokens.space[2],
        justifyContent: "flex-end",
        marginTop: tokens.space[2],
        ...style,
      }}
    >
      {children}
    </div>
  );
}
