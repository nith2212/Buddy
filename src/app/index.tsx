// Home: just the task list (mockup screen 2). Tap a task to open its own chat; long-press it, or tap its pencil,
// to edit or delete it.

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { AppState, FlatList, Keyboard, KeyboardAvoidingView, Pressable, RefreshControl, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { Checkbox } from '@/components/checkbox';
import { DuePicker } from '@/components/due-picker';
import { EditTaskSheet } from '@/components/edit-task-sheet';
import { BrandHeader } from '@/components/side-menu';
import { Card, SketchButton, Txt } from '@/components/sketch';
import { Border, Font, Wobble, type Colors } from '@/constants/sketch';
import { useColors, useThemedStyles } from '@/hooks/use-theme';
import { useToken } from '@/hooks/use-session';
import { api, Task } from '@/lib/api';
import { DayKey, dueDateFor, formatDue, isOverdue } from '@/lib/dates';

const CARD_WOBBLES = ['a', 'b', 'c'] as const;

export default function TaskListScreen() {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [title, setTitle] = useState('');
  const [due, setDue] = useState<DayKey | null>(null);
  const [adding, setAdding] = useState(false);
  const [addFailed, setAddFailed] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);

  const load = useCallback(async () => {
    try {
      setTasks(await client.listTasks());
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    }
  }, [client]);

  // Refetch whenever this screen regains focus, so steps ticked in a chat show up here, and whenever the app
  // comes back to the front, so a Done tapped on a notification shows without pulling to refresh.
  useFocusEffect(
    useCallback(() => {
      load();
      const sub = AppState.addEventListener('change', (state) => {
        if (state === 'active') load();
      });
      return () => sub.remove();
    }, [load]),
  );

  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  async function addTask() {
    const trimmed = title.trim();
    if (!trimmed || adding) return;
    setAdding(true);
    setAddFailed(false);
    try {
      const created = await client.createTask(trimmed, dueDateFor(due));
      setTasks((prev) => [created, ...(prev ?? [])]);
      setTitle('');
      setDue(null);
    } catch {
      setAddFailed(true);
    } finally {
      setAdding(false);
    }
  }

  async function toggleDone(task: Task) {
    const next = task.status === 'done' ? 'open' : 'done';
    const replace = (t: Task) => setTasks((prev) => prev?.map((x) => (x.id === t.id ? t : x)) ?? prev);
    replace({ ...task, status: next });
    try {
      replace(await client.updateTask(task.id, { status: next }));
    } catch {
      replace(task);
    }
  }

  const openTask = (id: number) => router.push({ pathname: '/task/[id]', params: { id: String(id) } });
  const replaceTask = (t: Task) => setTasks((prev) => prev?.map((x) => (x.id === t.id ? t : x)) ?? prev);
  const dropTask = (id: number) => setTasks((prev) => prev?.filter((x) => x.id !== id) ?? prev);

  // Open tasks first; the server already returns newest first within each group.
  const sorted = tasks ? [...tasks].sort((a, b) => Number(a.status === 'done') - Number(b.status === 'done')) : [];

  function renderItem({ item, index }: { item: Task; index: number }) {
    const done = item.status === 'done';
    const dueLabel = done ? 'done!' : formatDue(item.due_date);
    const soon = !done && item.due_date !== null && (isOverdue(item.due_date) || /today|tomorrow/i.test(dueLabel ?? ''));
    const stepsDone = item.subtasks.filter((s) => s.done).length;
    return (
      <View style={styles.row}>
        <Checkbox checked={done} onPress={() => toggleDone(item)} label={`${done ? 'Mark not done' : 'Mark done'}: ${item.title ?? 'task'}`} />
        <Pressable
          onPress={() => openTask(item.id)}
          onLongPress={() => setEditing(item)}
          accessibilityRole="button"
          accessibilityLabel={`Open ${item.title ?? 'task'}`}
          accessibilityHint="Long-press to edit or delete"
          style={({ pressed }) => [styles.rowCard, pressed && styles.pressed]}>
          <Card wobble={CARD_WOBBLES[index % 3]} style={styles.cardBody}>
            <View style={styles.cardText}>
              <Txt variant="bold" style={done ? styles.struck : undefined}>{item.title ?? 'Untitled'}</Txt>
              <View style={styles.meta}>
                {dueLabel ? (
                  <View style={[styles.dueChip, { backgroundColor: soon ? c.soft : done ? c.pop : c.bg }]}>
                    <Txt variant="hand" style={[styles.dueText, (soon || done) && { color: c.onPop }]}>{dueLabel}</Txt>
                  </View>
                ) : null}
                {item.subtasks.length ? <Txt variant="small">{`${stepsDone}/${item.subtasks.length} steps`}</Txt> : null}
              </View>
            </View>
            <Pressable
              onPress={() => setEditing(item)}
              accessibilityRole="button"
              accessibilityLabel={`Edit ${item.title ?? 'task'}`}
              hitSlop={6}
              style={({ pressed }) => [styles.pencil, pressed && { backgroundColor: c.soft }]}>
              <Svg width={18} height={18} viewBox="0 0 18 18">
                <Path
                  d="M3 15 L3.6 11.6 L11.8 3.4 Q13 2.2 14.3 3.5 Q15.6 4.8 14.4 6 L6.2 14.2 Z M10.6 4.6 L13.2 7.2"
                  fill="none"
                  stroke={c.ink}
                  strokeWidth={1.9}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </Svg>
            </Pressable>
          </Card>
        </Pressable>
      </View>
    );
  }

  const listHeader = (
    <View style={styles.tasksHeading}>
      <Txt variant="title" accessibilityRole="header">Tasks:</Txt>
      <Svg width={96} height={10} viewBox="0 0 96 10">
        <Path d="M2 6 Q14 1 26 6 T50 6 T74 6 T94 5" fill="none" stroke={c.deep} strokeWidth={3} strokeLinecap="round" />
      </Svg>
    </View>
  );

  return (
    <KeyboardAvoidingView style={styles.screen} behavior="padding">
      <BrandHeader topInset={insets.top} />

      {tasks === null && !loadFailed ? (
        <View style={styles.center}>
          <BuddyBlob width={140} label="Buddy, fetching your tasks" />
          <Txt variant="hand">Getting your tasks…</Txt>
        </View>
      ) : tasks === null ? (
        <View style={styles.center}>
          <BuddyBlob width={140} mood="worried" label="Buddy, worried: can't reach the server" />
          <Txt variant="heading">Couldn’t reach Buddy.</Txt>
          <SketchButton label="Try again" onPress={load} />
        </View>
      ) : (
        <FlatList
          data={sorted}
          keyExtractor={(t) => String(t.id)}
          renderItem={renderItem}
          ListHeaderComponent={listHeader}
          ListEmptyComponent={
            <View style={styles.empty}>
              <BuddyBlob width={130} label="Buddy" />
              <Txt style={styles.emptyText}>Nothing here yet. Add a task below and Buddy will check in when it’s time.</Txt>
            </View>
          }
          ItemSeparatorComponent={() => <View style={{ height: 16 }} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} colors={[c.deep]} progressBackgroundColor={c.card} />}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.list}
        />
      )}

      <View style={[styles.composer, { paddingBottom: insets.bottom + 16 }]}>
        <View style={styles.inputRow}>
          <TextInput
            value={title}
            onChangeText={setTitle}
            placeholder="Add a task…"
            placeholderTextColor={c.muted}
            accessibilityLabel="New task"
            maxLength={200}
            returnKeyType="done"
            onSubmitEditing={addTask}
            style={styles.input}
          />
          <SketchButton label={adding ? '…' : '+ Add'} onPress={addTask} disabled={!title.trim() || adding} accessibilityLabel="Add task" />
        </View>
        <DuePicker value={due} onChange={setDue} onOpenCalendar={Keyboard.dismiss} />
        {addFailed ? <Txt variant="small" style={{ color: c.danger }}>Couldn’t add that. Check your connection and try again.</Txt> : null}
      </View>

      {editing ? (
        <EditTaskSheet
          task={editing}
          client={client}
          onClose={() => setEditing(null)}
          onSaved={replaceTask}
          onDeleted={dropTask}
        />
      ) : null}
    </KeyboardAvoidingView>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
  screen: { flex: 1, backgroundColor: c.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24 },
  list: { paddingHorizontal: 24, paddingTop: 8, paddingBottom: 24 },
  tasksHeading: { marginBottom: 16 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  rowCard: { flex: 1, marginRight: 6 },
  pressed: { transform: [{ translateX: 2 }, { translateY: 2 }] },
  cardBody: { paddingLeft: 16, paddingRight: 6, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 6 },
  cardText: { flex: 1, gap: 6 },
  pencil: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 12 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  dueChip: { borderWidth: 2, borderColor: c.ink, paddingHorizontal: 10, ...Wobble.c },
  dueText: { fontSize: 16, lineHeight: 21 },
  struck: { textDecorationLine: 'line-through' },
  empty: { alignItems: 'center', gap: 12, paddingVertical: 40 },
  emptyText: { textAlign: 'center', maxWidth: 280 },
  composer: {
    paddingHorizontal: 20,
    paddingTop: 14,
    gap: 12,
    backgroundColor: c.card,
    borderTopWidth: Border,
    borderStyle: 'dashed',
    borderColor: c.ink,
  },
  inputRow: { flexDirection: 'row', gap: 10 },
  input: {
    flex: 1,
    minHeight: 48,
    paddingHorizontal: 14,
    fontFamily: Font.semi,
    fontSize: 16,
    color: c.ink,
    backgroundColor: c.white,
    borderWidth: Border,
    borderColor: c.ink,
    ...Wobble.c,
  },
});
