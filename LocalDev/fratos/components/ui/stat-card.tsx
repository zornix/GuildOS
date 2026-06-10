"use client";
import { T } from "../../lib/theme";
import { Icon } from "./icon";
import { Card } from "./card";

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
          borderRadius: 10,
          background: color + "22",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color,
        }}
      >
        <Icon type={icon} />
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: T.tx }}>{value}</div>
        <div style={{ fontSize: 11, color: T.txm }}>{label}</div>
      </div>
    </Card>
  );
}
