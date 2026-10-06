import type { ChapterEvent } from '../types';

/** Chips on the Events bar. 'All' first; the rest are the types officers
 *  actually schedule (Recruitment and Community Service exist but are rare). */
export const EVENT_FILTER_TYPES = [
  'All', 'Chapter Meeting', 'Philanthropy', 'Brotherhood', 'Social', 'Pledge Education'
] as const;

export function filterEventsByType(events: ChapterEvent[], type: string): ChapterEvent[] {
  return type === 'All' ? events : events.filter(e => e.type === type);
}

/** The event a member can check into right now: earliest upcoming event whose
 *  door code is open. `today` is YYYY-MM-DD. */
export function liveDoorEvent(events: ChapterEvent[], today: string): ChapterEvent | undefined {
  return events
    .filter(e => e.checkInLinkActive && e.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date) || a.startTime.localeCompare(b.startTime))[0];
}

/** DELETE /api/events/{id}: an event with attendance, jobs or fines is
 *  cancelled instead of deleted (decision D4); either way it leaves the list. */
export function eventDeleteMessage(result: { deleted: boolean; cancelled: boolean }): string {
  return result.cancelled ? 'Event cancelled. Its attendance and fines were kept.' : 'Event deleted.';
}
