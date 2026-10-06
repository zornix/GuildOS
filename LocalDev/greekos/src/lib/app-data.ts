import type { api, EventDto } from '../api';
import type { ChapterEvent, Member } from '../types';
import { adaptEvents, adaptUpcomingDetails } from '../adapters';

/** Startup enrichment always uses one bulk read, even for an empty list. */
export async function loadStartupEvents(
  eventRows: EventDto[], roster: Member[], calls: Pick<typeof api, 'getUpcomingEventDetails'>
): Promise<{ events: ChapterEvent[]; notice?: string; error?: unknown }> {
  const events = adaptEvents(eventRows);
  try {
    const { securityByEvent, detailByEvent } = adaptUpcomingDetails(
      await calls.getUpcomingEventDetails(), roster, new Map(roster.map(m => [m.id, m]))
    );
    return { events: events.map(e => ({
      ...e,
      ...(detailByEvent.get(e.id) || {}),
      securityAssignments: securityByEvent.get(e.id) || e.securityAssignments
    })) };
  } catch (error) {
    return { events, notice: 'Event details could not be loaded.', error };
  }
}

/** Job boards share one task read; only the affected event needs a detail read. */
export async function loadJobRefresh(
  calls: Pick<typeof api, 'getTasks' | 'getEvent'>, eventId?: string
) {
  const [tasks, event] = await Promise.allSettled([
    calls.getTasks(), eventId ? calls.getEvent(eventId) : undefined
  ]);
  if (tasks.status === 'rejected') console.error('Task refresh failed', tasks.reason);
  if (event.status === 'rejected') console.error('Event refresh failed', event.reason);
  return {
    taskRows: tasks.status === 'fulfilled' ? tasks.value : undefined,
    detail: event.status === 'fulfilled' ? event.value : undefined
  };
}
