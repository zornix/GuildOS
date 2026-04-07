"use client";
import type { ReactNode } from "react";
import { T } from "../../lib/theme";

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
        background: "rgba(0,0,0,0.6)",
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
          background: T.sf,
          borderRadius: 16,
          padding: 24,
          maxWidth: 440,
          width: "90%",
          border: `1px solid ${T.bd}`,
          maxHeight: "85vh",
          overflowY: "auto",
        }}
      >
        {children}
      </div>
    </div>
  );
}
