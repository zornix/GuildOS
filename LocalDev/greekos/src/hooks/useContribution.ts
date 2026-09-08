import { useMemo } from 'react';
import type { ChapterEvent, Initiative } from '../types';
import { isoDay } from '../formatters';
import { ContributionSummary, upcomingContribution } from '../lib/contribution';

/** Personal contribution counts for the signed-in (or viewed-as) member.
 *  ponytail: upcoming-only, computed from loaded rows. Swap the body for
 *  api.getMyContribution() + an adapter when issue #40 lands; callers keep
 *  the same ContributionSummary. */
export function useContribution(
  memberName: string,
  events: ChapterEvent[],
  initiatives: Initiative[]
): ContributionSummary {
  return useMemo(
    () => upcomingContribution(memberName, events, initiatives, isoDay()),
    [memberName, events, initiatives]
  );
}
