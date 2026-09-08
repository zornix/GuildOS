import type { Member } from '../types';

export type RollStatus = 'Present' | 'Absent' | 'Excused' | 'Late';

export interface RollCallSummary {
  present: number;
  absent: number;
  excused: number;
  late: number;
  unmarked: number;
  /** Only rows a human set, in roster order. This is what gets saved. */
  marked: { memberId: string; status: RollStatus }[];
  label: string;
}

/** Unmarked stays unmarked. Nothing is defaulted to Present here or anywhere. */
export function rollCallSummary(members: Member[], records: Record<string, RollStatus>): RollCallSummary {
  const counts = { present: 0, absent: 0, excused: 0, late: 0, unmarked: 0 };
  const marked: RollCallSummary['marked'] = [];
  for (const m of members) {
    const status = records[m.id];
    if (!status) { counts.unmarked++; continue; }
    counts[status.toLowerCase() as 'present' | 'absent' | 'excused' | 'late']++;
    marked.push({ memberId: m.id, status });
  }
  const parts = (['present', 'absent', 'excused', 'late', 'unmarked'] as const)
    .filter(k => counts[k] > 0)
    .map(k => `${counts[k]} ${k}`);
  return { ...counts, marked, label: parts.join(' · ') };
}

/** The explicit version of the old silent default: fills gaps, keeps choices. */
export function markRemainingPresent(members: Member[], records: Record<string, RollStatus>): Record<string, RollStatus> {
  const next: Record<string, RollStatus> = {};
  for (const m of members) next[m.id] = records[m.id] || 'Present';
  return next;
}
