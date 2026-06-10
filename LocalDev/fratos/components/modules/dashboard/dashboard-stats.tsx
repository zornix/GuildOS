"use client";
import { StatCard } from "../../ui/stat-card";
import { tokens } from "../../../config/theme/tokens";

interface Stat {
  label: string;
  value: string;
  icon: string;
  color: string;
}

interface DashboardStatsProps {
  stats: Stat[];
}

export function DashboardStats({ stats }: DashboardStatsProps) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: `repeat(${stats.length}, 1fr)`,
      gap: tokens.space[4],
      marginBottom: tokens.space[6],
    }}>
      {stats.map((s, i) => (
        <StatCard key={i} label={s.label} value={s.value} icon={s.icon} color={s.color} />
      ))}
    </div>
  );
}
