// Drives the check-in flow once a push/local notification's action button is tapped:
// POST the tap to the backend, then present whatever stage comes back next as a
// local notification — chaining task_state -> emotion -> chat_opt_in -> done/chat
// without needing another server-sent push for each step.

import * as Notifications from 'expo-notifications';

import { API_BASE_URL } from '@/constants/api';
import { CheckinStage } from '@/lib/checkin-categories';

export async function handleCheckinResponse(
  response: Notifications.NotificationResponse,
  token: string,
) {
  const actionIdentifier = response.actionIdentifier;
  if (actionIdentifier === Notifications.DEFAULT_ACTION_IDENTIFIER) {
    // User tapped the notification body, not an action button — nothing to submit yet.
    return;
  }

  const data = response.notification.request.content.data as {
    stage?: CheckinStage;
    task_id?: number;
  };
  if (!data?.stage || data.task_id == null) {
    console.warn('[Checkin] Notification missing stage/task_id, cannot submit action');
    return;
  }

  const res = await fetch(`${API_BASE_URL}/checkin/action`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ task_id: data.task_id, stage: data.stage, value: actionIdentifier }),
  });

  if (!res.ok) {
    console.warn('[Checkin] /checkin/action failed:', res.status);
    return;
  }

  const body = await res.json();
  const next = body.notification as
    | { title: string; body: string; data: Record<string, unknown> }
    | undefined;
  if (!next) return;

  const nextData = next.data as { stage?: string; task_id?: number; actions?: unknown[] };

  await Notifications.scheduleNotificationAsync({
    content: {
      title: next.title,
      body: next.body,
      data: nextData,
      // Only stages with buttons (task_state/emotion/chat_opt_in) have a matching
      // registered category — "done"/"chat" are plain informational notifications.
      ...(nextData.actions ? { categoryIdentifier: nextData.stage } : {}),
    },
    trigger: null, // fire immediately
  });
}
