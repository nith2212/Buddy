import { DarkTheme, DefaultTheme, Stack, ThemeProvider, useRouter } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, useColorScheme } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useAuth } from '@/hooks/use-auth';
import { SessionProvider } from '@/hooks/use-session';
import { API_BASE_URL } from '@/constants/api';
import { registerCheckinCategories } from '@/lib/checkin-categories';
import { handleCheckinResponse } from '@/lib/checkin-flow';

SplashScreen.preventAutoHideAsync();

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

async function registerPushToken(token: string) {
  if (!Device.isDevice) return;

  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== 'granted') {
    console.log('[PushToken] Permission not granted');
    return;
  }

  const pushToken = await Notifications.getExpoPushTokenAsync();

  await fetch(`${API_BASE_URL}/devices/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      expo_push_token: pushToken.data,
      platform: 'android',
    }),
  });

  console.log('[PushToken] Registered:', pushToken.data);
}

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const auth = useAuth();
  const router = useRouter();
  const token = auth.status === 'ready' ? auth.token : null;

  useEffect(() => {
    if (!token) return;
    registerCheckinCategories();
    registerPushToken(token);

    const respond = (response: Notifications.NotificationResponse) =>
      handleCheckinResponse(response, token, {
        openChat: (taskId) => router.push({ pathname: '/task/[id]', params: { id: String(taskId) } }),
      }).catch((e) => console.warn('[Checkin] handleCheckinResponse failed:', e));

    // A tap that launched the app from a killed state isn't guaranteed to reach the
    // live listener below, so pick it up explicitly (handleCheckinResponse dedupes).
    Notifications.getLastNotificationResponseAsync().then((last) => {
      if (last) respond(last);
    });

    const receivedSub = Notifications.addNotificationReceivedListener((n) =>
      console.log('[NotificationReceived]', JSON.stringify(n)),
    );
    const responseSub = Notifications.addNotificationResponseReceivedListener(respond);
    return () => {
      receivedSub.remove();
      responseSub.remove();
    };
  }, [token, router]);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      {auth.status === 'ready' ? (
        <SessionProvider value={auth.token}>
          <Stack screenOptions={{ headerShown: false }} />
        </SessionProvider>
      ) : (
        <ThemedView style={styles.center}>
          {auth.status === 'loading' ? (
            <ActivityIndicator />
          ) : (
            <ThemedText style={styles.centerText}>
              Couldn&apos;t reach Buddy. Check your connection and reopen the app.
            </ThemedText>
          )}
        </ThemedView>
      )}
      <AnimatedSplashOverlay />
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  centerText: { textAlign: 'center' },
});
