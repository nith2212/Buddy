// Buddy: the soft white "dumpling" blob (developer's drawing). The body wobbles like an amoeba and the
// eyes blink; both stop when the phone asks for reduced motion. Three moods:
//   default  round eyes, small smile (loading, chat, menu)
//   happy    ^ ^ eyes, little open mouth (Echoes, wins)
//   worried  tall eyes, flat mouth (only for "can't reach the server", never at the user's feelings)

import { useEffect } from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, {
  Easing,
  useAnimatedProps,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Ellipse, Path } from 'react-native-svg';

import { Ink } from '@/constants/sketch';

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedEllipse = Animated.createAnimatedComponent(Ellipse);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

// Three body outlines with the same commands (M + 4 curves), so the wobble is a plain number blend.
// They live INSIDE a worklet: a module-level array captured by the animation turned up undefined on
// the UI thread (phone test 2026-11-05), which crashed the frame loop and froze the loading screen.
const POINTS = 26;

function shapePoint(shape: number, k: number): number {
  'worklet';
  const S0 = [80, 14, 121, 12, 149, 32, 151, 62, 153, 91, 131, 108, 82, 108, 35, 108, 9, 95, 9, 64, 9, 32, 39, 16, 80, 14];
  const S1 = [78, 10, 124, 12, 152, 36, 150, 64, 148, 94, 126, 110, 80, 110, 38, 110, 12, 92, 11, 62, 10, 30, 36, 8, 78, 10];
  const S2 = [82, 15, 118, 10, 147, 28, 152, 60, 156, 90, 134, 112, 84, 107, 33, 106, 6, 98, 8, 66, 10, 34, 42, 19, 82, 15];
  return (shape === 0 ? S0 : shape === 1 ? S1 : S2)[k];
}

/** The body outline `s` (0..1) of the way from shape `from` to the next one. */
function blendedOutline(from: number, s: number): string {
  'worklet';
  const to = (from + 1) % 3;
  const n: number[] = [];
  for (let k = 0; k < POINTS; k++) {
    const a = shapePoint(from, k);
    n.push(a + (shapePoint(to, k) - a) * s);
  }
  let d = `M${n[0].toFixed(1)} ${n[1].toFixed(1)}`;
  for (let i = 2; i < POINTS; i += 6) {
    d += ` C${n[i].toFixed(1)} ${n[i + 1].toFixed(1)} ${n[i + 2].toFixed(1)} ${n[i + 3].toFixed(1)} ${n[i + 4].toFixed(1)} ${n[i + 5].toFixed(1)}`;
  }
  return d + ' Z';
}

const REST_OUTLINE = 'M80 14 C121 12 149 32 151 62 C153 91 131 108 82 108 C35 108 9 95 9 64 C9 32 39 16 80 14 Z';
const SKETCH = 'M82 11 C123 13 147 34 149 60 C151 92 128 110 80 106 C37 106 11 93 12 62 C13 33 41 13 82 11 Z';
const WOBBLE_MS = 4200;

export type Mood = 'default' | 'happy' | 'worried';

type Props = {
  width: number;
  mood?: Mood;
  /** wobble + blink; keep it off for small avatars next to text */
  animated?: boolean;
  label?: string;
  style?: StyleProp<ViewStyle>;
};

export function BuddyBlob({ width, mood = 'default', animated = true, label = 'Buddy', style }: Props) {
  const height = (width * 120) / 160;
  const reduceMotion = useReducedMotion();
  const moving = animated && !reduceMotion;
  // Lines look the same thickness at any size.
  const stroke = Math.min(9, Math.max(2.4, (2.8 * 160) / width));

  const phase = useSharedValue(0);
  const blink = useSharedValue(1);
  useEffect(() => {
    if (!moving) return;
    phase.value = withRepeat(withTiming(1, { duration: WOBBLE_MS, easing: Easing.linear }), -1, false);
    blink.value = withRepeat(
      withSequence(withDelay(3800, withTiming(0.08, { duration: 90 })), withTiming(1, { duration: 130 })),
      -1,
      false,
    );
  }, [moving, phase, blink]);

  const bodyProps = useAnimatedProps(() => {
    const t = phase.value * 3; // 0..3 across the three shapes and back to the first
    const i = Math.min(2, Math.floor(t));
    const f = t - i;
    const s = f * f * (3 - 2 * f); // ease in-out
    return { d: blendedOutline(i, s) };
  });
  // one set of animated props per element (each animated component gets its own)
  const leftEye = useAnimatedProps(() => ({ ry: (mood === 'worried' ? 10 : 7) * blink.value }));
  const rightEye = useAnimatedProps(() => ({ ry: (mood === 'worried' ? 10 : 7) * blink.value }));
  const leftSparkle = useAnimatedProps(() => ({ opacity: blink.value > 0.5 ? 1 : 0 }));
  const rightSparkle = useAnimatedProps(() => ({ opacity: blink.value > 0.5 ? 1 : 0 }));

  return (
    <View accessible accessibilityRole="image" accessibilityLabel={label} style={[{ width, height }, style]}>
      <Svg width={width} height={height} viewBox="0 0 160 120">
        <AnimatedPath animatedProps={bodyProps} d={REST_OUTLINE} fill="#FFFFFF" stroke={Ink} strokeWidth={stroke} strokeLinejoin="round" />
        {width >= 80 ? <Path d={SKETCH} fill="none" stroke={Ink} strokeWidth={stroke * 0.45} strokeOpacity={0.55} /> : null}

        {mood === 'default' ? (
          <>
            <AnimatedEllipse animatedProps={leftEye} cx={60} cy={58} rx={7} ry={7} fill={Ink} />
            <AnimatedEllipse animatedProps={rightEye} cx={102} cy={56} rx={7} ry={7} fill={Ink} />
            {width >= 60 ? (
              <>
                <AnimatedCircle animatedProps={leftSparkle} cx={62.5} cy={55} r={2} fill="#FFFFFF" />
                <AnimatedCircle animatedProps={rightSparkle} cx={104.5} cy={53} r={2} fill="#FFFFFF" />
              </>
            ) : null}
            <Path d="M74 74 Q81 80 88 73" fill="none" stroke={Ink} strokeWidth={stroke * 0.9} strokeLinecap="round" />
          </>
        ) : null}

        {mood === 'happy' ? (
          <>
            <Path d="M51 59 Q60 49 69 59 M93 57 Q102 47 111 57" fill="none" stroke={Ink} strokeWidth={stroke * 1.1} strokeLinecap="round" />
            <Path d="M74 70 L88 70 Q88 83 81 83 Q74 83 74 70 Z" fill="#FFFFFF" stroke={Ink} strokeWidth={stroke * 0.9} strokeLinejoin="round" />
          </>
        ) : null}

        {mood === 'worried' ? (
          <>
            <AnimatedEllipse animatedProps={leftEye} cx={60} cy={56} rx={5.5} ry={10} fill={Ink} />
            <AnimatedEllipse animatedProps={rightEye} cx={102} cy={54} rx={5.5} ry={10} fill={Ink} />
            <AnimatedCircle animatedProps={leftSparkle} cx={61} cy={65} r={2.2} fill="#FFFFFF" />
            <AnimatedCircle animatedProps={rightSparkle} cx={103} cy={63} r={2.2} fill="#FFFFFF" />
            <Path d="M74 77 Q81 74 88 77" fill="none" stroke={Ink} strokeWidth={stroke * 0.9} strokeLinecap="round" />
          </>
        ) : null}
      </Svg>
    </View>
  );
}
