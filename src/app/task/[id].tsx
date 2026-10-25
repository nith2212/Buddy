import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Pressable,
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
import { api, ChatTurn, Subtask, Task } from '@/lib/api';
import { formatDue, isOverdue } from '@/lib/dates';

export default function TaskChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const taskId = Number(id);
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const theme = useTheme();
  const insets = useSafeAreaInsets();

  const [task, setTask] = useState<Task | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false); // also true while Buddy writes the opening message
  const [sendFailed, setSendFailed] = useState(false);
  const [newStep, setNewStep] = useState('');

  const listRef = useRef<FlatList<ChatTurn>>(null);
  const stickToEnd = useRef(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [loadedTask, history] = await Promise.all([client.getTask(taskId), client.chatHistory(taskId)]);
        if (cancelled) return;
        setTask(loadedTask);
        setTurns(history);
        setLoadState('ready');

        if (history.length === 0) {
          // First time in this chat: Buddy speaks first (this is what "Yes, let's chat" leads to).
          setSending(true);
          try {
            const opening = await client.initiate(taskId);
            if (!cancelled) setTurns([{ role: 'assistant', content: opening.reply }]);
          } catch {
            // Not fatal: the user can just type first.
          } finally {
            if (!cancelled) setSending(false);
          }
        }
      } catch {
        if (!cancelled) setLoadState('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, taskId]);

  // Scroll to the newest message once the list has actually laid it out.
  useEffect(() => {
    stickToEnd.current = true;
  }, [turns.length, sending]);

  function goBack() {
    if (router.canGoBack()) router.back();
    else router.replace('/');
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    setSendFailed(false);
    setSending(true);
    setTurns((prev) => [...prev, { role: 'user', content: text }]);
    try {
      const res = await client.chat(taskId, text);
      setTurns((prev) => [...prev, { role: 'assistant', content: res.reply }]);
    } catch {
      setTurns((prev) => prev.slice(0, -1)); // take the unsent message back out…
      setInput(text); // …and give it back to the user to resend
      setSendFailed(true);
    } finally {
      setSending(false);
    }
  }

  const patchSubtasks = (fn: (subtasks: Subtask[]) => Subtask[]) =>
    setTask((prev) => (prev ? { ...prev, subtasks: fn(prev.subtasks) } : prev));

  async function toggleSubtask(sub: Subtask) {
    patchSubtasks((list) => list.map((s) => (s.id === sub.id ? { ...s, done: !s.done } : s)));
    try {
      await client.updateSubtask(taskId, sub.id, { done: !sub.done });
    } catch {
      patchSubtasks((list) => list.map((s) => (s.id === sub.id ? sub : s)));
    }
  }

  async function addStep() {
    const title = newStep.trim();
    if (!title) return;
    setNewStep('');
    try {
      const created = await client.createSubtask(taskId, title);
      patchSubtasks((list) => [...list, created]);
    } catch {
      setNewStep(title);
    }
  }

  const header = (
    <View style={styles.header}>
      {task && formatDue(task.due_date) && task.status !== 'done' ? (
        <ThemedText type="small" themeColor="textSecondary" style={isOverdue(task.due_date) ? { color: Danger } : undefined}>
          {formatDue(task.due_date)}
        </ThemedText>
      ) : null}

      <View style={[styles.stepsCard, { backgroundColor: theme.backgroundElement }]}>
        <ThemedText type="smallBold">Steps</ThemedText>
        {task && task.subtasks.length === 0 ? (
          <ThemedText type="small" themeColor="textSecondary">
            Breaking it into small steps can help. Totally optional.
          </ThemedText>
        ) : null}
        {[...(task?.subtasks ?? [])]
          .sort((a, b) => a.position - b.position)
          .map((s) => (
            <View key={s.id} style={styles.stepRow}>
              <Checkbox checked={s.done} onPress={() => toggleSubtask(s)} label={s.done ? `Mark "${s.title}" not done` : `Mark "${s.title}" done`} />
              <ThemedText style={[styles.stepTitle, s.done && styles.struck]} themeColor={s.done ? 'textSecondary' : 'text'}>
                {s.title}
              </ThemedText>
            </View>
          ))}
        <View style={styles.stepRow}>
          <TextInput
            value={newStep}
            onChangeText={setNewStep}
            placeholder="Add a step"
            placeholderTextColor={theme.textSecondary}
            maxLength={200}
            returnKeyType="done"
            onSubmitEditing={addStep}
            style={[styles.stepInput, { color: theme.text, borderColor: theme.backgroundSelected }]}
          />
          <Pressable onPress={addStep} disabled={!newStep.trim()} accessibilityRole="button" accessibilityLabel="Add step">
            <ThemedText type="linkPrimary" style={!newStep.trim() && styles.disabled}>
              Add
            </ThemedText>
          </Pressable>
        </View>
      </View>
    </View>
  );

  function renderTurn({ item }: { item: ChatTurn }) {
    const mine = item.role === 'user';
    return (
      <View style={[styles.bubble, mine ? styles.mine : styles.theirs, { backgroundColor: mine ? Accent : theme.backgroundElement }]}>
        <ThemedText style={mine ? styles.mineText : undefined}>{item.content}</ThemedText>
      </View>
    );
  }

  const topBar = (
    <View style={[styles.topBar, { paddingTop: insets.top + Spacing.two }]}>
      <Pressable onPress={goBack} hitSlop={12} accessibilityRole="button" accessibilityLabel="Back">
        <ThemedText type="linkPrimary">‹ Back</ThemedText>
      </Pressable>
      <ThemedText type="smallBold" numberOfLines={1} style={styles.topTitle}>
        {task?.title ?? ''}
      </ThemedText>
      <View style={styles.topSpacer} />
    </View>
  );

  if (loadState !== 'ready') {
    return (
      <ThemedView style={styles.screen}>
        {topBar}
        <View style={styles.center}>
          {loadState === 'loading' ? (
            <ActivityIndicator />
          ) : (
            <ThemedText>Couldn&apos;t open this task.</ThemedText>
          )}
        </View>
      </ThemedView>
    );
  }

  return (
    <ThemedView style={styles.screen}>
      {topBar}
      <KeyboardAvoidingView style={styles.screen} behavior="padding">
        <FlatList
          ref={listRef}
          data={turns}
          keyExtractor={(_, i) => String(i)}
          renderItem={renderTurn}
          ListHeaderComponent={header}
          ListFooterComponent={
            sending ? (
              <View style={[styles.bubble, styles.theirs, { backgroundColor: theme.backgroundElement }]}>
                <ThemedText themeColor="textSecondary">Buddy is typing…</ThemedText>
              </View>
            ) : null
          }
          ItemSeparatorComponent={() => <View style={{ height: Spacing.two }} />}
          onContentSizeChange={() => {
            if (stickToEnd.current) {
              listRef.current?.scrollToEnd({ animated: true });
              stickToEnd.current = false;
            }
          }}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.content}
        />
        {sendFailed ? (
          <ThemedText type="small" style={[styles.error, { color: Danger }]}>
            Couldn&apos;t send that. Your message is back in the box. Try again.
          </ThemedText>
        ) : null}
        <View style={[styles.inputBar, { paddingBottom: insets.bottom + Spacing.two, borderTopColor: theme.backgroundSelected }]}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Message Buddy"
            placeholderTextColor={theme.textSecondary}
            maxLength={1000}
            multiline
            style={[styles.messageInput, { color: theme.text, backgroundColor: theme.backgroundElement }]}
          />
          <Pressable
            onPress={send}
            disabled={!input.trim() || sending}
            accessibilityRole="button"
            accessibilityLabel="Send message"
            style={[styles.sendButton, (!input.trim() || sending) && styles.disabled]}>
            <ThemedText style={styles.sendText}>Send</ThemedText>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
    gap: Spacing.three,
  },
  topTitle: { flex: 1, textAlign: 'center' },
  topSpacer: { width: 52 },
  content: {
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  header: { gap: Spacing.three, marginBottom: Spacing.three },
  stepsCard: { borderRadius: Spacing.three, padding: Spacing.three, gap: Spacing.two },
  stepRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three },
  stepTitle: { flex: 1 },
  stepInput: {
    flex: 1,
    fontSize: 16,
    paddingVertical: Spacing.one,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  struck: { textDecorationLine: 'line-through' },
  bubble: { maxWidth: '85%', borderRadius: Spacing.three, paddingHorizontal: Spacing.three, paddingVertical: Spacing.two },
  mine: { alignSelf: 'flex-end' },
  theirs: { alignSelf: 'flex-start' },
  mineText: { color: '#ffffff' },
  error: { paddingHorizontal: Spacing.three, paddingBottom: Spacing.one },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingTop: Spacing.two,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  messageInput: {
    flex: 1,
    maxHeight: 120,
    fontSize: 16,
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
  },
  sendButton: {
    backgroundColor: Accent,
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two + 2,
  },
  sendText: { color: '#ffffff', fontWeight: '600' },
  disabled: { opacity: 0.4 },
});
