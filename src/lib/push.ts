// Registering this phone for check-in notifications.
// Buddy asks for notification permission on onboarding's check-in screen, after explaining what check-ins are,
// never at launch. At launch it only re-registers when permission was already given (tokens can change).

import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';

import { API_BASE_URL } from '@/constants/api';

/** Returns whether this phone is now registered. `ask` shows Android's permission prompt if it still may. */
export async function registerPushToken(authToken: string, ask = false): Promise<boolean> {
  if (!Device.isDevice) return false;

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
