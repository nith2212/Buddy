import { Gaegu_400Regular, Gaegu_700Bold } from '@expo-google-fonts/gaegu';
import { Nunito_400Regular, Nunito_600SemiBold, Nunito_700Bold, useFonts } from '@expo-google-fonts/nunito';
import { DefaultTheme, Stack, ThemeProvider, useRouter } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

import { BuddySplash } from '@/components/buddy-splash';
import { useAuth } from '@/hooks/use-auth';
import { SessionProvider } from '@/hooks/use-session';
import { API_BASE_URL } from '@/constants/api';
import { Palette } from '@/constants/sketch';
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

// The sketch design is light-only for now: one cream background everywhere.
const BuddyTheme = { ...DefaultTheme, colors: { ...DefaultTheme.colors, background: Palette.bg, card: Palette.card } };

export default function RootLayout() {
  // The splash screen stays up (preventAutoHideAsync above) until the fonts are ready.
  const [fontsLoaded, fontError] = useFonts({
    Gaegu_400Regular, Gaegu_700Bold, Nunito_400Regular, Nunito_600SemiBold, Nunito_700Bold,
  });
  const auth = useAuth();
  const router = useRouter();
  const token = auth.status === 'ready' ? auth.token : null;

  useEffect(() => {
    if (!token) return;
    registerCheckinCategories();
    registerPushToken(token);

    const respond = (response: Notifications.NotificationResponse) =>
      handleCheckinResponse(response, token, {
        openChat: (taskId) => router.push({ pathname: '/task/[id]', params: { id: String(taskId), from: 'checkin' } }),
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

  // Hand over from the native splash to Buddy's own loading screen once the fonts can draw it.
  useEffect(() => {
    if (fontsLoaded || fontError) SplashScreen.hideAsync();
  }, [fontsLoaded, fontError]);

  if (!fontsLoaded && !fontError) return null;

  return (
    <ThemeProvider value={BuddyTheme}>
      {auth.status === 'ready' ? (
        <SessionProvider value={{ token: auth.token, restart: auth.restart }}>
          <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Palette.bg } }} />
        </SessionProvider>
      ) : (
        <BuddySplash failed={auth.status === 'error'} />
      )}
    </ThemeProvider>
  );
}
