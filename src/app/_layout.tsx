import { Gaegu_400Regular, Gaegu_700Bold } from '@expo-google-fonts/gaegu';
import { Nunito_400Regular, Nunito_600SemiBold, Nunito_700Bold, useFonts } from '@expo-google-fonts/nunito';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider, useRootNavigationState, useRouter } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, useState } from 'react';
import * as Notifications from 'expo-notifications';

import { BuddySplash } from '@/components/buddy-splash';
import { Onboarding } from '@/components/onboarding';
import { useAuth } from '@/hooks/use-auth';
import { SessionProvider } from '@/hooks/use-session';
import { ThemeRoot, useTheme } from '@/hooks/use-theme';
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

export default function RootLayout() {
  return (
    <ThemeRoot>
      <App />
    </ThemeRoot>
  );
}

function App() {
  const theme = useTheme();
  const c = theme.colors;
  // Navigation's own backgrounds follow the look too, so no white flashes between screens.
  const navTheme = useMemo(() => {
    const base = theme.dark ? DarkTheme : DefaultTheme;
    return { ...base, colors: { ...base.colors, background: c.bg, card: c.card, text: c.ink, border: c.ink } };
  }, [theme.dark, c]);
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
    if ((fontsLoaded || fontError) && theme.ready) SplashScreen.hideAsync();
  }, [fontsLoaded, fontError, theme.ready]);

  // Wait for the saved light/dark pick too, so the app never opens in the wrong look and flips.
  if ((!fontsLoaded && !fontError) || !theme.ready) return null;

  return (
    <ThemeProvider value={navTheme}>
      {/* The clock and battery follow Buddy's look, not the phone's: dark on cream, light on Dusk Night. */}
      <StatusBar style={theme.dark ? 'light' : 'dark'} />
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
          <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.bg } }} />
        </SessionProvider>
      )}
    </ThemeProvider>
  );
}
