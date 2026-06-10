"use client";
import { tokens } from "../../../config/theme/tokens";
import { Card } from "../../ui/card";
import { Icon } from "../../ui/icon";
import { Badge } from "../../ui/badge";
import type { Event } from "../../../lib/types";

interface UpcomingEventsWidgetProps {
  events: Event[];
  loading: boolean;
  error: string | null;
}

export function UpcomingEventsWidget({ events, loading, error }: UpcomingEventsWidgetProps) {
  return (
    <Card>
      <div style={{ fontSize: tokens.font.sizeXl, fontWeight: tokens.font.weightBold, color: tokens.color.text, marginBottom: 14, display: "flex", alignItems: "center", gap: tokens.space[2] }}>
        <Icon type="cal" /> Upcoming
      </div>
      {loading && !events.length ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>Loading events…</div>
      ) : error ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>Could not load events. Use Retry above.</div>
      ) : events.length === 0 ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>No upcoming events</div>
      ) : (
        events.slice(0, 5).map((e) => (
          <div key={e.id} style={{ padding: "10px 12px", borderRadius: tokens.radius.md, background: tokens.color.bg, marginBottom: tokens.space[2], display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: tokens.font.sizeMd, fontWeight: 600, color: tokens.color.text }}>{e.title}</div>
              <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>{e.date} · {e.time}</div>
            </div>
            {e.required && <Badge color="purple">Required</Badge>}
          </div>
        ))
      )}
    </Card>
  );
}
