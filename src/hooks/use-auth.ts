import { useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { API_BASE_URL, INVITE_CODE } from '@/constants/api';

const TOKEN_KEY = 'buddy_token';
const USER_ID_KEY = 'buddy_user_id';

export type AuthState =
  | { status: 'loading' }
  | { status: 'ready'; token: string; userId: string }
  | { status: 'error'; message: string };

export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    bootstrap();
  }, []);

  async function bootstrap() {
    try {
      const [storedToken, storedUserId] = await Promise.all([
        SecureStore.getItemAsync(TOKEN_KEY),
        SecureStore.getItemAsync(USER_ID_KEY),
      ]);

      if (storedToken && storedUserId) {
        console.log('[Auth] Using stored identity. token:', storedToken, 'user_id:', storedUserId);
        setState({ status: 'ready', token: storedToken, userId: storedUserId });
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

      console.log('[Auth] Registered new identity. token:', token, 'user_id:', user_id);
      setState({ status: 'ready', token, userId: user_id });
    } catch (e: any) {
      setState({ status: 'error', message: e.message ?? 'Auth failed' });
    }
  }

  return state;
}
