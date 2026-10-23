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
    registerPushToken(auth.token);

    const sub = Notifications.addNotificationReceivedListener(n =>
      console.log('[NotificationReceived]', JSON.stringify(n))
    );
    return () => sub.remove();
  }, [auth.status]);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AnimatedSplashOverlay />
      <AppTabs />
    </ThemeProvider>
  );
}
