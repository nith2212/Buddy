// Root layout for the Buddy app.
// Handles:
//   - Notification permission request and push token logging (dev helper)
//   - Global notification handler (controls foreground display behaviour)
//   - Notification received listener (logs incoming notifications to Metro console)

import { DarkTheme, DefaultTheme, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import AppTabs from '@/components/app-tabs';

SplashScreen.preventAutoHideAsync();

// Requests notification permission and logs the Expo push token to the Metro console.
// Token looks like: ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxxxx]
// Only runs on physical devices — emulators don't support push tokens.
async function logPushToken() {
  if (!Device.isDevice) {
    console.log('[PushToken] Must use a physical device for push tokens');
    return;
  }
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== 'granted') {
    console.log('[PushToken] Permission not granted');
    return;
  }
  const token = await Notifications.getExpoPushTokenAsync();
  console.log('[PushToken]', token.data);
}

// Controls how notifications behave when the app is in the foreground.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,  // Show the notification banner while app is open.
    shouldShowList: true,    // Include in the notification tray.
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export default function TabLayout() {
  const colorScheme = useColorScheme();

  useEffect(() => {
    logPushToken();
    // Log all incoming notifications to Metro for debugging.
    const sub = Notifications.addNotificationReceivedListener(n =>
      console.log('[NotificationReceived]', JSON.stringify(n))
    );
    return () => sub.remove();
  }, []);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AnimatedSplashOverlay />
      <AppTabs />
    </ThemeProvider>
  );
}
