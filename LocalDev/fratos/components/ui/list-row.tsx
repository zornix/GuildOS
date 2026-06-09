"use client";
import type { ReactNode, CSSProperties } from "react";
import { tokens } from "../../config/theme/tokens";

interface ListRowProps {
  primary: string;
  secondary?: string;
  left?: ReactNode;
  right?: ReactNode;
  style?: CSSProperties;
}

export function ListRow({ primary, secondary, left, right, style }: ListRowProps) {
  return (
    <div style={{
      padding: `${tokens.space[2]} ${tokens.space[3]}`,
      borderRadius: tokens.radius.md,
      background: tokens.color.bg,
      marginBottom: tokens.space[2],
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      ...style,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
        {left}
        <div>
          <div style={{ fontSize: tokens.font.sizeMd, fontWeight: 600, color: tokens.color.text }}>{primary}</div>
          {secondary && <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>{secondary}</div>}
        </div>
      </div>
      {right && <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>{right}</div>}
    </div>
  );
}
