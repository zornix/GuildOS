"use client";
import { tokens } from "../../../config/theme/tokens";
import { LoadingState } from "../../ui/loading-state";
import { EmptyState } from "../../ui/empty-state";
import { EventRow } from "./event-row";
import type { Event } from "../../../lib/types";

interface EventListProps {
  events: Event[];
  loading: boolean;
  error: string | null;
  tab: "upcoming" | "past";
  onSelectEvent: (id: string) => void;
}

export function EventList({ events, loading, error, tab, onSelectEvent }: EventListProps) {
  if (loading && !events.length) {
    return <LoadingState message="Loading events…" />;
  }

  if (events.length === 0) {
    return (
      <EmptyState message={error ? `Could not load events (${tab}). Use Retry above.` : `No ${tab} events`} />
    );
  }

  return (
    <div style={{ display: "grid", gap: tokens.space[2] }}>
      {events.map((e) => (
        <EventRow key={e.id} event={e} onClick={() => onSelectEvent(e.id)} />
      ))}
    </div>
  );
}
