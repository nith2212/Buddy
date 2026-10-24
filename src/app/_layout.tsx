import { DarkTheme, DefaultTheme, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import AppTabs from '@/components/app-tabs';
import { useAuth } from '@/hooks/use-auth';
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

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const auth = useAuth();

  useEffect(() => {
    if (auth.status !== 'ready') return;
    registerCheckinCategories();
    registerPushToken(auth.token);

    const receivedSub = Notifications.addNotificationReceivedListener(n =>
      console.log('[NotificationReceived]', JSON.stringify(n))
    );
    const responseSub = Notifications.addNotificationResponseReceivedListener(response => {
      handleCheckinResponse(response, auth.token).catch(e =>
        console.warn('[Checkin] handleCheckinResponse failed:', e)
      );
    });
    return () => {
      receivedSub.remove();
      responseSub.remove();
    };
  }, [auth.status]);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AnimatedSplashOverlay />
      <AppTabs />
    </ThemeProvider>
  );
}
