// Registering this phone for check-in notifications.
// Buddy asks for notification permission on onboarding's check-in screen, after explaining what check-ins are,
// never at launch. At launch it only re-registers when permission was already given (tokens can change).

import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { API_BASE_URL } from '@/constants/api';

// The server sends check-ins on this channel (backend notifications/service.py). Android files a push for a channel
// that doesn't exist under "Miscellaneous", so the app creates it, before any token is requested. People can change
// its sound or turn it off in Settings → Apps → Buddy → Notifications. Creating it again is harmless.
export const CHECKIN_CHANNEL = 'buddy-checkin';

async function ensureCheckinChannel() {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync(CHECKIN_CHANNEL, {
    name: 'Check-ins',
    description: "Buddy's check-in on a task, at most once a day",
    importance: Notifications.AndroidImportance.HIGH, // shows the buttons right away, so a reason is one tap
  });
}

/** Returns whether this phone is now registered. `ask` shows Android's permission prompt if it still may. */
export async function registerPushToken(authToken: string, ask = false): Promise<boolean> {
  if (!Device.isDevice) return false;
  await ensureCheckinChannel();

  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted && ask && permission.canAskAgain) {
    permission = await Notifications.requestPermissionsAsync();
  }
  if (!permission.granted) return false;

  const pushToken = await Notifications.getExpoPushTokenAsync();
  const res = await fetch(`${API_BASE_URL}/devices/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
    body: JSON.stringify({ expo_push_token: pushToken.data, platform: 'android' }),
  });
  return res.ok; // never log the push token itself
}
