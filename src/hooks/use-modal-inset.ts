import { useSafeAreaInsets } from 'react-native-safe-area-context';

// Android quirk, seen on the developer's Redmi (3-button navigation, 2026-11-09): a Modal with statusBarTranslucent
// lays its content out over the full screen height, but its window stops above the navigation bar, and the bottom
// inset can read 0 inside it. So whatever sat in the bottom ~48dp of the menu (Buddy, "Delete my data") was cut off.
// Keep the bottom of a modal clear of the tallest navigation bar, whatever the inset says.
const NAV_BAR_MAX = 48;

export function useModalBottomInset(): number {
  return Math.max(useSafeAreaInsets().bottom, NAV_BAR_MAX);
}
