import type { Event } from "./types";

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

function eventTimestamp(event: Pick<Event, "date" | "time">): number {
  const withTime = Date.parse(`${event.date}T${event.time}`);
  if (!Number.isNaN(withTime)) return withTime;
  return Date.parse(event.date);
}

export function isPastEvent(event: Pick<Event, "date" | "time">, reference: Date = new Date()): boolean {
  return eventTimestamp(event) < reference.getTime() - ONE_DAY_MS;
}

export function isUpcomingEvent(event: Pick<Event, "date" | "time">, reference: Date = new Date()): boolean {
  return !isPastEvent(event, reference);
}
