// Light ("Dusk") or dark ("Dusk Night"). Until the person taps the toggle, the app follows the phone's setting;
// after that it remembers their pick on the phone.

import * as SecureStore from 'expo-secure-store';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { Dusk, DuskNight, type Colors } from '@/constants/sketch';

const THEME_KEY = 'buddy_theme'; // 'light' | 'dark'; missing = follow the phone

type Theme = { colors: Colors; dark: boolean; ready: boolean; toggle: () => void };

const ThemeContext = createContext<Theme>({ colors: Dusk, dark: false, ready: true, toggle: () => {} });

export function ThemeRoot({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [picked, setPicked] = useState<'light' | 'dark' | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(THEME_KEY)
      .then((v) => setPicked(v === 'light' || v === 'dark' ? v : null))
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  const dark = (picked ?? system) === 'dark';
  const toggle = useCallback(() => {
    const next = dark ? 'light' : 'dark';
    setPicked(next);
    SecureStore.setItemAsync(THEME_KEY, next).catch(() => {}); // not saved = follows the phone next launch
  }, [dark]);

  const value = useMemo(() => ({ colors: dark ? DuskNight : Dusk, dark, ready, toggle }), [dark, ready, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}

export function useColors(): Colors {
  return useContext(ThemeContext).colors;
}

/** Styles that use theme colours, built once per look: `const styles = useThemedStyles(makeStyles)`. */
export function useThemedStyles<T>(make: (c: Colors) => T): T {
  const colors = useColors();
  return useMemo(() => make(colors), [make, colors]);
}
