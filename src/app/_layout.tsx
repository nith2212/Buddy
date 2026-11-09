import { Gaegu_400Regular, Gaegu_700Bold } from '@expo-google-fonts/gaegu';
import { Nunito_400Regular, Nunito_600SemiBold, Nunito_700Bold, useFonts } from '@expo-google-fonts/nunito';
import { DefaultTheme, Stack, ThemeProvider, useRootNavigationState, useRouter } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import * as Notifications from 'expo-notifications';

import { BuddySplash } from '@/components/buddy-splash';
import { Onboarding } from '@/components/onboarding';
import { useAuth } from '@/hooks/use-auth';
import { SessionProvider } from '@/hooks/use-session';
import { Palette } from '@/constants/sketch';
import { registerCheckinCategories } from '@/lib/checkin-categories';
import { handleCheckinResponse } from '@/lib/checkin-flow';
import { registerPushToken } from '@/lib/push';

SplashScreen.preventAutoHideAsync();

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

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
  const onboarded = auth.status === 'ready' && auth.onboarded;
  // The task made on onboarding's last screen: its chat opens once the app's screens exist.
  const [firstTask, setFirstTask] = useState<number | null>(null);
  const navReady = !!useRootNavigationState()?.key;

  useEffect(() => {
    if (firstTask === null || !onboarded || !navReady) return;
    router.push({ pathname: '/task/[id]', params: { id: String(firstTask) } });
    setFirstTask(null);
  }, [firstTask, onboarded, navReady, router]);

  useEffect(() => {
    if (!token) return;
    registerCheckinCategories();
    // Only re-registers when permission was already given: onboarding's check-in screen is where Buddy asks.
    registerPushToken(token).catch((e) => console.warn('[PushToken] register failed:', e));

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
      {/* Dark clock and battery on the cream background, even when the phone is in dark mode (the look is light-only). */}
      <StatusBar style="dark" />
      {auth.status !== 'ready' ? (
        <BuddySplash failed={auth.status === 'error'} />
      ) : !auth.onboarded ? (
        <Onboarding
          token={auth.token}
          onDone={(taskId) => {
            setFirstTask(taskId);
            auth.finishOnboarding();
          }}
        />
      ) : (
        <SessionProvider value={{ token: auth.token, restart: auth.restart }}>
          <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: Palette.bg } }} />
        </SessionProvider>
      )}
    </ThemeProvider>
  );
}
