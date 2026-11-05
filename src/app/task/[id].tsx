// One task's own chat (mockup 2a/2b): its steps strip, its whole conversation, and the reason chips.
// No chat yet: Buddy asks "What's in the way?". Chat exists: "stuck again? tell Buddy why" reopens the chips.

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { Checkbox } from '@/components/checkbox';
import { Bubble, Chip, SketchButton, Txt } from '@/components/sketch';
import { Border, Font, Ink, Palette, Wobble } from '@/constants/sketch';
import { useToken } from '@/hooks/use-session';
import { api, ChatTurn, Subtask, Task } from '@/lib/api';
import { formatDue, isOverdue } from '@/lib/dates';
import { Reason, REASONS } from '@/lib/reasons';

export default function TaskChatScreen() {
  const { id, from, ask } = useLocalSearchParams<{ id: string; from?: string; ask?: string }>();
  const taskId = Number(id);
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [task, setTask] = useState<Task | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false); // also true while Buddy writes the opening message
  const [sendFailed, setSendFailed] = useState(false);
  const [newStep, setNewStep] = useState('');
  const [stepsOpen, setStepsOpen] = useState(false);
  const [askAgain, setAskAgain] = useState(ask === '1'); // the reason chips, once a chat exists

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
        setStepsOpen(history.length === 0); // a fresh task shows its steps box; a chat keeps it folded
        setLoadState('ready');

        if (history.length === 0 && from === 'checkin') {
          // Arrived from a check-in ("Yes, let's chat"): they already told us how it feels, so Buddy
          // speaks first. Opened from the task list instead, the reason chips ask first.
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
  }, [client, taskId, from]);

  // Scroll to the newest message once the list has actually laid it out.
  useEffect(() => {
    stickToEnd.current = true;
  }, [turns.length, sending, askAgain]);

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
    setAskAgain(false);
    setTurns((prev) => [...prev, { role: 'user', content: text }]);
    try {
      const res = await client.chat(taskId, { message: text });
      setTurns((prev) => [...prev, { role: 'assistant', content: res.reply }]);
    } catch {
      setTurns((prev) => prev.slice(0, -1)); // take the unsent message back out…
      setInput(text); // …and give it back to the user to resend
      setSendFailed(true);
    } finally {
      setSending(false);
    }
  }

  async function pickReason(reason: Reason) {
    if (sending) return;
    setSendFailed(false);
    setSending(true);
    try {
      // The tap isn't a typed message: Buddy answers it by asking its first question.
      const res = await client.chat(taskId, { reason });
      setTurns((prev) => [...prev, { role: 'assistant', content: res.reply }]);
      setAskAgain(false);
    } catch {
      setSendFailed(true); // chips stay, so they can tap again
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

  const subtasks = [...(task?.subtasks ?? [])].sort((a, b) => a.position - b.position);
  const stepsDone = subtasks.filter((s) => s.done).length;
  const fresh = turns.length === 0 && !sending;
  const dueLabel = task && task.status !== 'done' ? formatDue(task.due_date) : task?.status === 'done' ? 'done!' : null;

  const topBar = (
    <View style={[styles.topBar, { paddingTop: insets.top + 12 }]}>
      <View style={styles.titleRow}>
        <SketchButton tone="plain" wobble="round" lifted={false} onPress={goBack} accessibilityLabel="Back to tasks" style={styles.back}>
          <Svg width={18} height={16} viewBox="0 0 18 16">
            <Path d="M9 2 L2 8 L9 14 M2 8 Q10 7.4 16 8" fill="none" stroke={Ink} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
          </Svg>
        </SketchButton>
        <View style={styles.titleText}>
          <Txt variant="heading" numberOfLines={2} accessibilityRole="header">{task?.title ?? ''}</Txt>
          {dueLabel ? (
            <View style={[styles.dueChip, { backgroundColor: task && isOverdue(task.due_date) ? Palette.soft : Palette.bg }]}>
              <Txt variant="hand" style={styles.dueText}>{dueLabel}</Txt>
            </View>
          ) : null}
        </View>
      </View>

      {task ? (
        <View style={styles.steps}>
          <SketchButton
            tone="soft"
            lifted={false}
            onPress={() => setStepsOpen((o) => !o)}
            accessibilityState={{ expanded: stepsOpen }}
            style={styles.stepsToggle}>
            <Txt variant="hand">{subtasks.length ? `Steps · ${stepsDone} of ${subtasks.length} done` : 'Steps (totally optional)'}</Txt>
            <Txt variant="hand" importantForAccessibility="no">{stepsOpen ? '▴' : '▾'}</Txt>
          </SketchButton>
          {stepsOpen ? (
            <View style={styles.stepsList}>
              {subtasks.map((s) => (
                <View key={s.id} style={styles.stepRow}>
                  <Checkbox size={24} checked={s.done} onPress={() => toggleSubtask(s)} label={s.done ? `Mark "${s.title}" not done` : `Mark "${s.title}" done`} />
                  <Txt variant="semi" style={[styles.stepTitle, s.done && styles.struck]}>{s.title}</Txt>
                </View>
              ))}
              <View style={styles.stepRow}>
                <TextInput
                  value={newStep}
                  onChangeText={setNewStep}
                  placeholder="Add a step…"
                  placeholderTextColor={Palette.muted}
                  accessibilityLabel="Add a step"
                  maxLength={200}
                  returnKeyType="done"
                  onSubmitEditing={addStep}
                  style={[styles.input, styles.stepInput]}
                />
                <SketchButton label="add" lifted={false} onPress={addStep} disabled={!newStep.trim()} accessibilityLabel="Add step" style={styles.smallButton} />
              </View>
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );

  if (loadState !== 'ready') {
    return (
      <View style={styles.screen}>
        {topBar}
        <View style={styles.center}>
          <BuddyBlob width={130} mood={loadState === 'error' ? 'worried' : 'default'} label={loadState === 'error' ? 'Buddy, worried' : 'Buddy'} />
          <Txt variant="hand">{loadState === 'loading' ? 'Opening your chat…' : 'Couldn’t open this task.'}</Txt>
        </View>
      </View>
    );
  }

  function renderTurn({ item }: { item: ChatTurn }) {
    const mine = item.role === 'user';
    return (
      <View style={[styles.turn, mine ? styles.turnMine : styles.turnTheirs]}>
        {mine ? null : <BuddyBlob width={38} animated={false} style={styles.avatar} />}
        <Bubble from={mine ? 'me' : 'buddy'}>{item.content}</Bubble>
      </View>
    );
  }

  const reasonChips = (
    <View style={styles.chips} accessibilityLabel="Why it's hard to start">
      {REASONS.map((r) => (
        <Chip key={r.value} label={r.label} onPress={() => pickReason(r.value)} disabled={sending} />
      ))}
    </View>
  );

  return (
    <KeyboardAvoidingView style={styles.screen} behavior="padding">
      {topBar}
      {fresh ? (
        <View style={styles.freshBody}>
          <BuddyBlob width={128} label="Buddy, curious, waiting for you" />
          <Txt variant="title" style={styles.centerText} accessibilityRole="header">What’s in the way?</Txt>
          <Txt style={[styles.centerText, styles.freshSub]}>Tap the closest one. Buddy will ask a little more before suggesting anything.</Txt>
          <View style={styles.reasonList}>
            {REASONS.map((r, i) => (
              <SketchButton
                key={r.value}
                label={r.label}
                tone="plain"
                wobble={(['a', 'b', 'c', 'b', 'a'] as const)[i]}
                onPress={() => pickReason(r.value)}
                style={styles.reasonButton}
              />
            ))}
          </View>
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={turns}
          keyExtractor={(_, i) => String(i)}
          renderItem={renderTurn}
          ListFooterComponent={
            sending ? (
              <View style={[styles.turn, styles.turnTheirs]}>
                <BuddyBlob width={38} animated={false} style={styles.avatar} />
                <Bubble from="buddy">Buddy is typing…</Bubble>
              </View>
            ) : askAgain ? (
              <View style={styles.askAgain}>
                <Txt variant="hand">What’s in the way this time?</Txt>
                {reasonChips}
              </View>
            ) : null
          }
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          onContentSizeChange={() => {
            if (stickToEnd.current) {
              listRef.current?.scrollToEnd({ animated: true });
              stickToEnd.current = false;
            }
          }}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.content}
        />
      )}

      {sendFailed ? (
        <Txt variant="small" style={styles.error}>
          Couldn’t send that. {turns.length === 0 ? 'Try again.' : 'Your message is back in the box. Try again.'}
        </Txt>
      ) : null}
      <View style={[styles.inputArea, { paddingBottom: insets.bottom + 14 }]}>
        {!fresh && !sending && !askAgain ? (
          <Pressable onPress={() => setAskAgain(true)} accessibilityRole="button" style={({ pressed }) => [styles.stuck, pressed && styles.pressed]}>
            <Txt variant="hand" style={styles.stuckText}>stuck again? tell Buddy why</Txt>
          </Pressable>
        ) : null}
        <View style={styles.inputRow}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder={fresh ? 'Or just tell Buddy…' : 'Message Buddy…'}
            placeholderTextColor={Palette.muted}
            accessibilityLabel="Message Buddy about this task"
            maxLength={1000}
            multiline
            style={[styles.input, styles.messageInput]}
          />
          <SketchButton onPress={send} disabled={!input.trim() || sending} accessibilityLabel="Send message" style={styles.send}>
            <Svg width={22} height={20} viewBox="0 0 22 20">
              <Path d="M2 10 L20 2 L14 18 L11 11 Z" fill="none" stroke={Ink} strokeWidth={2.4} strokeLinejoin="round" />
            </Svg>
          </SketchButton>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Palette.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  centerText: { textAlign: 'center' },
  topBar: {
    paddingHorizontal: 18,
    paddingBottom: 12,
    gap: 10,
    backgroundColor: Palette.card,
    borderBottomWidth: Border,
    borderStyle: 'dashed',
    borderColor: Ink,
  },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  back: { width: 44, height: 44, minHeight: 44, paddingHorizontal: 0 },
  titleText: { flex: 1, gap: 4 },
  dueChip: { alignSelf: 'flex-start', borderWidth: 2, borderColor: Ink, paddingHorizontal: 9, ...Wobble.c },
  dueText: { fontSize: 15, lineHeight: 20 },
  steps: { gap: 8 },
  stepsToggle: { minHeight: 44, flexDirection: 'row', justifyContent: 'space-between', borderWidth: 2 },
  stepsList: { gap: 8, paddingHorizontal: 2 },
  stepRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  stepTitle: { flex: 1 },
  struck: { textDecorationLine: 'line-through' },
  input: {
    fontFamily: Font.semi,
    fontSize: 16,
    color: Ink,
    backgroundColor: Palette.white,
    borderWidth: Border,
    borderColor: Ink,
    paddingHorizontal: 14,
  },
  stepInput: { flex: 1, minHeight: 44, borderWidth: 2, ...Wobble.c },
  smallButton: { minHeight: 44, borderWidth: 2 },
  freshBody: { flex: 1, alignItems: 'center', paddingHorizontal: 22, paddingTop: 20, gap: 10 },
  freshSub: { maxWidth: 290, marginBottom: 6 },
  reasonList: { alignSelf: 'stretch', gap: 10 },
  reasonButton: { backgroundColor: Palette.white, boxShadow: `4px 4px 0px ${Palette.deep}` },
  content: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 16 },
  turn: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  turnMine: { justifyContent: 'flex-end' },
  turnTheirs: { justifyContent: 'flex-start' },
  avatar: { marginTop: 4 },
  askAgain: { marginTop: 14, gap: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  error: { color: Palette.danger, paddingHorizontal: 16, paddingBottom: 4 },
  inputArea: {
    paddingHorizontal: 16,
    paddingTop: 10,
    gap: 10,
    backgroundColor: Palette.card,
    borderTopWidth: Border,
    borderStyle: 'dashed',
    borderColor: Ink,
  },
  stuck: {
    alignSelf: 'center',
    minHeight: 40,
    justifyContent: 'center',
    paddingHorizontal: 14,
    borderWidth: 2,
    borderColor: Ink,
    backgroundColor: Palette.bg,
    ...Wobble.c,
  },
  stuckText: { fontSize: 18 },
  pressed: { transform: [{ translateX: 2 }, { translateY: 2 }] },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 10 },
  messageInput: { flex: 1, minHeight: 50, maxHeight: 120, paddingVertical: 12, ...Wobble.round },
  send: { width: 54, height: 50, minHeight: 50, paddingHorizontal: 0 },
});
