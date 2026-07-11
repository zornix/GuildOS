"use client";
import { tokens } from "../../../config/theme/tokens";
import { Card } from "../../ui/card";
import { Badge } from "../../ui/badge";
import { Icon } from "../../ui/icon";
import type { Event } from "../../../lib/types";
import { formatMoney } from "../../../lib/formatters/money";
import { eventFineAmountCents } from "../../../lib/adapters/events";

interface EventRowProps {
  event: Event;
  onClick: () => void;
}

export function EventRow({ event, onClick }: EventRowProps) {
  return (
    <Card onClick={onClick} style={{ padding: tokens.space[4], display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}>
      <div>
        <div style={{ fontSize: tokens.font.sizeLg, fontWeight: tokens.font.weightBold, color: tokens.color.text }}>{event.title}</div>
        <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, marginTop: 2 }}>{event.date} at {event.time} · {event.location}</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
        {event.required && <Badge color="purple">Required</Badge>}
        {/* fine_amount is legacy float dollars; eventFineAmountCents owns the float→cents boundary */}
        {event.fine_amount > 0 && <Badge color="red">{formatMoney(eventFineAmountCents(event))}</Badge>}
        <span style={{ color: tokens.color.textMuted }}><Icon type="chev" size={14} /></span>
      </div>
    </Card>
  );
}
