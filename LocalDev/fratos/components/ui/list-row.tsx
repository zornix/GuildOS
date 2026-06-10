"use client";
import type { CSSProperties, ReactNode } from "react";
import { tokens } from "../../config/theme/tokens";

interface ListRowProps {
  primary: ReactNode;
  secondary?: ReactNode;
  left?: ReactNode;
  right?: ReactNode;
  style?: CSSProperties;
}

export function ListRow({ primary, secondary, left, right, style }: ListRowProps) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: `${tokens.space[3]}px ${tokens.space[2] + 4}px`,
        borderRadius: tokens.radius.md,
        background: tokens.color.bg,
        ...style,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: tokens.space[3], flex: 1, minWidth: 0 }}>
        {left}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: tokens.font.sizeMd, fontWeight: tokens.font.weightMedium, color: tokens.color.text }}>
            {primary}
          </div>
          {secondary != null && (
            <div style={{ fontSize: tokens.font.sizeXs, color: tokens.color.textMuted, marginTop: 2 }}>
              {secondary}
            </div>
          )}
        </div>
      </div>
      {right != null && (
        <div style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
          {right}
        </div>
      )}
    </div>
  );
}
