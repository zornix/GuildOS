import { useState } from 'react';
import { ContributionRecord, EMPTY_CONTRIBUTION } from '../lib/contribution';

/** The signed-in member's contribution record, loaded once by useAppData from
 *  GET /api/contribution/me. Lifetime counts are the server's to derive — the
 *  UI never recomputes them from whatever rows happen to be loaded. */
export function useContribution() {
  const [record, setRecord] = useState<ContributionRecord>(EMPTY_CONTRIBUTION);
  return { record, setRecord };
}
