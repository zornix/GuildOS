/** A member's own contribution record, as GET /api/contribution/me derives it:
 *  structurally-known, positive-only facts. Shown to the member themself (and
 *  officers) — never ranked against anyone, never a standing input (ADR-0004). */
export interface ContributionEvent {
  eventId: string;
  title: string;
  date: string;
  attendeeCount: number;
}

export interface ContributionInitiative {
  initiativeId: string;
  title: string;
  start: string;
  end: string | null;
}

export interface ContributionJob {
  jobId: string;
  title: string;
  attachedTo: 'event' | 'initiative' | 'standalone';
  date: string;
}

export interface ContributionRecord {
  eventsOrganized: ContributionEvent[];
  eventsSupervised: ContributionEvent[];
  initiativesChaired: ContributionInitiative[];
  jobsDone: ContributionJob[];
  eventsAttendedCount: number;
}

export const EMPTY_CONTRIBUTION: ContributionRecord = {
  eventsOrganized: [],
  eventsSupervised: [],
  initiativesChaired: [],
  jobsDone: [],
  eventsAttendedCount: 0
};

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`;

/** The copy-to-clipboard résumé line, e.g. "Organized 12 events with 340 total
 *  attendees, chaired 2 initiatives, completed 9 jobs." Zero counts are left
 *  out rather than printed as zeros. */
export function resumeLine(record: ContributionRecord): string {
  const attendees = record.eventsOrganized.reduce((sum, e) => sum + e.attendeeCount, 0);
  const parts = [
    record.eventsOrganized.length &&
      `organized ${plural(record.eventsOrganized.length, 'event')}` +
        (attendees ? ` with ${plural(attendees, 'total attendee')}` : ''),
    record.eventsSupervised.length &&
      `supervised ${plural(record.eventsSupervised.length, 'event')}`,
    record.initiativesChaired.length &&
      `chaired ${plural(record.initiativesChaired.length, 'initiative')}`,
    record.jobsDone.length && `completed ${plural(record.jobsDone.length, 'job')}`,
    record.eventsAttendedCount && `attended ${plural(record.eventsAttendedCount, 'event')}`
  ].filter((p): p is string => typeof p === 'string');

  if (!parts.length) return 'No chapter record yet.';
  const line = parts.join(', ');
  return `${line[0].toUpperCase()}${line.slice(1)}.`;
}

/** "2026-04-01 – 2026-04-05", or just the start when there is no end. */
export function dateRangeLabel(initiative: ContributionInitiative): string {
  return initiative.end && initiative.end !== initiative.start
    ? `${initiative.start} – ${initiative.end}`
    : initiative.start;
}
