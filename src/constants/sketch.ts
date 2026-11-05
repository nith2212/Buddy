// The hand-drawn look (owner-approved mockup, 2026-11-05): the "Dusk" palette, ink outlines,
// slightly uneven corners and offset shadows. Light only for now.

import type { ViewStyle } from 'react-native';

export const Ink = '#2A2238';

export const Palette = {
  bg: '#F2EAE0', // cream: screen background
  card: '#FFFCF8', // cards, Buddy's bubbles
  soft: '#B4D3D9', // sky: selected chips, highlights
  pop: '#BDA6CE', // lavender: buttons, your bubbles
  deep: '#9B8EC7', // violet: shadows and accents only (too light for text)
  white: '#FFFFFF',
  danger: '#9E2F2A', // errors (passes contrast on cream)
  muted: '#5A5168', // secondary text, placeholders
} as const;

// Font family names = the @expo-google-fonts export names loaded in app/_layout.tsx.
// Android ignores fontWeight for custom fonts, so each weight is its own family.
export const Font = {
  hand: 'Gaegu_700Bold',
  handRegular: 'Gaegu_400Regular',
  body: 'Nunito_400Regular',
  semi: 'Nunito_600SemiBold',
  bold: 'Nunito_700Bold',
} as const;

export const Border = 2.5;

// Uneven corners so boxes look drawn, not machined. Pick one per element so neighbours differ.
export const Wobble = {
  a: { borderTopLeftRadius: 18, borderTopRightRadius: 10, borderBottomRightRadius: 20, borderBottomLeftRadius: 9 },
  b: { borderTopLeftRadius: 10, borderTopRightRadius: 20, borderBottomRightRadius: 9, borderBottomLeftRadius: 18 },
  c: { borderTopLeftRadius: 14, borderTopRightRadius: 9, borderBottomRightRadius: 13, borderBottomLeftRadius: 8 },
  round: { borderTopLeftRadius: 26, borderTopRightRadius: 23, borderBottomRightRadius: 25, borderBottomLeftRadius: 22 },
  buddy: { borderTopLeftRadius: 6, borderTopRightRadius: 20, borderBottomRightRadius: 18, borderBottomLeftRadius: 16 },
  me: { borderTopLeftRadius: 20, borderTopRightRadius: 6, borderBottomRightRadius: 16, borderBottomLeftRadius: 18 },
} satisfies Record<string, ViewStyle>;

export type WobbleKey = keyof typeof Wobble;
