// First launch only (approved mockup, 2026-11-07): Hi → Your name (developer, 2026-11-09) → How it works → About you →
// What gets in your way → Check-ins + privacy → First task. "skip" on screens 1–5 jumps to 6, so everyone sees the
// privacy line.
// The answers are "you said" (POST /me/onboarding): they set check-in hours, and are never confirmed causes.

import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { BackHandler, Keyboard, KeyboardAvoidingView, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { DuePicker } from '@/components/due-picker';
import { Card, Chip, SketchButton, Txt } from '@/components/sketch';
import { Font, Wobble, type Colors } from '@/constants/sketch';
import { useColors, useThemedStyles } from '@/hooks/use-theme';
import { api, type OnboardingAnswers } from '@/lib/api';
import { type DayKey, dueDateFor } from '@/lib/dates';
import { registerPushToken } from '@/lib/push';

type Days = NonNullable<OnboardingAnswers['days']>;
type ClickTime = NonNullable<OnboardingAnswers['click_time']>;
type Way = NonNullable<OnboardingAnswers['gets_in_way']>[number];

const DAYS: { value: Days; label: string }[] = [
  { value: 'school', label: 'School or college' },
  { value: 'work', label: 'Work' },
  { value: 'own_projects', label: 'My own projects' },
  { value: 'mix', label: 'A mix' },
];

const TIMES: { value: ClickTime; label: string }[] = [
  { value: 'morning', label: 'Morning' },
  { value: 'afternoon', label: 'Afternoon' },
  { value: 'evening', label: 'Evening' },
  { value: 'late_night', label: 'Late night' },
  { value: 'changes', label: 'It changes' },
];

const WAYS: { value: Way; label: string }[] = [
  { value: 'unclear', label: 'Not knowing where to start' },
  { value: 'too_much', label: 'It feels too big' },
  { value: 'afraid', label: 'Scared it won’t be good' },
  { value: 'bored', label: 'It’s boring or pointless' },
  { value: 'tired', label: 'Too tired' },
  { value: 'not_sure', label: 'Not sure yet' },
];

const HOW_CHIPS = ['don’t know where to start', 'feels too big', 'scared it won’t be good', 'boring', 'too tired'];
const STEPS = 7;

type Props = {
  token: string;
  /** Onboarding is over. With a task id, its chat opens next. */
  onDone: (firstTaskId: number | null) => void;
};

export function Onboarding({ token, onDone }: Props) {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  const client = useMemo(() => api(token), [token]);
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState(1);

  const [name, setName] = useState('');
  const [days, setDays] = useState<Days | null>(null);
  const [clickTime, setClickTime] = useState<ClickTime | null>(null);
  const [ways, setWays] = useState<Way[]>([]);
  const [asking, setAsking] = useState(false);

  const [title, setTitle] = useState('');
  const [due, setDue] = useState<DayKey | null>(null);
  const [adding, setAdding] = useState(false);
  const [addFailed, setAddFailed] = useState(false);

  // Android back goes to the previous screen; on the first one it leaves the app as usual.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (step === 1) return false;
      setStep(step - 1);
      return true;
    });
    return () => sub.remove();
  }, [step]);

  function toCheckins() {
    // Whatever they picked so far; every answer is optional, and a failed save mustn't block onboarding.
    if (name.trim() || days || clickTime || ways.length) {
      client
        .saveOnboarding({
          name: name.trim() || undefined,
          days: days ?? undefined,
          click_time: clickTime ?? undefined,
          gets_in_way: ways,
        })
        .catch(() => {});
    }
    setStep(6);
  }

  function toggleWay(way: Way) {
    // "Not sure yet" stands alone; picking a reason replaces it.
    if (way === 'not_sure') setWays(ways.includes('not_sure') ? [] : ['not_sure']);
    else setWays(ways.includes(way) ? ways.filter((w) => w !== way) : [...ways.filter((w) => w !== 'not_sure'), way]);
  }

  async function turnOnCheckins() {
    setAsking(true);
    try {
      await registerPushToken(token, true);
    } catch {
      // No check-ins for now; they can still use everything else.
    } finally {
      setAsking(false);
      setStep(7);
    }
  }

  async function startFirstTask() {
    const trimmed = title.trim();
    if (!trimmed || adding) return;
    setAdding(true);
    setAddFailed(false);
    try {
      const task = await client.createTask(trimmed, dueDateFor(due));
      onDone(task.id);
    } catch {
      setAddFailed(true);
      setAdding(false);
    }
  }

  let body: ReactNode;
  if (step === 1) {
    body = (
      <>
        <View style={styles.center}>
          <BuddyBlob width={200} label="Buddy, a soft white dumpling, smiling" />
          <Card wobble="buddy" outerStyle={styles.full} style={styles.cardGap12}>
            <Txt variant="title" style={styles.h1Big} accessibilityRole="header">Hi, I’m Buddy!</Txt>
            <Txt style={styles.p}>I help you start the things you keep putting off.</Txt>
            <Txt style={styles.p}>Not by pushing you. By finding out what’s actually in the way, then making the first bit tiny.</Txt>
          </Card>
        </View>
        <Primary label="Hi Buddy!" onPress={() => setStep(2)} />
      </>
    );
  } else if (step === 2) {
    const first = name.trim().split(/\s+/)[0]?.slice(0, 12);
    body = (
      <>
        <View style={styles.centerRow}>
          <BuddyBlob width={150} label="Buddy, curious" />
        </View>
        <View style={styles.gap8}>
          <Txt variant="title" style={styles.h1} accessibilityRole="header">What should I call you?</Txt>
          <Txt style={styles.small}>A first name or a nickname is perfect.</Txt>
        </View>
        <Card style={styles.cardGap14}>
          <Txt variant="hand" style={styles.label}>Your name</Txt>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="Your name"
            placeholderTextColor={c.muted}
            accessibilityLabel="Your name"
            maxLength={30}
            autoCapitalize="words"
            autoComplete="name"
            returnKeyType="next"
            onSubmitEditing={() => setStep(3)}
            style={styles.input}
          />
        </Card>
        <View style={styles.grow} />
        <Primary
          label={first ? `Nice to meet you, ${first}!` : 'Next'}
          onPress={() => {
            Keyboard.dismiss();
            setStep(3);
          }}
        />
      </>
    );
  } else if (step === 3) {
    body = (
      <>
        <Txt variant="title" style={styles.h1} accessibilityRole="header">Stuck? Tell me why.</Txt>
        <Card style={styles.cardGap14}>
          <Txt style={styles.p}>When a task feels hard to start, pick what’s closest:</Txt>
          <View style={styles.chips} accessibilityLabel="The five reasons">
            {HOW_CHIPS.map((c) => (
              <View key={c} style={styles.staticChip}>
                <Txt variant="hand" style={styles.staticChipText}>{c}</Txt>
              </View>
            ))}
          </View>
          <Txt style={styles.p}>
            Then we find one tiny way in, <Txt style={[styles.p, { fontFamily: Font.bold }]}>together</Txt>. You always get the last word on the plan.
          </Txt>
        </Card>
        <Card wobble="b" outerStyle={styles.mt6} style={styles.mondayCard}>
          <View style={styles.bars} importantForAccessibility="no-hide-descendants">
            {[22, 40, 30, 58].map((h, i) => (
              <View key={i} style={[styles.bar, { height: h, backgroundColor: i % 2 ? c.pop : c.soft }]} />
            ))}
          </View>
          <View style={styles.mondayText}>
            <Txt variant="heading" style={styles.h2}>Every Monday</Txt>
            <Txt style={styles.small}>I’ll show you what helped last week. No streaks, no guilt.</Txt>
          </View>
        </Card>
        <View style={styles.grow} />
        <Primary label="Got it" onPress={() => setStep(4)} />
      </>
    );
  } else if (step === 4) {
    body = (
      <>
        <View style={styles.gap8}>
          <Txt variant="title" style={styles.h1} accessibilityRole="header">A little about you</Txt>
          <Txt style={styles.small}>So I can check in at the right time. Skip any you don’t want to answer.</Txt>
        </View>
        <Card style={styles.cardGap14}>
          <Txt variant="heading" style={styles.h2}>What fills most of your days?</Txt>
          <View style={styles.chips}>
            {DAYS.map((o) => (
              <Chip key={o.value} label={o.label} selected={days === o.value} onPress={() => setDays(days === o.value ? null : o.value)} />
            ))}
          </View>
        </Card>
        <Card wobble="b" outerStyle={styles.mt4} style={styles.cardGap14}>
          <Txt variant="heading" style={styles.h2}>When do things usually click for you?</Txt>
          <View style={styles.chips}>
            {TIMES.map((o) => (
              <Chip
                key={o.value}
                label={o.label}
                selected={clickTime === o.value}
                onPress={() => setClickTime(clickTime === o.value ? null : o.value)}
              />
            ))}
          </View>
          <Txt style={styles.small}>I’ll send check-ins around then.</Txt>
        </Card>
        <View style={styles.grow} />
        <Primary label="Next" onPress={() => setStep(5)} />
      </>
    );
  } else if (step === 5) {
    body = (
      <>
        <View style={styles.wayHead}>
          <Txt variant="title" style={[styles.h1, styles.flex1]} accessibilityRole="header">What usually gets in your way?</Txt>
          <BuddyBlob width={96} label="Buddy" />
        </View>
        <Txt style={styles.small}>Pick any. It’s just your guess. I’ll learn the real story from how things actually go.</Txt>
        <Card style={styles.wayList}>
          {WAYS.map((o) => {
            const on = ways.includes(o.value);
            return (
              <Pressable
                key={o.value}
                onPress={() => toggleWay(o.value)}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                style={({ pressed }) => [styles.wayRow, on && styles.wayRowOn, pressed && styles.pressed]}>
                <View style={styles.box}>
                  {on ? (
                    <Svg width={14} height={14} viewBox="0 0 14 14">
                      <Path d="M2 7.5 L5.5 11 L12 3" fill="none" stroke={c.onPop} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
                    </Svg>
                  ) : null}
                </View>
                <Txt variant="hand" style={[styles.wayText, on && { color: c.onPop }]}>{o.label}</Txt>
              </Pressable>
            );
          })}
        </Card>
        <View style={styles.grow} />
        <Primary label="Next" onPress={toCheckins} />
      </>
    );
  } else if (step === 6) {
    body = (
      <>
        <SampleCheckin />
        <View style={[styles.gap8, styles.mt6]}>
          <Txt variant="title" style={styles.h1} accessibilityRole="header">Can I check in on you?</Txt>
          <Txt style={styles.p}>
            A little nudge on your tasks now and then, around the time you said works. Answer right from the notification.
          </Txt>
        </View>
        <Card wobble="b" style={styles.privacy}>
          <Txt variant="heading" style={[styles.h2Small, { color: c.onPop }]}>About your chats</Txt>
          <Txt style={styles.privacyText}>
            Your chats are saved so I can learn what helps you. While Buddy is in testing, Nithya (who made me) can read them. Delete everything anytime: menu → Delete my data.
          </Txt>
        </Card>
        <View style={styles.grow} />
        <View style={styles.gap6}>
          <Primary label={asking ? '…' : 'Turn on check-ins'} onPress={turnOnCheckins} disabled={asking} />
          <TextLink label="maybe later" onPress={() => setStep(7)} disabled={asking} />
        </View>
      </>
    );
  } else {
    body = (
      <>
        <View style={styles.centerRow}>
          <BuddyBlob width={130} mood="happy" label="Buddy, happy" />
        </View>
        <Txt variant="title" style={styles.h1} accessibilityRole="header">What’s one thing you’ve been putting off?</Txt>
        <Card style={styles.cardGap14}>
          <Txt variant="hand" style={styles.label}>Your task</Txt>
          <TextInput
            value={title}
            onChangeText={setTitle}
            placeholder="e.g. start my DBMS assignment"
            placeholderTextColor={c.muted}
            accessibilityLabel="Your task"
            maxLength={200}
            returnKeyType="done"
            style={styles.input}
          />
          <Txt variant="hand" style={styles.label}>When’s it due?</Txt>
          <DuePicker value={due} onChange={setDue} onOpenCalendar={Keyboard.dismiss} />
        </Card>
        <Txt style={styles.small}>Next, we’ll chat about what’s making it hard to start.</Txt>
        {addFailed ? (
          <Txt variant="small" style={styles.error}>Couldn’t add that. Check your connection and try again.</Txt>
        ) : null}
        <View style={styles.grow} />
        <View style={styles.gap6}>
          <Primary label={adding ? '…' : 'Let’s start'} onPress={startFirstTask} disabled={!title.trim() || adding} />
          <TextLink label="I’ll add one later" onPress={() => onDone(null)} disabled={adding} />
        </View>
      </>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.screen} behavior="padding">
      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 28 }]}
        keyboardShouldPersistTaps="handled"
        bounces={false}>
        <View style={styles.top}>
          <View style={styles.dots} accessible accessibilityRole="image" accessibilityLabel={`Step ${step} of ${STEPS}`}>
            {Array.from({ length: STEPS }, (_, i) => (
              <View key={i} style={[styles.dot, i < step && styles.dotOn]} />
            ))}
          </View>
          {step <= 5 ? <TextLink label="skip" onPress={toCheckins} small /> : null}
        </View>
        <Animated.View key={step} entering={FadeIn.duration(220)} style={styles.step}>
          {body}
        </Animated.View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Primary({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) {
  const styles = useThemedStyles(makeStyles);
  return (
    <SketchButton label={label} wobble="b" onPress={onPress} disabled={disabled} style={styles.primary} textStyle={styles.primaryText} />
  );
}

function TextLink({ label, onPress, disabled, small }: { label: string; onPress: () => void; disabled?: boolean; small?: boolean }) {
  const styles = useThemedStyles(makeStyles);
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" hitSlop={8} style={small ? styles.skipLink : styles.link}>
      <Txt variant="hand" style={[styles.linkText, small && { fontSize: 20 }]}>{label}</Txt>
    </Pressable>
  );
}

/** What a check-in looks like, in the developer's wording (backend/notifications/service.py). */
function SampleCheckin() {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  return (
    <Card wobble="c" style={styles.sample} outerStyle={styles.full}>
      <View
        accessible
        accessibilityLabel="Example check-in from Buddy: Hey! Checking in on DBMS assignment! Where are you at? With buttons Not yet, On it, and Done."
        style={styles.gap10}>
        <View style={styles.sampleHead}>
          <BuddyBlob width={26} animated={false} label="" />
          <Txt variant="small" style={styles.bold}>Buddy</Txt>
          <Txt variant="small" style={{ color: c.muted }}>· now</Txt>
        </View>
        <View>
          <Txt variant="semi" style={styles.bold}>Hey! 🌟</Txt>
          <Txt variant="semi">Checking in on “DBMS assignment”! Where are you at?</Txt>
        </View>
        <View style={styles.sampleButtons}>
          {['Not yet', 'On it', 'Done!'].map((b) => (
            <View key={b} style={styles.sampleButton}>
              <Txt variant="small" style={styles.bold}>{b}</Txt>
            </View>
          ))}
        </View>
      </View>
    </Card>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
  screen: { flex: 1, backgroundColor: c.bg },
  content: { flexGrow: 1, paddingHorizontal: 24, gap: 18 },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 44 },
  dots: { flexDirection: 'row', gap: 7 },
  dot: { width: 10, height: 10, borderRadius: 5, borderWidth: 2, borderColor: c.ink },
  dotOn: { backgroundColor: c.ink },
  step: { flexGrow: 1, gap: 18 },
  grow: { flexGrow: 1 },
  flex1: { flex: 1 },
  full: { alignSelf: 'stretch' },
  center: { flexGrow: 1, alignItems: 'center', justifyContent: 'center', gap: 30 },
  centerRow: { alignItems: 'center' },
  gap6: { gap: 6 },
  gap8: { gap: 8 },
  gap10: { gap: 10 },
  mt4: { marginTop: 4 },
  mt6: { marginTop: 6 },
  cardGap12: { padding: 18, gap: 12 },
  cardGap14: { padding: 18, gap: 14 },
  h1Big: { fontSize: 44, lineHeight: 46 },
  h1: { fontSize: 42, lineHeight: 44 },
  h2: { fontSize: 25, lineHeight: 28 },
  h2Small: { fontSize: 23, lineHeight: 26 },
  p: { fontSize: 17, lineHeight: 25 },
  small: { fontSize: 15, lineHeight: 22, color: c.muted },
  bold: { fontFamily: Font.bold },
  label: { fontSize: 22, lineHeight: 26, marginBottom: -6 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  staticChip: { borderWidth: 2, borderColor: c.ink, backgroundColor: c.bg, paddingHorizontal: 12, paddingVertical: 4, ...Wobble.c },
  staticChipText: { fontSize: 19, lineHeight: 24 },
  mondayCard: { padding: 18, flexDirection: 'row', alignItems: 'center', gap: 16 },
  bars: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 64 },
  bar: { width: 26, borderWidth: 2, borderColor: c.ink, borderTopLeftRadius: 6, borderTopRightRadius: 6, borderBottomLeftRadius: 3, borderBottomRightRadius: 3 },
  mondayText: { flex: 1, gap: 6 },
  wayHead: { flexDirection: 'row', alignItems: 'flex-end', gap: 12 },
  wayList: { padding: 18, gap: 10 },
  wayRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: 48,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 2,
    borderColor: c.ink,
    backgroundColor: c.bg,
    ...Wobble.c,
  },
  wayRowOn: { backgroundColor: c.soft },
  pressed: { transform: [{ translateX: 2 }, { translateY: 2 }] },
  box: {
    width: 22,
    height: 22,
    borderWidth: 2.5,
    borderColor: c.ink,
    backgroundColor: c.card,
    alignItems: 'center',
    justifyContent: 'center',
    borderTopLeftRadius: 6,
    borderTopRightRadius: 4,
    borderBottomRightRadius: 7,
    borderBottomLeftRadius: 3,
  },
  wayText: { flex: 1, fontSize: 21, lineHeight: 25 },
  sample: { padding: 14 },
  sampleHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sampleButtons: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  sampleButton: { borderWidth: 1.5, borderColor: c.ink, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, backgroundColor: c.bg },
  privacy: { padding: 16, gap: 6, backgroundColor: c.soft },
  privacyText: { fontSize: 14.5, lineHeight: 21, color: c.onPop },
  input: {
    minHeight: 50,
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
  primary: { minHeight: 58 },
  primaryText: { fontSize: 27, lineHeight: 31 },
  link: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  skipLink: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 4 },
  linkText: { fontSize: 21, lineHeight: 25, color: c.muted, textDecorationLine: 'underline' },
});
