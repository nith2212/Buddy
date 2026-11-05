// The slide-out menu (mockup screen 3): Tasks, Chat with Buddy, Echoes, and "Delete my data".
// Buddy has no accounts (anonymous token + invite code), so there's no "log out": deleting wipes
// everything on the server and starts a fresh identity.

import { usePathname, useRouter, type Href } from 'expo-router';
import { useMemo, useState } from 'react';
import { Alert, Modal, Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, SlideInLeft } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { SketchButton, Txt } from '@/components/sketch';
import { Border, Ink, Palette, Wobble } from '@/constants/sketch';
import { useRestart, useToken } from '@/hooks/use-session';
import { api } from '@/lib/api';

const ITEMS: { label: string; href: Href; match: (path: string) => boolean }[] = [
  { label: 'Tasks', href: '/', match: (p) => p === '/' || p.startsWith('/task') },
  { label: 'Chat with Buddy', href: '/chat', match: (p) => p === '/chat' },
  { label: 'Echoes', href: '/echoes', match: (p) => p === '/echoes' },
];

/** The round sketchy menu button for screen headers; owns the menu's open state. */
export function MenuButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <SketchButton tone="card" wobble="round" lifted accessibilityLabel="Open menu" onPress={() => setOpen(true)} style={styles.menuButton}>
        <Svg width={22} height={18} viewBox="0 0 22 18">
          <Path d="M2 3 Q11 1.5 20 3 M2 9 Q11 10.5 20 9 M2 15 Q11 13.8 20 15" fill="none" stroke={Ink} strokeWidth={2.6} strokeLinecap="round" />
        </Svg>
      </SketchButton>
      <SideMenu visible={open} onClose={() => setOpen(false)} />
    </>
  );
}

function SideMenu({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const router = useRouter();
  const path = usePathname();
  const insets = useSafeAreaInsets();
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
        style={[styles.panel, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 8 }]}>
        <View style={styles.brandRow}>
          <Txt variant="title">
            buddy<Txt variant="title" style={{ color: Palette.deep }}>.</Txt>
          </Txt>
          <SketchButton tone="plain" wobble="round" lifted={false} accessibilityLabel="Close menu" onPress={onClose} style={styles.close}>
            <Svg width={16} height={16} viewBox="0 0 16 16">
              <Path d="M2 2 L14 14 M14 2 L2 14" stroke={Ink} strokeWidth={2.6} strokeLinecap="round" />
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
          <Pressable onPress={confirmDelete} disabled={deleting} accessibilityRole="button" style={styles.delete} hitSlop={8}>
            <Txt variant="small" style={styles.deleteText}>{deleting ? 'Deleting…' : 'Delete my data'}</Txt>
          </Pressable>
        </View>
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  menuButton: { width: 48, height: 48, paddingHorizontal: 0 },
  backdrop: { flex: 1, backgroundColor: 'rgba(42, 34, 56, 0.45)' },
  panel: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    width: '78%',
    maxWidth: 320,
    paddingHorizontal: 18,
    backgroundColor: Palette.card,
    borderRightWidth: Border + 0.5,
    borderColor: Ink,
    borderTopRightRadius: 28,
    borderBottomRightRadius: 34,
    boxShadow: `8px 0px 0px ${Palette.deep}`,
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
  deleteText: { textDecorationLine: 'underline', color: Palette.muted },
});

/** The header on top-level screens: menu button, "buddy." in the middle. */
export function BrandHeader({ topInset }: { topInset: number }) {
  return (
    <View style={[headerStyles.row, { paddingTop: topInset + 12 }]}>
      <MenuButton />
      <Txt variant="title">
        buddy<Txt variant="title" style={{ color: Palette.deep }}>.</Txt>
      </Txt>
      <View style={headerStyles.spacer} />
    </View>
  );
}

const headerStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingBottom: 8 },
  spacer: { width: 48 },
});
