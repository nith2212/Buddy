// The slide-out menu (mockup screen 3): Tasks, Chat with Buddy, Echoes, and "Delete my data".
// Buddy has no accounts (anonymous token + invite code), so there's no "log out": deleting wipes
// everything on the server and starts a fresh identity.

import { usePathname, useRouter, type Href } from 'expo-router';
import { useMemo, useState } from 'react';
import { Alert, Modal, Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, SlideInLeft } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { SketchButton, Txt } from '@/components/sketch';
import { Border, Wobble, type Colors } from '@/constants/sketch';
import { useModalBottomInset } from '@/hooks/use-modal-inset';
import { useColors, useTheme, useThemedStyles } from '@/hooks/use-theme';
import { useRestart, useToken } from '@/hooks/use-session';
import { api } from '@/lib/api';

const ITEMS: { label: string; href: Href; match: (path: string) => boolean }[] = [
  { label: 'Tasks', href: '/', match: (p) => p === '/' || p.startsWith('/task') },
  { label: 'Chat with Buddy', href: '/chat', match: (p) => p === '/chat' },
  { label: 'Echoes', href: '/echoes', match: (p) => p === '/echoes' },
];

/** The round sketchy menu button for screen headers; owns the menu's open state. */
export function MenuButton() {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  const [open, setOpen] = useState(false);
  return (
    <>
      <SketchButton tone="card" wobble="round" lifted accessibilityLabel="Open menu" onPress={() => setOpen(true)} style={styles.menuButton}>
        <Svg width={22} height={18} viewBox="0 0 22 18">
          <Path d="M2 3 Q11 1.5 20 3 M2 9 Q11 10.5 20 9 M2 15 Q11 13.8 20 15" fill="none" stroke={c.ink} strokeWidth={2.6} strokeLinecap="round" />
        </Svg>
      </SketchButton>
      <SideMenu visible={open} onClose={() => setOpen(false)} />
    </>
  );
}

function SideMenu({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  const router = useRouter();
  const path = usePathname();
  const insets = useSafeAreaInsets();
  const bottomInset = useModalBottomInset();
  const token = useToken();
  const restart = useRestart();
  const client = useMemo(() => api(token), [token]);
  const [deleting, setDeleting] = useState(false);

  function go(href: Href) {
    onClose();
    router.replace(href);
  }

  function confirmDelete() {
    Alert.alert(
      'Delete everything?',
      'This wipes your tasks, chats and everything Buddy has learned about you. It can’t be undone.',
      [
        { text: 'Keep it', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setDeleting(true);
            try {
              await client.deleteMe();
              onClose();
              await restart();
            } catch {
              Alert.alert('Couldn’t delete right now', 'Check your connection and try again.');
            } finally {
              setDeleting(false);
            }
          },
        },
      ],
    );
  }

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose} statusBarTranslucent>
      <Animated.View entering={FadeIn.duration(160)} style={StyleSheet.absoluteFill}>
        <Pressable style={styles.backdrop} onPress={onClose} accessibilityRole="button" accessibilityLabel="Close menu" />
      </Animated.View>
      <Animated.View
        entering={SlideInLeft.duration(240)}
        accessibilityViewIsModal
        style={[styles.panel, { paddingTop: insets.top + 16, paddingBottom: bottomInset + 8 }]}>
        <View style={styles.brandRow}>
          <Txt variant="title">
            buddy<Txt variant="title" style={{ color: c.deep }}>.</Txt>
          </Txt>
          <SketchButton tone="plain" wobble="round" lifted={false} accessibilityLabel="Close menu" onPress={onClose} style={styles.close}>
            <Svg width={16} height={16} viewBox="0 0 16 16">
              <Path d="M2 2 L14 14 M14 2 L2 14" stroke={c.ink} strokeWidth={2.6} strokeLinecap="round" />
            </Svg>
          </SketchButton>
        </View>

        <View style={styles.items}>
          {ITEMS.map((item, i) => {
            const current = item.match(path);
            return (
              <SketchButton
                key={item.label}
                label={item.label}
                tone={current ? 'pop' : 'plain'}
                wobble={(['a', 'b', 'c'] as const)[i]}
                lifted={current}
                accessibilityState={{ selected: current }}
                onPress={() => go(item.href)}
                style={styles.item}
                textStyle={styles.itemText}
              />
            );
          })}
        </View>

        <View style={styles.bottom}>
          <Txt variant="hand" style={styles.around}>I’m around if you get stuck!</Txt>
          <View style={styles.peek}>
            <BuddyBlob width={150} label="Buddy peeking up from the bottom of the menu" />
          </View>
          {/* The link onboarding promises ("menu → Delete my data"). The panel's bottom padding keeps it clear of
              on-screen nav buttons (hooks/use-modal-inset.ts). */}
          <Pressable onPress={confirmDelete} disabled={deleting} accessibilityRole="button" style={styles.delete} hitSlop={8}>
            <Txt variant="small" style={styles.deleteText}>{deleting ? 'Deleting…' : 'Delete my data'}</Txt>
          </Pressable>
        </View>
      </Animated.View>
    </Modal>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
  menuButton: { width: 48, height: 48, paddingHorizontal: 0 },
  backdrop: { flex: 1, backgroundColor: c.scrim },
  panel: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    width: '78%',
    maxWidth: 320,
    paddingHorizontal: 18,
    backgroundColor: c.card,
    borderRightWidth: Border + 0.5,
    borderColor: c.ink,
    borderTopRightRadius: 28,
    borderBottomRightRadius: 34,
    boxShadow: `8px 0px 0px ${c.deep}`,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  close: { width: 44, height: 44, minHeight: 44, paddingHorizontal: 0, ...Wobble.round },
  items: { marginTop: 28, gap: 12 },
  item: { minHeight: 56, alignItems: 'flex-start' },
  itemText: { fontSize: 26, lineHeight: 30 },
  bottom: { marginTop: 'auto', alignItems: 'center', gap: 8 },
  around: { textAlign: 'center', fontSize: 21 },
  peek: { height: 84, overflow: 'hidden' },
  delete: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12 },
  // Quiet (it's destructive) but findable: onboarding promises it. 13px was too small to spot (developer, 2026-11-09).
  deleteText: { fontSize: 15, lineHeight: 20, textDecorationLine: 'underline', color: c.muted },
});

/** The header on top-level screens: menu button, "buddy." in the middle. */
export function BrandHeader({ topInset }: { topInset: number }) {
  const c = useColors();
  return (
    <View style={[headerStyles.row, { paddingTop: topInset + 12 }]}>
      <MenuButton />
      <Txt variant="title">
        buddy<Txt variant="title" style={{ color: c.deep }}>.</Txt>
      </Txt>
      <ThemeToggle />
    </View>
  );
}

/** Top-right of the header: Buddy's light look (Dusk) or dark look (Dusk Night). It shows the look you'd switch to. */
function ThemeToggle() {
  const { dark, toggle, colors: c } = useTheme();
  const styles = useThemedStyles(makeStyles);
  return (
    <SketchButton
      tone="card"
      wobble="round"
      lifted
      onPress={toggle}
      accessibilityLabel={dark ? 'Switch to the light look' : 'Switch to the dark look'}
      style={styles.menuButton}>
      <Svg width={22} height={22} viewBox="0 0 22 22">
        {dark ? (
          <>
            <Circle cx={11} cy={11} r={4.2} fill="none" stroke={c.ink} strokeWidth={2.4} />
            <Path
              d="M11 1.8 V4.2 M11 17.8 V20.2 M1.8 11 H4.2 M17.8 11 H20.2 M4.5 4.5 L6.2 6.2 M15.8 15.8 L17.5 17.5 M4.5 17.5 L6.2 15.8 M15.8 6.2 L17.5 4.5"
              stroke={c.ink}
              strokeWidth={2.2}
              strokeLinecap="round"
            />
          </>
        ) : (
          <Path d="M14.5 2.5 A8.6 8.6 0 1 0 19.5 15.5 A6.8 6.8 0 1 1 14.5 2.5 Z" fill="none" stroke={c.ink} strokeWidth={2.4} strokeLinejoin="round" />
        )}
      </Svg>
    </SketchButton>
  );
}

const headerStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingBottom: 8 },
});
