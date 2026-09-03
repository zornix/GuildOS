import { isoDay } from '../formatters';

// The console's schedule command carries a date and a time in plain English.
// This resolves both, or refuses — it never guesses a day the user didn't type.

const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december'];

const clean = (s: string) => s.trim().toLowerCase().replace(/[.,!]+$/, '');

/** Prefix match, so "fri" and "friday" both land — 3 letters minimum to stay unambiguous. */
const nameIndex = (names: string[], word: string) =>
  word.length >= 3 ? names.findIndex(n => n.startsWith(word)) : -1;

/** "today" | "tomorrow" | "friday" | "july 17" | "2026-07-17" -> YYYY-MM-DD, else null. */
function parseDate(desc: string, now: Date): string | null {
  const s = clean(desc).replace(/^(?:on|this|next|the)\s+/, '');
  const dayAfter = (n: number) => isoDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() + n));

  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  if (s === 'today') return isoDay(now);
  if (s === 'tomorrow') return dayAfter(1);

  const weekday = nameIndex(DAYS, s);
  if (weekday >= 0) return dayAfter((weekday - now.getDay() + 7) % 7 || 7); // the coming one, never today

  const monthDay = s.match(/^([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?$/);
  if (monthDay) {
    const month = nameIndex(MONTHS, monthDay[1]);
    if (month < 0) return null;
    const d = new Date(now.getFullYear(), month, Number(monthDay[2]));
    if (d.getMonth() !== month) return null;                          // "february 31"
    if (isoDay(d) < isoDay(now)) d.setFullYear(d.getFullYear() + 1);  // a month already past means next year
    return isoDay(d);
  }
  return null;
}

/** "8pm" | "8:30 pm" | "19:00" | "noon" -> HH:mm, else null. */
function parseTime(desc: string): string | null {
  const s = clean(desc);
  if (s === 'noon') return '12:00';
  if (s === 'midnight') return '00:00';

  const m = s.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/);
  if (!m) return null;
  let hour = Number(m[1]);
  const minute = Number(m[2] ?? 0);
  if (minute > 59) return null;
  if (m[3]) {
    if (hour < 1 || hour > 12) return null;
    hour = (hour % 12) + (m[3] === 'pm' ? 12 : 0);
  } else if (hour > 23) return null;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

/** Both halves of "... on <date> at <time>", or null if either one can't be resolved. */
export function parseWhen(dateDesc: string, timeDesc: string, now: Date = new Date()) {
  const date = parseDate(dateDesc, now);
  const time = parseTime(timeDesc);
  return date && time ? { date, time } : null;
}
