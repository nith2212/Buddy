// Hand-drawn building blocks: text, cards with a hatched shadow, buttons, chips and chat bubbles.
// Every screen is made of these, so the look stays in one place.

import { useId, type ReactNode } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type PressableProps,
  type StyleProp,
  type TextProps,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import Svg, { Defs, Line, Pattern, Rect } from 'react-native-svg';

import { Border, Font, Ink, Palette, Wobble, type WobbleKey } from '@/constants/sketch';

// ── text ────────────────────────────────────────────────────────────────────────

const TEXT: Record<string, TextStyle> = {
  title: { fontFamily: Font.hand, fontSize: 34, lineHeight: 38 },
  heading: { fontFamily: Font.hand, fontSize: 26, lineHeight: 30 },
  hand: { fontFamily: Font.hand, fontSize: 19, lineHeight: 23 },
  body: { fontFamily: Font.body, fontSize: 16, lineHeight: 22 },
  semi: { fontFamily: Font.semi, fontSize: 16, lineHeight: 22 },
  bold: { fontFamily: Font.bold, fontSize: 16, lineHeight: 22 },
  small: { fontFamily: Font.semi, fontSize: 13, lineHeight: 18 },
};

export function Txt({ variant = 'body', style, ...rest }: TextProps & { variant?: keyof typeof TEXT }) {
  return <Text {...rest} style={[{ color: Ink }, TEXT[variant], style]} />;
}

// ── hatched shadow ──────────────────────────────────────────────────────────────

/** Diagonal pen hatching that fills its parent (used as an offset shadow). */
export function Hatch({ color = Palette.deep, style }: { color?: string; style?: StyleProp<ViewStyle> }) {
  const id = 'h' + useId().replace(/[^a-zA-Z0-9]/g, '');
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { overflow: 'hidden' }, style]}>
      <Svg width="100%" height="100%">
        <Defs>
          <Pattern id={id} patternUnits="userSpaceOnUse" width={7} height={7} patternTransform="rotate(45)">
            <Line x1={0} y1={0} x2={0} y2={7} stroke={color} strokeWidth={2.4} />
          </Pattern>
        </Defs>
        <Rect x={0} y={0} width="100%" height="100%" fill={`url(#${id})`} />
      </Svg>
    </View>
  );
}

// ── card ────────────────────────────────────────────────────────────────────────

type CardProps = {
  children: ReactNode;
  /** padding, background, layout of the content */
  style?: StyleProp<ViewStyle>;
  /** margins / flex / alignment of the whole card, shadow included */
  outerStyle?: StyleProp<ViewStyle>;
  shadow?: 'hatch' | 'solid' | 'none';
  wobble?: WobbleKey;
  dashed?: boolean;
};

export function Card({ children, style, outerStyle, shadow = 'hatch', wobble = 'a', dashed }: CardProps) {
  const radii = Wobble[wobble];
  return (
    <View style={outerStyle}>
      {shadow === 'hatch' ? <Hatch style={[radii, styles.shadowOffset]} /> : null}
      {shadow === 'solid' ? <View pointerEvents="none" style={[StyleSheet.absoluteFill, radii, styles.shadowOffset, { backgroundColor: Palette.deep }]} /> : null}
      <View style={[styles.cardBody, radii, dashed && styles.dashed, style]}>{children}</View>
    </View>
  );
}

// ── buttons and chips ───────────────────────────────────────────────────────────

type ButtonProps = Omit<PressableProps, 'style' | 'children'> & {
  label?: string;
  children?: ReactNode;
  tone?: 'pop' | 'soft' | 'plain' | 'card';
  wobble?: WobbleKey;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
  /** the offset ink shadow; off for small inline buttons */
  lifted?: boolean;
};

const TONE = { pop: Palette.pop, soft: Palette.soft, plain: Palette.white, card: Palette.card };

/** A pressable sketch box. Pressing pushes it into its shadow. */
export function SketchButton({ label, children, tone = 'pop', wobble = 'c', style, textStyle, lifted = true, disabled, ...rest }: ButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      {...rest}
      style={({ pressed }) => [
        styles.button,
        Wobble[wobble],
        { backgroundColor: TONE[tone] },
        lifted && !pressed && styles.lifted,
        pressed && styles.pressed,
        disabled && styles.disabled,
        style,
      ]}>
      {children ?? <Txt variant="hand" style={[styles.buttonText, textStyle]}>{label}</Txt>}
    </Pressable>
  );
}

type ChipProps = {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  disabled?: boolean;
  /** a small drawn icon before the label */
  icon?: ReactNode;
  accessibilityLabel?: string;
};

export function Chip({ label, selected, onPress, disabled, icon, accessibilityLabel }: ChipProps) {
  return (
    <SketchButton
      label={label}
      tone={selected ? 'soft' : 'plain'}
      lifted={false}
      onPress={onPress}
      disabled={disabled}
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ selected: !!selected, disabled: !!disabled }}
      style={styles.chip}
      textStyle={styles.chipText}>
      {icon ? (
        <View style={styles.chipRow}>
          {icon}
          <Txt variant="hand" style={styles.chipText}>{label}</Txt>
        </View>
      ) : undefined}
    </SketchButton>
  );
}

// ── chat bubbles ────────────────────────────────────────────────────────────────

export function Bubble({ from, children }: { from: 'buddy' | 'me'; children: ReactNode }) {
  const mine = from === 'me';
  return (
    <View style={[styles.bubble, mine ? Wobble.me : Wobble.buddy, mine ? styles.mine : styles.theirs]}>
      <Txt variant={mine ? 'semi' : 'body'}>{children}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  shadowOffset: { transform: [{ translateX: 6 }, { translateY: 6 }] },
  cardBody: { borderWidth: Border, borderColor: Ink, backgroundColor: Palette.card },
  dashed: { borderStyle: 'dashed' },
  button: {
    minHeight: 48,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: Border,
    borderColor: Ink,
  },
  buttonText: { fontSize: 21, lineHeight: 25 },
  lifted: { boxShadow: `4px 4px 0px ${Ink}` },
  pressed: { transform: [{ translateX: 3 }, { translateY: 3 }] },
  disabled: { opacity: 0.45 },
  chip: { minHeight: 44, paddingHorizontal: 12, borderWidth: 2 },
  chipText: { fontSize: 17, lineHeight: 21 },
  chipRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  bubble: { maxWidth: '82%', paddingHorizontal: 14, paddingVertical: 10, borderWidth: Border, borderColor: Ink },
  theirs: { backgroundColor: Palette.card, boxShadow: `4px 4px 0px ${Palette.deep}` },
  mine: { backgroundColor: Palette.pop },
});
