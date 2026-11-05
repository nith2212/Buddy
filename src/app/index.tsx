// Home: just the task list (mockup screen 2). Tap a task to open its own chat.

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Pressable, RefreshControl, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { Checkbox } from '@/components/checkbox';
import { BrandHeader } from '@/components/side-menu';
import { Card, Chip, SketchButton, Txt } from '@/components/sketch';
import { Border, Font, Ink, Palette, Wobble } from '@/constants/sketch';
import { useToken } from '@/hooks/use-session';
import { api, Task } from '@/lib/api';
import { DUE_OPTIONS, DueOption, dueDateFor, formatDue, isOverdue } from '@/lib/dates';

const CARD_WOBBLES = ['a', 'b', 'c'] as const;

export default function TaskListScreen() {
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [title, setTitle] = useState('');
  const [due, setDue] = useState<DueOption>('none');
  const [adding, setAdding] = useState(false);
  const [addFailed, setAddFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setTasks(await client.listTasks());
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    }
  }, [client]);

  // Refetch whenever this screen regains focus, so steps ticked in a chat show up here.
  useFocusEffect(
    useCallback(() => {
      load();
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
      setDue('none');
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
          accessibilityRole="button"
          accessibilityLabel={`Open ${item.title ?? 'task'}`}
          style={({ pressed }) => [styles.rowCard, pressed && styles.pressed]}>
          <Card wobble={CARD_WOBBLES[index % 3]} style={styles.cardBody}>
            <Txt variant="bold" style={done ? styles.struck : undefined}>{item.title ?? 'Untitled'}</Txt>
            <View style={styles.meta}>
              {dueLabel ? (
                <View style={[styles.dueChip, { backgroundColor: soon ? Palette.soft : done ? Palette.pop : Palette.bg }]}>
                  <Txt variant="hand" style={styles.dueText}>{dueLabel}</Txt>
                </View>
              ) : null}
              {item.subtasks.length ? <Txt variant="small">{`${stepsDone}/${item.subtasks.length} steps`}</Txt> : null}
            </View>
          </Card>
        </Pressable>
      </View>
    );
  }

  const listHeader = (
    <View style={styles.tasksHeading}>
      <Txt variant="title" accessibilityRole="header">Tasks:</Txt>
      <Svg width={96} height={10} viewBox="0 0 96 10">
        <Path d="M2 6 Q14 1 26 6 T50 6 T74 6 T94 5" fill="none" stroke={Palette.deep} strokeWidth={3} strokeLinecap="round" />
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
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} colors={[Palette.deep]} />}
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
            placeholderTextColor={Palette.muted}
            accessibilityLabel="New task"
            maxLength={200}
            returnKeyType="done"
            onSubmitEditing={addTask}
            style={styles.input}
          />
          <SketchButton label={adding ? '…' : '+ Add'} onPress={addTask} disabled={!title.trim() || adding} accessibilityLabel="Add task" />
        </View>
        <View style={styles.chips} accessibilityLabel="Due date">
          {DUE_OPTIONS.map((option) => (
            <Chip key={option.key} label={option.label} selected={option.key === due} onPress={() => setDue(option.key)} />
          ))}
        </View>
        {addFailed ? <Txt variant="small" style={{ color: Palette.danger }}>Couldn’t add that. Check your connection and try again.</Txt> : null}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Palette.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24 },
  list: { paddingHorizontal: 24, paddingTop: 8, paddingBottom: 24 },
  tasksHeading: { marginBottom: 16 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  rowCard: { flex: 1, marginRight: 6 },
  pressed: { transform: [{ translateX: 2 }, { translateY: 2 }] },
  cardBody: { paddingHorizontal: 16, paddingVertical: 12, gap: 6 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  dueChip: { borderWidth: 2, borderColor: Ink, paddingHorizontal: 10, ...Wobble.c },
  dueText: { fontSize: 16, lineHeight: 21 },
  struck: { textDecorationLine: 'line-through' },
  empty: { alignItems: 'center', gap: 12, paddingVertical: 40 },
  emptyText: { textAlign: 'center', maxWidth: 280 },
  composer: {
    paddingHorizontal: 20,
    paddingTop: 14,
    gap: 12,
    backgroundColor: Palette.card,
    borderTopWidth: Border,
    borderStyle: 'dashed',
    borderColor: Ink,
  },
  inputRow: { flexDirection: 'row', gap: 10 },
  input: {
    flex: 1,
    minHeight: 48,
    paddingHorizontal: 14,
    fontFamily: Font.semi,
    fontSize: 16,
    color: Ink,
    backgroundColor: Palette.white,
    borderWidth: Border,
    borderColor: Ink,
    ...Wobble.c,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
});
