// The loading screen (mockup screen 1): Buddy floating while the app gets ready. Render's free tier
// naps when idle, so a first launch can take a while: say so honestly instead of a bare spinner.

import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  FadeOut,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { BuddyBlob } from '@/components/buddy-blob';
import { Txt } from '@/components/sketch';
import { type Colors } from '@/constants/sketch';
import { useColors, useThemedStyles } from '@/hooks/use-theme';

export function BuddySplash({ failed }: { failed?: boolean }) {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  const reduceMotion = useReducedMotion();
  const float = useSharedValue(0);
  useEffect(() => {
    if (reduceMotion) return;
    float.value = withRepeat(withTiming(1, { duration: 1600, easing: Easing.inOut(Easing.sin) }), -1, true);
  }, [float, reduceMotion]);

  const bob = useAnimatedStyle(() => ({ transform: [{ translateY: -16 * float.value }, { rotate: `${-3 + 6 * float.value}deg` }] }));
  const floor = useAnimatedStyle(() => ({ transform: [{ scaleX: 1 - 0.3 * float.value }], opacity: 0.55 - 0.25 * float.value }));

  return (
    <Animated.View exiting={FadeOut.duration(250)} style={styles.screen} accessibilityLiveRegion="polite">
      <Txt variant="title" style={styles.brand}>
        buddy<Txt variant="title" style={[styles.brand, { color: c.deep }]}>.</Txt>
      </Txt>
      <Animated.View style={bob}>
        <BuddyBlob width={220} mood={failed ? 'worried' : 'default'} label={failed ? 'Buddy, worried' : 'Buddy, floating while the app wakes up'} />
      </Animated.View>
      <Animated.View style={[styles.floor, floor]} />
      {failed ? (
        <View style={styles.text}>
          <Txt variant="heading" style={styles.center}>Couldn’t reach Buddy.</Txt>
          <Txt style={styles.center}>Check your connection and reopen the app.</Txt>
        </View>
      ) : (
        <View style={styles.text}>
          <Txt variant="heading" style={styles.center}>Waking Buddy up…</Txt>
          <Txt style={styles.center}>Buddy naps when nobody’s around. This takes a few seconds.</Txt>
        </View>
      )}
    </Animated.View>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
  screen: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: c.bg,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    gap: 8,
  },
  brand: { fontSize: 68, lineHeight: 72, marginBottom: 20 },
  floor: { width: 130, height: 16, borderRadius: 8, backgroundColor: c.deep, marginTop: 4 },
  text: { marginTop: 36, gap: 6, maxWidth: 280 },
  center: { textAlign: 'center' },
});
