// The rough reasons a user can tap when a task feels hard to start. The values are exactly what
// POST /chat accepts as `reason` (backend/chat.py). The first three are also the notification
// buttons (Android allows 3); "afraid" and "bored" only appear here, as in-app chips.

export type Reason = 'unclear' | 'too_much' | 'afraid' | 'bored' | 'tired';

export const REASONS: { value: Reason; label: string }[] = [
  { value: 'unclear', label: "Don't know where to start" },
  { value: 'too_much', label: 'Feels too big' },
  { value: 'afraid', label: "Scared it won't be good enough" },
  { value: 'bored', label: 'Boring or pointless' },
  { value: 'tired', label: 'Too tired' },
];
