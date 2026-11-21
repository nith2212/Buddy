// Edit a task (title, due date) or delete it (approved mockup: EditTask and DeleteConfirm boards).
// The delete dialog sits in the same overlay as the sheet, so there's never a modal on top of a modal.
// Deleting removes everything about the task on the server (DELETE /tasks/{id}), so the dialog says so plainly.

import { useState } from 'react';
import { Keyboard, KeyboardAvoidingView, Modal, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import Animated, { FadeIn, SlideInDown, ZoomIn } from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { DuePicker } from '@/components/due-picker';
import { Card, SketchButton, Txt } from '@/components/sketch';
import { Border, Font, Wobble, type Colors } from '@/constants/sketch';
import { useModalBottomInset } from '@/hooks/use-modal-inset';
import { useColors, useThemedStyles } from '@/hooks/use-theme';
import type { api, Task } from '@/lib/api';
import { DayKey, dayKeyOfIso, dueDateFor } from '@/lib/dates';

type Props = {
  task: Task;
  client: ReturnType<typeof api>;
  onClose: () => void;
  onSaved: (task: Task) => void;
  onDeleted: (id: number) => void;
};

/** Mount it only while editing (`{editing ? <EditTaskSheet task={editing} … /> : null}`), so it starts fresh. */
export function EditTaskSheet({ task, client, onClose, onSaved, onDeleted }: Props) {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  const bottomInset = useModalBottomInset();
  const initialDay = dayKeyOfIso(task.due_date);
  const [title, setTitle] = useState(task.title ?? '');
  const [day, setDay] = useState<DayKey | null>(initialDay);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<'save' | 'delete' | null>(null);
  const [confirming, setConfirming] = useState(false);

  const trimmed = title.trim();
  const shownTitle = trimmed || task.title || 'this task';

  async function save() {
    if (!trimmed || busy) return;
    const patch: { title?: string; due_date?: string | null } = {};
    if (trimmed !== (task.title ?? '')) patch.title = trimmed;
    // Only when it changed: re-sending the same day would rewrite its time, and a later date counts as a postpone.
    if (day !== initialDay) patch.due_date = dueDateFor(day);
    if (!Object.keys(patch).length) return onClose();
    setBusy(true);
    setFailed(null);
    try {
      onSaved(await client.updateTask(task.id, patch));
      onClose();
    } catch {
      setFailed('save');
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    setFailed(null);
    try {
      await client.deleteTask(task.id);
      onDeleted(task.id);
      onClose();
    } catch {
      setFailed('delete');
      setBusy(false);
    }
  }

  function askToDelete() {
    Keyboard.dismiss();
    setFailed(null);
    setConfirming(true);
  }

  // Android back: from the dialog, back to the sheet; from the sheet, close.
  const back = () => (confirming ? setConfirming(false) : onClose());

  return (
    <Modal visible transparent animationType="none" onRequestClose={back} statusBarTranslucent>
      <Animated.View entering={FadeIn.duration(160)} style={StyleSheet.absoluteFill}>
        <Pressable
          style={styles.scrim}
          onPress={back}
          accessibilityRole="button"
          accessibilityLabel={confirming ? 'Keep the task' : 'Close without saving'}
        />
      </Animated.View>

      {confirming ? (
        <View style={styles.center} pointerEvents="box-none">
          <Animated.View entering={ZoomIn.duration(180)} style={styles.dialogWrap}>
            <Card wobble="buddy" style={styles.dialog}>
              <View accessibilityViewIsModal accessibilityRole="alert" style={styles.dialogInner}>
                <BuddyBlob width={100} label="Buddy" />
                <Txt variant="heading" style={styles.dialogTitle} accessibilityRole="header">Delete this task?</Txt>
                <Txt style={styles.dialogBody}>
                  {`This deletes “${shownTitle}” and everything about it: its steps, your chat with Buddy, and its check-ins. It’s gone for good, and you can’t get it back.`}
                </Txt>
                {failed === 'delete' ? (
                  <Txt variant="small" style={styles.error}>Couldn’t delete it. Check your connection and try again.</Txt>
                ) : null}
                <View style={styles.dialogRow}>
                  <SketchButton
                    label={busy ? '…' : 'delete'}
                    tone="card"
                    lifted={false}
                    onPress={remove}
                    disabled={busy}
                    accessibilityLabel={`Delete ${shownTitle} for good`}
                    style={styles.dialogButton}
                    textStyle={[styles.dialogButtonText, { color: c.danger }]}
                  />
                  <SketchButton
                    label="keep it"
                    wobble="b"
                    onPress={() => setConfirming(false)}
                    disabled={busy}
                    style={styles.dialogButton}
                    textStyle={styles.dialogButtonText}
                  />
                </View>
              </View>
            </Card>
          </Animated.View>
        </View>
      ) : (
        <KeyboardAvoidingView behavior="padding" style={styles.bottom} pointerEvents="box-none">
          <Animated.View
            entering={SlideInDown.duration(240)}
            accessibilityViewIsModal
            style={[styles.sheet, { paddingBottom: bottomInset + 22 }]}>
            <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.sheetContent} bounces={false}>
              <View style={styles.grab} />
              <Txt variant="heading" style={styles.heading} accessibilityRole="header">Edit task</Txt>

              <Txt variant="hand" style={styles.label}>Task</Txt>
              <TextInput
                value={title}
                onChangeText={setTitle}
                placeholder="What's the task?"
                placeholderTextColor={c.muted}
                accessibilityLabel="Task"
                maxLength={200}
                returnKeyType="done"
                onSubmitEditing={save}
                style={styles.input}
              />

              <Txt variant="hand" style={styles.label}>When’s it due?</Txt>
              <DuePicker value={day} onChange={setDay} onOpenCalendar={Keyboard.dismiss} />

              {failed === 'save' ? (
                <Txt variant="small" style={styles.error}>Couldn’t save that. Check your connection and try again.</Txt>
              ) : null}

              <View style={styles.actions}>
                <Pressable onPress={askToDelete} accessibilityRole="button" hitSlop={8} style={styles.deleteLink} disabled={busy}>
                  <Svg width={18} height={18} viewBox="0 0 18 18">
                    <Path
                      d="M3 5 H15 M7 5 V3 H11 V5 M4.5 5 L5.5 16 H12.5 L13.5 5"
                      fill="none"
                      stroke={c.danger}
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </Svg>
                  <Txt variant="hand" style={styles.deleteText}>delete task</Txt>
                </Pressable>
                <SketchButton
                  label={busy ? '…' : 'save'}
                  wobble="b"
                  onPress={save}
                  disabled={!trimmed || busy}
                  style={styles.save}
                  textStyle={styles.saveText}
                />
              </View>
            </ScrollView>
          </Animated.View>
        </KeyboardAvoidingView>
      )}
    </Modal>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
  scrim: { flex: 1, backgroundColor: c.scrim },
  bottom: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '92%',
    backgroundColor: c.card,
    borderWidth: Border,
    borderBottomWidth: 0,
    borderColor: c.ink,
    borderTopLeftRadius: 26,
    borderTopRightRadius: 18,
  },
  sheetContent: { paddingHorizontal: 22, paddingTop: 14, gap: 12 },
  grab: { width: 56, height: 6, borderRadius: 3, backgroundColor: c.ink, opacity: 0.5, alignSelf: 'center' },
  heading: { fontSize: 30, lineHeight: 32 },
  label: { fontSize: 21, lineHeight: 25, marginBottom: -4 },
  input: {
    minHeight: 48,
    paddingHorizontal: 14,
    fontFamily: Font.semi,
    fontSize: 17,
    color: c.ink,
    backgroundColor: c.bg,
    borderWidth: 2,
    borderColor: c.ink,
    ...Wobble.c,
  },
  error: { color: c.danger },
  actions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  deleteLink: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 44 },
  deleteText: { fontSize: 21, lineHeight: 25, color: c.danger, textDecorationLine: 'underline' },
  save: { minHeight: 54, paddingHorizontal: 26 },
  saveText: { fontSize: 26, lineHeight: 30 },
  center: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, alignItems: 'center', justifyContent: 'center', padding: 28 },
  dialogWrap: { width: '100%' },
  dialog: { padding: 22 },
  dialogInner: { alignItems: 'center', gap: 14 },
  dialogTitle: { fontSize: 32, lineHeight: 34, textAlign: 'center' },
  dialogBody: { textAlign: 'center', lineHeight: 23 },
  dialogRow: { flexDirection: 'row', gap: 12, alignSelf: 'stretch', marginTop: 6 },
  dialogButton: { flex: 1, minHeight: 54 },
  dialogButtonText: { fontSize: 25, lineHeight: 29 },
});
