export type DueOption = 'none' | 'today' | 'tomorrow' | 'in3' | 'nextweek';

export const DUE_OPTIONS: { key: DueOption; label: string }[] = [
  { key: 'none', label: 'No date' },
  { key: 'today', label: 'Today' },
  { key: 'tomorrow', label: 'Tomorrow' },
  { key: 'in3', label: 'In 3 days' },
  { key: 'nextweek', label: 'Next week' },
];

const DAYS_AHEAD = { today: 0, tomorrow: 1, in3: 3, nextweek: 7 } as const;

/** End of the chosen local day as an ISO instant (the backend stores UTC). */
export function dueDateFor(option: DueOption): string | null {
  if (option === 'none') return null;
  const d = new Date();
  d.setDate(d.getDate() + DAYS_AHEAD[option]);
  d.setHours(23, 59, 0, 0);
  return d.toISOString();
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
