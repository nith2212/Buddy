// The hand-drawn look (developer-approved mockup, 2026-11-05): ink outlines, slightly uneven corners and offset
// shadows, in two palettes: "Dusk" (light) and "Dusk Night" (dark, developer's pick 2026-11-09). Screens read
// colours from the theme (hooks/use-theme.tsx), never these objects directly, so both looks stay in step.

import type { ViewStyle } from 'react-native';

export type Colors = {
  bg: string; // screen background (paper)
  card: string; // cards, Buddy's bubbles
  soft: string; // sky: selected chips, highlights
  pop: string; // lavender: buttons, your bubbles
  deep: string; // violet: shadows and accents only (too light/dark for text)
  white: string; // inputs and plain buttons, a step brighter than cards
  danger: string; // errors
  muted: string; // secondary text, placeholders
  ink: string; // lines and text
  onPop: string; // text and lines drawn ON lavender or sky (ink in light; dark in dark, for contrast)
  lift: string; // the offset shadow under lifted buttons
  scrim: string; // the dim layer behind sheets and the menu
  pastDay: string; // greyed-out days in the calendar
};

export const Dusk: Colors = {
  bg: '#F2EAE0',
  card: '#FFFCF8',
  soft: '#B4D3D9',
  pop: '#BDA6CE',
  deep: '#9B8EC7',
  white: '#FFFFFF',
  danger: '#9E2F2A', // passes contrast on cream
  muted: '#5A5168',
  ink: '#2A2238',
  onPop: '#2A2238',
  lift: '#2A2238',
  scrim: 'rgba(42, 34, 56, 0.42)',
  pastDay: '#8A8296',
};

// Every text pair checked for contrast (4.5:1 or more) on 2026-11-09.
export const DuskNight: Colors = {
  bg: '#1C1826',
  card: '#282236',
  soft: '#86B2BB',
  pop: '#BDA6CE',
  deep: '#7466B0',
  white: '#2F2940',
  danger: '#F28B82',
  muted: '#BDB4CC',
  ink: '#F2EAE0',
  onPop: '#1C1826',
  lift: '#7466B0',
  scrim: 'rgba(0, 0, 0, 0.55)',
  pastDay: '#6E6680',
};

/** Buddy's own colours: a white dumpling with dark ink, the same in both looks. */
export const BuddyInk = '#2A2238';
export const BuddyBody = '#FFFFFF';

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
