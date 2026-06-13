"use client";
import { tokens } from "../../../config/theme/tokens";
import { Btn } from "../../ui/btn";

interface EventTabsProps {
  tab: "upcoming" | "past";
  onTabChange: (tab: "upcoming" | "past") => void;
}

export function EventTabs({ tab, onTabChange }: EventTabsProps) {
  return (
    <div style={{ display: "flex", gap: tokens.space[1], background: tokens.color.surface, borderRadius: tokens.radius.md, padding: 3, marginBottom: tokens.space[4], width: "fit-content" }}>
      {(["upcoming", "past"] as const).map((t) => (
        <Btn key={t} variant={tab === t ? "primary" : "ghost"} style={{ textTransform: "capitalize", padding: "6px 14px" }} onClick={() => onTabChange(t)}>
          {t}
        </Btn>
      ))}
    </div>
  );
}
