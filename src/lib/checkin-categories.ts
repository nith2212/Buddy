// Notification action-button definitions for the 3-stage check-in flow.
// Each category's action identifiers ARE the values the server expects in
// POST /checkin/action — the response handler forwards them as-is.

import * as Notifications from 'expo-notifications';

export const CHECKIN_CATEGORIES = {
  task_state: [
    { identifier: 'not_started', buttonTitle: 'Not started' },
    { identifier: 'in_progress', buttonTitle: 'In progress' },
    { identifier: 'done', buttonTitle: 'Done' },
  ],
  emotion: [
    { identifier: 'good', buttonTitle: '😊 Good' },
    { identifier: 'neutral', buttonTitle: '😐 Neutral' },
    { identifier: 'low', buttonTitle: '😔 Low' },
  ],
  chat_opt_in: [
    { identifier: 'yes', buttonTitle: "Yes, let's chat" },
    { identifier: 'no', buttonTitle: 'No thanks' },
  ],
} as const;

export type CheckinStage = keyof typeof CHECKIN_CATEGORIES;

export async function registerCheckinCategories() {
  for (const [stage, actions] of Object.entries(CHECKIN_CATEGORIES)) {
    await Notifications.setNotificationCategoryAsync(stage, [...actions]);
  }
}
