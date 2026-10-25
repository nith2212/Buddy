import { Pressable, StyleSheet, Text } from 'react-native';

import { Accent } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export function Checkbox({ checked, onPress, label }: { checked: boolean; onPress: () => void; label: string }) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      hitSlop={10}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={label}
      style={[styles.box, { borderColor: checked ? Accent : theme.textSecondary }, checked && styles.checked]}>
      {checked ? <Text style={styles.tick}>✓</Text> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  box: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checked: { backgroundColor: Accent },
  tick: { color: '#ffffff', fontSize: 14, fontWeight: '700', lineHeight: 16 },
});
