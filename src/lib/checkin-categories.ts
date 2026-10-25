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

export const CHECKIN_CATEGORIES = {
  task_state: [
    { identifier: 'not_started', buttonTitle: 'Not started', options: BACKGROUND },
    { identifier: 'in_progress', buttonTitle: 'In progress', options: BACKGROUND },
    { identifier: 'done', buttonTitle: 'Done', options: BACKGROUND },
  ],
  // Each value maps straight to a playbook state (fatigue/overwhelm/ambiguity).
  // "avoidance" has no button on purpose — see backend/notifications/router.py.
  emotion: [
    { identifier: 'tired', buttonTitle: '😴 Tired', options: BACKGROUND },
    { identifier: 'too_much', buttonTitle: '😤 Too much', options: BACKGROUND },
    { identifier: 'unclear', buttonTitle: "🤷 Don't know where to start", options: BACKGROUND },
  ],
  chat_opt_in: [
    { identifier: 'yes', buttonTitle: "Yes, let's chat", options: OPEN_APP },
    { identifier: 'no', buttonTitle: 'No thanks', options: BACKGROUND },
  ],
} as const;

export type CheckinStage = keyof typeof CHECKIN_CATEGORIES;

export async function registerCheckinCategories() {
  for (const [stage, actions] of Object.entries(CHECKIN_CATEGORIES)) {
    await Notifications.setNotificationCategoryAsync(stage, [...actions]);
  }
}
