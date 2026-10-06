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

/** Roving radio keys for one member's row: Right/Down select the next option,
 *  Left/Up the previous, wrapping. An unmarked row lands on the first option.
 *  Any other key: null (let it through). */
export function nextStatus<T extends string>(current: T | undefined, key: string, options: readonly T[]): T | null {
  const step = key === 'ArrowRight' || key === 'ArrowDown' ? 1 : key === 'ArrowLeft' || key === 'ArrowUp' ? -1 : 0;
  if (!step) return null;
  const at = current ? options.indexOf(current) : -1;
  if (at < 0) return options[0];
  return options[(at + step + options.length) % options.length];
}
