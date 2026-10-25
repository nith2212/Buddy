// Drives the check-in flow once a push/local notification's action button is tapped:
// POST the tap to the backend, then present whatever stage comes back next as a
// local notification — chaining task_state -> emotion -> chat_opt_in -> done
// without needing another server-sent push for each step. Choosing "Yes, let's
// chat" skips the chaining and opens that task's chat screen directly.

import * as Notifications from 'expo-notifications';

import { API_BASE_URL } from '@/constants/api';
import { CheckinStage } from '@/lib/checkin-categories';

type Handlers = { openChat: (taskId: number) => void };

// When a tap launches the app from a killed state it can reach us twice (as the
// "last response" and through the live listener). Re-posting would log a second
// emotion/event, so remember what this process has already handled.
const handled = new Set<string>();

export async function handleCheckinResponse(
  response: Notifications.NotificationResponse,
  token: string,
  handlers: Handlers,
) {
  const key = `${response.notification.request.identifier}|${response.actionIdentifier}|${response.notification.date}`;
  if (handled.has(key)) return;
  handled.add(key);

  try {
    await process(response, token, handlers);
  } finally {
    // Otherwise the next launch would find this same response and replay it.
    await Notifications.clearLastNotificationResponseAsync();
  }
}

async function process(response: Notifications.NotificationResponse, token: string, { openChat }: Handlers) {
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
  const taskId = data.task_id;

  let res: Response | null = null;
  try {
    res = await fetch(`${API_BASE_URL}/checkin/action`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ task_id: taskId, stage: data.stage, value: actionIdentifier }),
    });
  } catch (e) {
    console.warn('[Checkin] /checkin/action network error:', e);
  }

  // Clear the notification that was just acted on, success or not — leaving it
  // in the shade with stale buttons invites a duplicate/conflicting tap.
  await Notifications.dismissNotificationAsync(response.notification.request.identifier);

  // They said yes to chatting: take them there even if recording the answer failed.
  if (data.stage === 'chat_opt_in' && actionIdentifier === 'yes') {
    openChat(taskId);
    return;
  }

  if (!res) return;
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
      // registered category — "done" is a plain informational notification.
      ...(nextData.actions ? { categoryIdentifier: nextData.stage } : {}),
    },
    trigger: null, // fire immediately
  });
}
