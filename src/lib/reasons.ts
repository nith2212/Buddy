// The rough reasons a user can tap when a task feels hard to start. The values are exactly what
// POST /chat accepts as `reason` (backend/chat.py). All five are also notification buttons, in two
// sets because Android allows 3 per notification (src/lib/checkin-categories.ts).

export type Reason = 'unclear' | 'too_much' | 'afraid' | 'bored' | 'tired';

export const REASONS: { value: Reason; label: string }[] = [
  { value: 'unclear', label: "Don't know where to start" },
  { value: 'too_much', label: 'Feels too big' },
  { value: 'afraid', label: "Scared it won't be good enough" },
  { value: 'bored', label: 'Boring or pointless' },
  { value: 'tired', label: 'Too tired' },
];
