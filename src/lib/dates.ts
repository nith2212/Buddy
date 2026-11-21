// Due dates. The app picks a local calendar DAY ('YYYY-MM-DD'); the backend stores the end of that day as a
// UTC instant. "Today" and "Tomorrow" are shortcuts for a day, so one value covers every chip.

export type DayKey = string; // 'YYYY-MM-DD', local time

const pad = (n: number) => String(n).padStart(2, '0');

export function dayKey(d: Date): DayKey {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Local midnight of a day key. */
export function dateOfKey(key: DayKey): Date {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function daysFromToday(n: number, now = new Date()): DayKey {
  return dayKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() + n));
}

/** The local day a stored due date falls on (dates set by the app are 23:59 local on that day). */
export function dayKeyOfIso(iso: string | null): DayKey | null {
  return iso ? dayKey(new Date(iso)) : null;
}

/** End of the chosen local day as an ISO instant (the backend stores UTC). */
export function dueDateFor(key: DayKey | null): string | null {
  if (!key) return null;
  const d = dateOfKey(key);
  d.setHours(23, 59, 0, 0);
  return d.toISOString();
}

export const WEEKDAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December'];

/** "Tue, Nov 10", with the year only when it isn't this year. */
export function prettyDay(key: DayKey, now = new Date()): string {
  const d = dateOfKey(key);
  const year = d.getFullYear() !== now.getFullYear() ? ` ${d.getFullYear()}` : '';
  return `${WEEKDAYS_SHORT[d.getDay()]}, ${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}${year}`;
}

/** One month as Monday-first weeks: null for the blank cells before the 1st. */
export function monthCells(year: number, month: number): (DayKey | null)[] {
  const lead = (new Date(year, month, 1).getDay() + 6) % 7;
  const count = new Date(year, month + 1, 0).getDate();
  const cells: (DayKey | null)[] = Array.from({ length: lead }, () => null);
  for (let d = 1; d <= count; d++) cells.push(`${year}-${pad(month + 1)}-${pad(d)}`);
  return cells;
}

// Calendar-day number in local time, so DST shifts can't skew "tomorrow".
const dayNumber = (d: Date) => Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / 86_400_000);

export function isOverdue(iso: string | null, now = new Date()): boolean {
  return iso !== null && new Date(iso).getTime() < now.getTime();
}

export function formatDue(iso: string | null, now = new Date()): string | null {
  if (!iso) return null;
  const due = new Date(iso);
  const diff = dayNumber(due) - dayNumber(now);
  const short = due.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  if (diff < 0) return `Overdue · ${short}`;
  if (diff === 0) return 'Due today';
  if (diff === 1) return 'Due tomorrow';
  return `Due ${short}`;
}
