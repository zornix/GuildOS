"use client";
import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { tokens } from "../../../config/theme/tokens";
import { Icon } from "../../ui/icon";
import { LoadingState } from "../../ui/loading-state";
import type { Event } from "../../../lib/types";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const MAX_CHIPS = 4;

/** Local YYYY-MM-DD key, avoiding UTC shift from toISOString(). */
function dayKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Parse an event's `YYYY-MM-DD` as a local date so it lands on the intended day. */
function parseEventDay(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : null;
}

/** "14:30" / "14:30:00" -> "2:30 PM". Falls back to the raw string. */
function formatTime(time: string): string {
  const match = /^(\d{1,2}):(\d{2})/.exec(time);
  if (!match) return time;
  let hour = Number(match[1]);
  const minute = match[2];
  const period = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${hour}:${minute} ${period}`;
}

interface CalendarCell {
  date: Date;
  key: string;
  inMonth: boolean;
  isToday: boolean;
  events: Event[];
}

interface EventCalendarProps {
  events: Event[];
  loading: boolean;
  error: string | null;
  onSelectEvent: (id: string) => void;
}

export function EventCalendar({ events, loading, error, onSelectEvent }: EventCalendarProps) {
  const todayKey = useMemo(() => dayKey(new Date()), []);
  // Anchor the visible month on the first day; default to the current month.
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const eventsByDay = useMemo(() => {
    const map = new Map<string, Event[]>();
    for (const event of events) {
      const key = parseEventDay(event.date);
      if (!key) continue;
      const bucket = map.get(key);
      if (bucket) bucket.push(event);
      else map.set(key, [event]);
    }
    for (const bucket of map.values()) {
      bucket.sort((a, b) => a.time.localeCompare(b.time));
    }
    return map;
  }, [events]);

  const cells = useMemo(() => {
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const firstWeekday = new Date(year, month, 1).getDay();
    const gridStart = new Date(year, month, 1 - firstWeekday);
    const result: CalendarCell[] = [];
    // 6 weeks covers every month layout without reflow between months.
    for (let i = 0; i < 42; i++) {
      const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
      const key = dayKey(date);
      result.push({
        date,
        key,
        inMonth: date.getMonth() === month,
        isToday: key === todayKey,
        events: eventsByDay.get(key) ?? [],
      });
    }
    return result;
  }, [cursor, eventsByDay, todayKey]);

  const monthEventCount = useMemo(
    () => cells.reduce((sum, cell) => sum + (cell.inMonth ? cell.events.length : 0), 0),
    [cells],
  );

  const goToMonth = (delta: number) =>
    setCursor((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1));
  const goToToday = () => {
    const now = new Date();
    setCursor(new Date(now.getFullYear(), now.getMonth(), 1));
  };

  if (loading && events.length === 0) {
    return <LoadingState message="Loading calendar…" />;
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: tokens.space[3], marginBottom: tokens.space[4], flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: tokens.space[3], minWidth: 0 }}>
          <h2 style={{ margin: 0, fontSize: tokens.font.size2xl, fontWeight: tokens.font.weightBold, color: tokens.color.text }}>
            {MONTHS[cursor.getMonth()]} {cursor.getFullYear()}
          </h2>
          <span style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>
            {monthEventCount === 0 ? "No events" : `${monthEventCount} event${monthEventCount === 1 ? "" : "s"}`}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: tokens.space[1] }}>
          <NavButton label="Previous month" onClick={() => goToMonth(-1)}>
            <span style={{ transform: "rotate(180deg)", display: "inline-flex" }}><Icon type="chev" size={16} /></span>
          </NavButton>
          <button
            type="button"
            onClick={goToToday}
            style={{
              padding: "6px 12px",
              borderRadius: tokens.radius.md,
              border: `1px solid ${tokens.color.border}`,
              background: tokens.color.surfaceHover,
              color: tokens.color.text,
              cursor: "pointer",
              fontSize: tokens.font.sizeSm,
              fontWeight: tokens.font.weightSemibold,
            }}
          >
            Today
          </button>
          <NavButton label="Next month" onClick={() => goToMonth(1)}>
            <Icon type="chev" size={16} />
          </NavButton>
        </div>
      </div>

      {error && (
        <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, marginBottom: tokens.space[3] }}>
          Events could not be loaded — the calendar may be incomplete. Use Retry above.
        </div>
      )}

      <div style={{ border: `1px solid ${tokens.color.border}`, borderRadius: tokens.radius.lg, overflow: "hidden", background: tokens.color.surface }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)" }}>
          {WEEKDAYS.map((day) => (
            <div
              key={day}
              style={{
                padding: `${tokens.space[2]} ${tokens.space[2]}`,
                textAlign: "center",
                fontSize: tokens.font.sizeXs,
                fontWeight: tokens.font.weightSemibold,
                letterSpacing: 0.6,
                textTransform: "uppercase",
                color: tokens.color.textMuted,
                borderBottom: `1px solid ${tokens.color.border}`,
              }}
            >
              {day}
            </div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)" }}>
          {cells.map((cell, index) => (
            <DayCell
              key={cell.key}
              cell={cell}
              isLastColumn={(index + 1) % 7 === 0}
              isLastRow={index >= 35}
              onSelectEvent={onSelectEvent}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function NavButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      style={{
        width: 32,
        height: 32,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: tokens.radius.md,
        border: `1px solid ${tokens.color.border}`,
        background: tokens.color.surfaceHover,
        color: tokens.color.text,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function DayCell({
  cell,
  isLastColumn,
  isLastRow,
  onSelectEvent,
}: {
  cell: CalendarCell;
  isLastColumn: boolean;
  isLastRow: boolean;
  onSelectEvent: (id: string) => void;
}) {
  const visible = cell.events.slice(0, MAX_CHIPS);
  const overflow = cell.events.length - visible.length;

  const cellStyle: CSSProperties = {
    minHeight: 104,
    padding: tokens.space[1],
    display: "flex",
    flexDirection: "column",
    gap: 3,
    borderRight: isLastColumn ? "none" : `1px solid ${tokens.color.border}`,
    borderBottom: isLastRow ? "none" : `1px solid ${tokens.color.border}`,
    background: cell.inMonth ? "transparent" : "rgba(0,0,0,0.18)",
    minWidth: 0,
  };

  return (
    <div style={cellStyle}>
      <div style={{ display: "flex", justifyContent: "flex-end", padding: "2px 4px 0" }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            minWidth: 20,
            height: 20,
            padding: "0 5px",
            borderRadius: tokens.radius.pill,
            fontSize: tokens.font.sizeSm,
            fontWeight: cell.isToday ? tokens.font.weightBold : tokens.font.weightMedium,
            background: cell.isToday ? tokens.color.accent : "transparent",
            color: cell.isToday ? "#fff" : cell.inMonth ? tokens.color.text : tokens.color.textMuted,
          }}
        >
          {cell.date.getDate()}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
        {visible.map((event) => (
          <EventChip key={event.id} event={event} onClick={() => onSelectEvent(event.id)} />
        ))}
        {overflow > 0 && (
          <span style={{ fontSize: tokens.font.sizeXs, color: tokens.color.textMuted, paddingLeft: 4 }}>
            +{overflow} more
          </span>
        )}
      </div>
    </div>
  );
}

function EventChip({ event, onClick }: { event: Event; onClick: () => void }) {
  const required = event.required;
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${event.title} · ${formatTime(event.time)} · ${event.location}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 4,
        width: "100%",
        textAlign: "left",
        padding: "3px 6px",
        borderRadius: tokens.radius.sm,
        border: "none",
        cursor: "pointer",
        fontSize: tokens.font.sizeXs,
        fontWeight: tokens.font.weightSemibold,
        background: required ? tokens.color.accent : tokens.color.surfaceHover,
        color: required ? "#fff" : tokens.color.text,
        minWidth: 0,
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          flexShrink: 0,
          background: required ? "#fff" : tokens.color.accentMuted,
        }}
      />
      <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>
        {event.title}
      </span>
    </button>
  );
}
