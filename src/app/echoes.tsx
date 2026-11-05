// Echoes, the weekly report (mockup screen 5), from GET /echo/week. Two views: this week so far (live)
// and last week (saved by the Sunday 23:00 cron), so Monday opens on a real report. Only kind, earned
// things: wins, the days you showed up, one Buddy line and what helped. Never ignored check-ins,
// untouched days or comparisons: the backend doesn't even send those. Last week can be saved or sent
// as text through the phone's share sheet (it's replaced after another week).

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, Share, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { BrandHeader } from '@/components/side-menu';
import { Card, Chip, Hatch, SketchButton, Txt } from '@/components/sketch';
import { Border, Ink, Palette, Wobble } from '@/constants/sketch';
import { useToken } from '@/hooks/use-session';
import { api, EchoWeek, EchoWeekSummary } from '@/lib/api';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function times(n: number) {
  return n === 1 ? 'once' : n === 2 ? 'twice' : `${n} times`;
}

/** "Nov 9 – 15" from the week's seven dates. */
function weekRange(days: EchoWeekSummary['days']) {
  if (!days.length) return '';
  const fmt = (iso: string, withMonth: boolean) =>
    new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, withMonth ? { month: 'short', day: 'numeric' } : { day: 'numeric' });
  const first = days[0].date;
  const last = days[days.length - 1].date;
  return `${fmt(first, true)} – ${fmt(last, first.slice(5, 7) !== last.slice(5, 7))}`;
}

function winLines(wins: EchoWeekSummary['wins']) {
  return [
    wins.tasks_finished ? `Finished ${plural(wins.tasks_finished, 'task')}` : null,
    wins.steps_done ? `Ticked off ${plural(wins.steps_done, 'step')}` : null,
    wins.started_when_hard ? `Got going ${times(wins.started_when_hard)} when it felt hard` : null,
  ].filter((w): w is string => w !== null);
}

/** The report as plain text, for saving or sending. */
function reportText(week: EchoWeekSummary, helped: EchoWeek['helped']) {
  const wins = winLines(week.wins);
  const shown = week.days.filter((d) => d.active).length;
  return [
    `buddy. · Echo for ${weekRange(week.days)}`,
    '',
    'Wins',
    ...(wins.length ? wins.map((w) => `• ${w}`) : ['• Nothing to count, and that’s okay.']),
    '',
    `Days you showed up: ${shown} of 7`,
    week.days.map((d, i) => `${DAY_NAMES[i].slice(0, 3)} ${d.active ? '●' : '○'}`).join('  '),
    '',
    `Buddy: “${week.line}”`,
    ...(helped.length ? ['', 'What helped', ...helped.map((h) => `• ${h.text}`)] : []),
    '',
    '(saved from the Buddy app)',
  ].join('\n');
}

/** Monday to Wednesday (local), open on last week's report if there is one. */
function opensOnLastWeek() {
  const day = new Date().getDay(); // 0 = Sunday
  return day >= 1 && day <= 3;
}

export default function EchoesScreen() {
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [week, setWeek] = useState<EchoWeek | null>(null);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState<'this' | 'last' | null>(null); // null = not chosen yet: pick by weekday

  const load = useCallback(async () => {
    try {
      setWeek(await client.echoWeek());
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

  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  const hasLast = !!week?.last_week;
  const showing: 'this' | 'last' = hasLast ? (view ?? (opensOnLastWeek() ? 'last' : 'this')) : 'this';
  const shown: EchoWeekSummary | null = week ? (showing === 'last' && week.last_week ? week.last_week : week) : null;

  async function saveReport() {
    if (!week?.last_week) return;
    try {
      await Share.share({ title: `Buddy Echo · ${weekRange(week.last_week.days)}`, message: reportText(week.last_week, week.helped) });
    } catch {
      // the share sheet was dismissed or isn't available: nothing to do
    }
  }

  return (
    <View style={styles.screen}>
      <BrandHeader topInset={insets.top} />
      {week === null || shown === null ? (
        <View style={styles.center}>
          <BuddyBlob width={140} mood={failed ? 'worried' : 'default'} label={failed ? 'Buddy, worried: can’t reach the server' : 'Buddy'} />
          <Txt variant="hand" style={styles.centerText}>{failed ? 'Couldn’t load your week. Check back in a bit!' : 'Looking back at your week…'}</Txt>
          {failed ? <SketchButton label="Try again" onPress={load} /> : null}
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 28 }]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} colors={[Palette.deep]} />}>
          <View style={styles.titleBlock}>
            <Txt variant="title" style={styles.bigTitle} accessibilityRole="header">
              Echoes<Txt variant="title" style={[styles.bigTitle, { color: Palette.deep }]}>.</Txt>
            </Txt>
            <Svg width={120} height={12} viewBox="0 0 120 12">
              <Path d="M4 8 Q30 2 60 7 T116 5" fill="none" stroke={Palette.deep} strokeWidth={3} strokeLinecap="round" />
            </Svg>
            <Txt variant="hand" style={styles.subtitle}>{`~ ${showing === 'last' ? 'last week' : 'this week'} · ${weekRange(shown.days)} ~`}</Txt>
          </View>

          {hasLast ? (
            <View style={styles.tabs} accessibilityLabel="Which week">
              <Chip label="This week" selected={showing === 'this'} onPress={() => setView('this')} />
              <Chip label="Last week" selected={showing === 'last'} onPress={() => setView('last')} />
            </View>
          ) : null}

          {week.first_week && showing === 'this' ? (
            <Card wobble="b" shadow="solid" style={styles.banner}>
              <BuddyBlob width={64} mood="happy" animated={false} />
              <View style={styles.bannerText}>
                <Txt variant="hand" style={styles.bannerTitle}>Your first Echo lands on Monday!</Txt>
                <Txt variant="small">Buddy’s still getting to know you. Here’s your week so far.</Txt>
              </View>
            </Card>
          ) : null}
          {showing === 'last' ? (
            <Card wobble="b" shadow="solid" style={styles.banner}>
              <BuddyBlob width={64} mood="happy" animated={false} />
              <View style={styles.bannerText}>
                <Txt variant="hand" style={styles.bannerTitle}>{`Your Echo for ${weekRange(shown.days)} is ready!`}</Txt>
                <Txt variant="small">It makes way for a new one next week, so save it if you’d like to keep it.</Txt>
              </View>
            </Card>
          ) : null}

          <WeekView week={shown} totalDays={showing === 'this' ? week.total_days : null} />

          {week.helped.length ? (
            <Card wobble="b" shadow="none" dashed style={styles.helped}>
              <Txt variant="hand" style={styles.helpedTitle}>What helped</Txt>
              {week.helped.map((h) => (
                <Txt key={h.cause} style={styles.helpedText}>{h.text}</Txt>
              ))}
            </Card>
          ) : null}

          {showing === 'last' ? (
            <SketchButton tone="soft" label="save or share this report" onPress={saveReport} accessibilityHint="Opens your phone's share sheet with the report as text" />
          ) : null}
          <SketchButton label="talk to buddy about my week" onPress={() => router.push('/chat')} style={styles.talk} textStyle={styles.talkText} />
        </ScrollView>
      )}
    </View>
  );
}

function WeekView({ week, totalDays }: { week: EchoWeekSummary; totalDays: number | null }) {
  const wins = winLines(week.wins);
  return (
    <>
      <Card wobble="a" style={styles.wins}>
        <Txt variant="heading" style={styles.underline}>Wins:</Txt>
        {wins.length ? (
          wins.map((w) => (
            <View key={w} style={styles.winRow}>
              <View style={styles.dot} />
              <Txt variant="semi" style={styles.winText}>{w}</Txt>
            </View>
          ))
        ) : (
          <Txt variant="semi">Nothing to count yet, and that’s okay.</Txt>
        )}
      </Card>

      <View style={styles.days} accessibilityLabel="Days you showed up">
        <View style={styles.dayRow}>
          {week.days.map((d, i) => (
            <View key={d.date} style={styles.dayCell} accessible accessibilityLabel={`${DAY_NAMES[i]}: ${d.active ? 'showed up' : 'rest day'}`}>
              <View style={[styles.dayDot, { backgroundColor: d.active ? Palette.pop : Palette.white }]}>
                {d.active ? <Hatch color={Ink} style={[Wobble.round, styles.dayHatch]} /> : null}
              </View>
              <Txt variant="hand" importantForAccessibility="no">{DAY_NAMES[i][0]}</Txt>
            </View>
          ))}
        </View>
        {totalDays ? <Txt variant="small" style={styles.centerText}>{`You’ve shown up ${plural(totalDays, 'day')} since you started.`}</Txt> : null}
      </View>

      <View style={styles.lineRow}>
        <BuddyBlob width={52} mood="happy" animated={false} style={styles.lineAvatar} />
        <View style={styles.quote}>
          <Txt variant="hand" style={styles.quoteText}>{`“${week.line}”`}</Txt>
        </View>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Palette.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24 },
  centerText: { textAlign: 'center' },
  content: { paddingHorizontal: 24, paddingTop: 4, gap: 20 },
  titleBlock: { alignItems: 'center' },
  bigTitle: { fontSize: 52, lineHeight: 56 },
  subtitle: { fontSize: 21, marginTop: 2 },
  tabs: { flexDirection: 'row', justifyContent: 'center', gap: 10 },
  banner: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 12, backgroundColor: Palette.soft },
  bannerText: { flex: 1, gap: 2 },
  bannerTitle: { fontSize: 21, lineHeight: 25 },
  wins: { paddingHorizontal: 18, paddingVertical: 14, gap: 8 },
  underline: { textDecorationLine: 'underline' },
  winRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  dot: { width: 12, height: 12, borderRadius: 6, borderWidth: 2, borderColor: Ink, backgroundColor: Palette.pop },
  winText: { flex: 1 },
  days: { gap: 8 },
  dayRow: { flexDirection: 'row', justifyContent: 'space-between' },
  dayCell: { alignItems: 'center', gap: 4 },
  dayDot: { width: 38, height: 38, borderWidth: Border, borderColor: Ink, overflow: 'hidden', ...Wobble.round },
  dayHatch: { opacity: 0.35 },
  lineRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  lineAvatar: { marginTop: 6 },
  quote: {
    flex: 1,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderWidth: Border,
    borderColor: Ink,
    backgroundColor: Palette.soft,
    ...Wobble.buddy,
  },
  quoteText: { fontSize: 22, lineHeight: 27 },
  helped: { paddingHorizontal: 16, paddingVertical: 14, gap: 6 },
  helpedTitle: { fontSize: 22 },
  helpedText: { fontSize: 15, lineHeight: 21 },
  talk: { minHeight: 52, marginTop: 4 },
  talkText: { fontSize: 23 },
});
