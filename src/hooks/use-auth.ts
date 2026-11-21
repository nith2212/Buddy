import { useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { API_BASE_URL, INVITE_CODE } from '@/constants/api';

const TOKEN_KEY = 'buddy_token';
const USER_ID_KEY = 'buddy_user_id';
// Set once onboarding is finished. "Delete my data" clears it, so a fresh identity sees onboarding again.
const ONBOARDED_KEY = 'buddy_onboarded';

export type AuthState =
  | { status: 'loading' }
  | { status: 'ready'; token: string; userId: string; onboarded: boolean }
  | { status: 'error'; message: string };

export function useAuth(): AuthState & { restart: () => Promise<void>; finishOnboarding: () => Promise<void> } {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    bootstrap();
  }, []);

  async function bootstrap() {
    try {
      const [storedToken, storedUserId, onboarded] = await Promise.all([
        SecureStore.getItemAsync(TOKEN_KEY),
        SecureStore.getItemAsync(USER_ID_KEY),
        SecureStore.getItemAsync(ONBOARDED_KEY),
      ]);

      if (storedToken && storedUserId) {
        if (__DEV__) console.log('[Auth] Using stored identity. user_id:', storedUserId); // never log the token
        setState({ status: 'ready', token: storedToken, userId: storedUserId, onboarded: onboarded === '1' });
        return;
      }

      // First launch — register a new anonymous user
      const res = await fetch(`${API_BASE_URL}/auth/anonymous`, {
        method: 'POST',
        headers: { 'X-Invite-Code': INVITE_CODE },
      });

      if (!res.ok) throw new Error(`Registration failed: ${res.status}`);

      const { token, user_id } = await res.json();

      await Promise.all([
        SecureStore.setItemAsync(TOKEN_KEY, token),
        SecureStore.setItemAsync(USER_ID_KEY, user_id),
      ]);

      if (__DEV__) console.log('[Auth] Registered new identity. user_id:', user_id); // never log the token
      setState({ status: 'ready', token, userId: user_id, onboarded: false });
    } catch (e: any) {
      setState({ status: 'error', message: e.message ?? 'Auth failed' });
    }
  }

  /** Forget this identity and register a fresh one (after "Delete my data" wiped it on the server). */
  async function restart() {
    setState({ status: 'loading' });
    await Promise.all([
      SecureStore.deleteItemAsync(TOKEN_KEY),
      SecureStore.deleteItemAsync(USER_ID_KEY),
      SecureStore.deleteItemAsync(ONBOARDED_KEY),
    ]);
    await bootstrap();
  }

  /** Onboarding is done: don't show it again. If saving the flag fails, it just shows once more next launch. */
  async function finishOnboarding() {
    setState((s) => (s.status === 'ready' ? { ...s, onboarded: true } : s));
    await SecureStore.setItemAsync(ONBOARDED_KEY, '1').catch(() => {});
  }

  return { ...state, restart, finishOnboarding };
}
