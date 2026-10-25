import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Checkbox } from '@/components/checkbox';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Accent, Danger, MaxContentWidth, Spacing } from '@/constants/theme';
import { useToken } from '@/hooks/use-session';
import { useTheme } from '@/hooks/use-theme';
import { api, Task } from '@/lib/api';
import { DUE_OPTIONS, DueOption, dueDateFor, formatDue, isOverdue } from '@/lib/dates';

export default function TaskListScreen() {
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const theme = useTheme();
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

  // Refetch whenever this screen regains focus, so steps ticked in the chat screen show up here.
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

  const composer = (
    <View style={styles.composer}>
      <ThemedText type="subtitle">Your tasks</ThemedText>
      <View style={[styles.inputRow, { backgroundColor: theme.backgroundElement }]}>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder="Add a task"
          placeholderTextColor={theme.textSecondary}
          maxLength={200}
          returnKeyType="done"
          onSubmitEditing={addTask}
          style={[styles.input, { color: theme.text }]}
        />
        <Pressable
          onPress={addTask}
          disabled={!title.trim() || adding}
          accessibilityRole="button"
          accessibilityLabel="Add task"
          style={[styles.addButton, (!title.trim() || adding) && styles.disabled]}>
          <ThemedText style={styles.addButtonText}>{adding ? '…' : 'Add'}</ThemedText>
        </Pressable>
      </View>
      <View style={styles.chips}>
        {DUE_OPTIONS.map((option) => {
          const selected = option.key === due;
          return (
            <Pressable
              key={option.key}
              onPress={() => setDue(option.key)}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              style={[styles.chip, { backgroundColor: selected ? Accent : theme.backgroundElement }]}>
              <ThemedText type="small" style={{ color: selected ? '#ffffff' : theme.text }}>
                {option.label}
              </ThemedText>
            </Pressable>
          );
        })}
      </View>
      {addFailed ? (
        <ThemedText type="small" style={{ color: Danger }}>
          Couldn&apos;t add that. Check your connection and try again.
        </ThemedText>
      ) : null}
    </View>
  );

  function renderItem({ item }: { item: Task }) {
    const done = item.status === 'done';
    const dueLabel = done ? null : formatDue(item.due_date);
    const overdue = !done && isOverdue(item.due_date);
    const stepsDone = item.subtasks.filter((s) => s.done).length;
    const details = [dueLabel, item.subtasks.length ? `${stepsDone}/${item.subtasks.length} steps` : null]
      .filter(Boolean)
      .join('  ·  ');

    return (
      <Pressable
        onPress={() => openTask(item.id)}
        accessibilityRole="button"
        accessibilityLabel={`Open ${item.title ?? 'task'}`}
        style={[styles.row, { backgroundColor: theme.backgroundElement }]}>
        <Checkbox checked={done} onPress={() => toggleDone(item)} label={done ? 'Mark as not done' : 'Mark as done'} />
        <View style={styles.rowText}>
          <ThemedText style={done ? styles.struck : undefined} themeColor={done ? 'textSecondary' : 'text'}>
            {item.title ?? 'Untitled'}
          </ThemedText>
          {details ? (
            <ThemedText type="small" themeColor="textSecondary" style={overdue ? { color: Danger } : undefined}>
              {details}
            </ThemedText>
          ) : null}
        </View>
        <ThemedText themeColor="textSecondary">›</ThemedText>
      </Pressable>
    );
  }

  return (
    <ThemedView style={styles.screen}>
      {tasks === null && !loadFailed ? (
        <View style={styles.center}>
          <ActivityIndicator />
        </View>
      ) : tasks === null ? (
        <View style={styles.center}>
          <ThemedText>Couldn&apos;t reach Buddy.</ThemedText>
          <Pressable onPress={load} accessibilityRole="button">
            <ThemedText type="linkPrimary">Try again</ThemedText>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={sorted}
          keyExtractor={(t) => String(t.id)}
          renderItem={renderItem}
          ListHeaderComponent={composer}
          ListEmptyComponent={
            <ThemedText themeColor="textSecondary" style={styles.empty}>
              Nothing here yet. Add a task above and Buddy will check in when it&apos;s time.
            </ThemedText>
          }
          ItemSeparatorComponent={() => <View style={{ height: Spacing.two }} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={[
            styles.content,
            { paddingTop: insets.top + Spacing.three, paddingBottom: insets.bottom + Spacing.four },
          ]}
        />
      )}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.two },
  content: {
    paddingHorizontal: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  composer: { gap: Spacing.three, marginBottom: Spacing.three },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: Spacing.three,
    paddingLeft: Spacing.three,
    paddingRight: Spacing.two,
    paddingVertical: Spacing.one,
    gap: Spacing.two,
  },
  input: { flex: 1, fontSize: 16, paddingVertical: Spacing.two },
  addButton: {
    backgroundColor: Accent,
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
  },
  addButtonText: { color: '#ffffff', fontWeight: '600' },
  disabled: { opacity: 0.4 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.two },
  chip: { borderRadius: Spacing.four, paddingHorizontal: Spacing.three, paddingVertical: Spacing.one + 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    borderRadius: Spacing.three,
    padding: Spacing.three,
  },
  rowText: { flex: 1, gap: 2 },
  struck: { textDecorationLine: 'line-through' },
  empty: { textAlign: 'center', paddingVertical: Spacing.five },
});
