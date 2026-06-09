"use client";
import type { ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

interface ModalProps {
  children: ReactNode;
  onClose: () => void;
}

export function Modal({ children, onClose }: ModalProps) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: tokens.color.overlay,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 999,
        backdropFilter: "blur(4px)",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: tokens.color.surface,
          borderRadius: tokens.radius.xl,
          padding: tokens.space[6],
          maxWidth: tokens.layout.modalMaxWidth,
          width: "90%",
          border: `1px solid ${tokens.color.border}`,
          maxHeight: "85vh",
          overflowY: "auto",
        }}
      >
        {children}
      </div>
    </div>
  );
}
