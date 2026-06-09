"use client";
import { tokens } from "../../config/theme/tokens";
import { Icon } from "./icon";

interface StatCardProps {
  label: string;
  value: string;
  icon: string;
  color: string;
}

export function StatCard({ label, value, icon, color }: StatCardProps) {
  return (
    <div style={{
      background: tokens.color.surface,
      borderRadius: tokens.radius.lg,
      border: `1px solid ${tokens.color.border}`,
      padding: tokens.space[5],
      display: "flex",
      alignItems: "center",
      gap: 14,
    }}>
      <div style={{
        width: tokens.layout.statIconSize,
        height: tokens.layout.statIconSize,
        borderRadius: tokens.radius.lg,
        background: color + "22",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color,
        flexShrink: 0,
      }}>
        <Icon type={icon} />
      </div>
      <div>
        <div style={{ fontSize: tokens.font.size3xl, fontWeight: 700, color: tokens.color.text }}>{value}</div>
        <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>{label}</div>
      </div>
    </div>
  );
}
