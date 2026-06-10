"use client";
import { tokens } from "../../config/theme/tokens";
import { Card } from "./card";
import { Icon } from "./icon";

interface StatCardProps {
  label: string;
  value: string;
  icon: string;
  color: string;
}

export function StatCard({ label, value, icon, color }: StatCardProps) {
  return (
    <Card style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <div
        style={{
          width: 42,
          height: 42,
          borderRadius: tokens.radius.lg,
          background: color + "22",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color,
          flexShrink: 0,
        }}
      >
        <Icon type={icon} />
      </div>
      <div>
        <div style={{ fontSize: tokens.font.size2xl, fontWeight: tokens.font.weightBold, color: tokens.color.text }}>
          {value}
        </div>
        <div style={{ fontSize: tokens.font.sizeXs, color: tokens.color.textMuted }}>
          {label}
        </div>
      </div>
    </Card>
  );
}
