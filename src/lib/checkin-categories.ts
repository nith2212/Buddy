// Notification action-button definitions for the 3-stage check-in flow.
// Each category's action identifiers ARE the values the server expects in
// POST /checkin/action — the response handler forwards them as-is.

import * as Notifications from 'expo-notifications';

// opensAppToForeground: false — these buttons submit in the background and chain
// to the next stage's local notification; nothing about answering "in progress"
// or picking an emotion needs the app to come to the foreground. The one exception
// is chat_opt_in's "yes": it opens the app straight into that task's chat.
const BACKGROUND = { opensAppToForeground: false } as const;
const OPEN_APP = { opensAppToForeground: true } as const;

// Labels are the developer's wording (docs/notification_wording.md, 2026-11-08). The server's `actions`
// lists in backend/notifications/ mirror them; keep both in step. Short labels: Android cuts long ones.
export const CHECKIN_CATEGORIES = {
  task_state: [
    { identifier: 'not_started', buttonTitle: 'Not yet', options: BACKGROUND },
    { identifier: 'in_progress', buttonTitle: 'On it', options: BACKGROUND },
    { identifier: 'done', buttonTitle: 'Done!', options: BACKGROUND },
  ],
  // Each value maps straight to a playbook state. Android allows 3 buttons, so the 5 reasons come in
  // two sets: "Something else" ('more') makes the server send the second set as stage emotion_more.
  // "avoidance" has no button on purpose — see backend/notifications/router.py.
  emotion: [
    { identifier: 'tired', buttonTitle: '😴 Tired', options: BACKGROUND },
    { identifier: 'unclear', buttonTitle: '🤷 Where do I start?', options: BACKGROUND },
    { identifier: 'more', buttonTitle: '💭 Something else', options: BACKGROUND },
  ],
  emotion_more: [
    { identifier: 'too_much', buttonTitle: '😤 Too much', options: BACKGROUND },
    { identifier: 'afraid', buttonTitle: "😬 Scared it's not good", options: BACKGROUND },
    { identifier: 'bored', buttonTitle: '🥱 Boring', options: BACKGROUND },
  ],
  chat_opt_in: [
    { identifier: 'yes', buttonTitle: "Let's chat", options: OPEN_APP },
    { identifier: 'no', buttonTitle: 'Not now', options: BACKGROUND },
  ],
} as const;

export type CheckinStage = keyof typeof CHECKIN_CATEGORIES;

export async function registerCheckinCategories() {
  for (const [stage, actions] of Object.entries(CHECKIN_CATEGORIES)) {
    await Notifications.setNotificationCategoryAsync(stage, [...actions]);
  }
}
