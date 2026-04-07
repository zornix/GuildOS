"use client";
import { T } from "../../lib/theme";

interface ToastProps {
  msg: string | null;
}

export function Toast({ msg }: ToastProps) {
  if (!msg) return null;
  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        left: "50%",
        transform: "translateX(-50%)",
        background: T.ok,
        color: "#fff",
        padding: "10px 24px",
        borderRadius: 10,
        fontSize: 13,
        fontWeight: 600,
        boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
        zIndex: 9999,
      }}
    >
      {msg}
    </div>
  );
}
