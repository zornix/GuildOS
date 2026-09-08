import type { ChapterEvent, Initiative } from '../types';

/** A member's own contribution numbers. `scope` says how far they reach:
 *  'upcoming' is computed client-side from loaded events; 'lifetime' will come
 *  from GET /api/contribution/me (issue #40). Never rendered as a ranking. */
export interface ContributionSummary {
  scope: 'upcoming' | 'lifetime';
  eventsOrganized: number;
  eventsSupervised: number;
  initiativesChaired: number;
}

/** Upcoming = on or after `today` (YYYY-MM-DD). Names are matched exactly
 *  because the event detail rows carry names, not ids. */
export function upcomingContribution(
  memberName: string,
  events: ChapterEvent[],
  initiatives: Initiative[],
  today: string
): ContributionSummary {
  const me = memberName.trim();
  const has = (names: string[] | undefined) => !!me && (names || []).includes(me);
  const upcoming = events.filter(e => e.date >= today);
  const open = initiatives.filter(i => (i.targetDate || i.startDate) >= today);
  return {
    scope: 'upcoming',
    eventsOrganized: upcoming.filter(e => has(e.organizers)).length,
    eventsSupervised: upcoming.filter(e => has(e.supervisors)).length,
    initiativesChaired: open.filter(i => has(i.leadChairs)).length
  };
}
