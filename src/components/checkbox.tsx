import { Pressable, StyleSheet } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { type Colors } from '@/constants/sketch';
import { useColors, useThemedStyles } from '@/hooks/use-theme';

/** A hand-drawn square checkbox with a 44px touch target. */
export function Checkbox({ checked, onPress, label, size = 28 }: { checked: boolean; onPress: () => void; label: string; size?: number }) {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  return (
    <Pressable
      onPress={onPress}
      hitSlop={(44 - size) / 2 + 2}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={label}
      style={[styles.box, { width: size, height: size, backgroundColor: checked ? c.pop : c.white }]}>
      {checked ? (
        <Svg width={size * 0.7} height={size * 0.62} viewBox="0 0 20 18">
          <Path d="M2 9 L8 15 L18 2" fill="none" stroke={c.onPop} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
        </Svg>
      ) : null}
    </Pressable>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
  box: {
    borderWidth: 2.5,
    borderColor: c.ink,
    borderTopLeftRadius: 6,
    borderTopRightRadius: 9,
    borderBottomRightRadius: 5,
    borderBottomLeftRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
