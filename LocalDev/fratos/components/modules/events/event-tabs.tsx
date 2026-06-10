"use client";
import { tokens } from "../../../config/theme/tokens";
import { Btn } from "../../ui/btn";
import { Icon } from "../../ui/icon";

interface EventTabsProps {
  tab: "upcoming" | "past";
  onTabChange: (tab: "upcoming" | "past") => void;
  isOfficer: boolean;
  onCreateEvent: () => void;
}

export function EventTabs({ tab, onTabChange, isOfficer, onCreateEvent }: EventTabsProps) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: tokens.space[4] }}>
      <div style={{ display: "flex", gap: tokens.space[1], background: tokens.color.surface, borderRadius: tokens.radius.md, padding: 3 }}>
        {(["upcoming", "past"] as const).map((t) => (
          <Btn key={t} variant={tab === t ? "primary" : "ghost"} style={{ textTransform: "capitalize", padding: "6px 14px" }} onClick={() => onTabChange(t)}>
            {t}
          </Btn>
        ))}
      </div>
      {isOfficer && (
        <Btn onClick={onCreateEvent}><Icon type="plus" size={14} /> New Event</Btn>
      )}
    </div>
  );
}
