/** Local calendar day as YYYY-MM-DD (toISOString would shift by the UTC offset). */
export function isoDay(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Cells of a month grid: leading blanks up to the 1st's weekday, then each day
 *  as YYYY-MM-DD. `month` is 0-based, like Date. */
export function monthCells(year: number, month: number): (string | null)[] {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  return [
    ...Array<null>(new Date(year, month, 1).getDay()).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => isoDay(new Date(year, month, i + 1)))
  ];
}

/** Unclaiming is locked inside T-36h of the event start, and stays locked once
 *  the event has begun — the same rule tk_uncommit_task enforces (0142). */
export function isWithin36Hours(date: string, startTime: string, now: number = Date.now()): boolean {
  const start = new Date(`${date}T${(startTime || '00:00').substring(0, 5)}`).getTime();
  return start - now < 36 * 60 * 60 * 1000;
}

/** Money is integer cents end to end; this is the only place it becomes a string. */
export function formatMoney(cents: number): string {
  return '$' + (cents / 100).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}
