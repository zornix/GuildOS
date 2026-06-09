"use client";
import { tokens } from "../../config/theme/tokens";

interface ToastProps {
  msg: string | null;
}

export function Toast({ msg }: ToastProps) {
  if (!msg) return null;
  return (
    <div
      style={{
        position: "fixed",
        bottom: tokens.space[6],
        left: "50%",
        transform: "translateX(-50%)",
        background: tokens.color.success,
        color: "#fff",
        padding: `10px ${tokens.space[6]}`,
        borderRadius: tokens.radius.lg,
        fontSize: tokens.font.sizeMd,
        fontWeight: 600,
        boxShadow: tokens.shadow.toast,
        zIndex: 9999,
      }}
    >
      {msg}
    </div>
  );
}
