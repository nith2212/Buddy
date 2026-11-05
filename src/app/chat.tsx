// "Chat with Buddy" from the menu (mockup screen 4): Buddy asks which task, then the chat continues
// inside that task's own thread (one conversation per task), with the reason chips open.

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BuddyBlob } from '@/components/buddy-blob';
import { BrandHeader } from '@/components/side-menu';
import { Bubble, Chip, SketchButton, Txt } from '@/components/sketch';
import { Palette } from '@/constants/sketch';
import { useToken } from '@/hooks/use-session';
import { api, Task } from '@/lib/api';

const MAX_CHOICES = 8;

export default function ChatPickerScreen() {
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setTasks((await client.listTasks()).filter((t) => t.status === 'open'));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [client]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const open = (task: Task) =>
    router.push({ pathname: '/task/[id]', params: { id: String(task.id), ask: '1' } });

  return (
    <View style={styles.screen}>
      <BrandHeader topInset={insets.top} />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.turn}>
          <BuddyBlob width={40} animated={false} style={styles.avatar} />
          <View style={styles.stack}>
            {failed ? (
              <>
                <Bubble from="buddy">I can’t reach your tasks right now. Check your connection?</Bubble>
                <SketchButton label="Try again" onPress={load} style={styles.retry} />
              </>
            ) : tasks === null ? (
              <Bubble from="buddy">One sec, looking at your tasks…</Bubble>
            ) : tasks.length === 0 ? (
              <>
                <Bubble from="buddy">Hey there! Add a task first, and I’ll help you start it whenever you’re ready.</Bubble>
                <SketchButton label="Go to tasks" onPress={() => router.replace('/')} style={styles.retry} />
              </>
            ) : (
              <>
                <Bubble from="buddy">Hey there! Which task do you need help starting?</Bubble>
                <View style={styles.chips} accessibilityLabel="Pick a task">
                  {tasks.slice(0, MAX_CHOICES).map((t) => (
                    <Chip key={t.id} label={t.title ?? 'Untitled'} onPress={() => open(t)} />
                  ))}
                </View>
              </>
            )}
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Palette.bg },
  content: { paddingHorizontal: 16, paddingTop: 16 },
  turn: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  avatar: { marginTop: 4 },
  stack: { flex: 1, gap: 12, alignItems: 'flex-start' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  retry: { alignSelf: 'flex-start' },
});
