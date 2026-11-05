// Echoes, the weekly report (mockup screen 5), from GET /echo/week. Only kind, earned things:
// wins, the days you showed up, one Buddy line and what helped. Never ignored check-ins,
// untouched days or comparisons: the backend doesn't even send those.

import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { BuddyBlob } from '@/components/buddy-blob';
import { BrandHeader } from '@/components/side-menu';
import { Card, Hatch, SketchButton, Txt } from '@/components/sketch';
import { Border, Ink, Palette, Wobble } from '@/constants/sketch';
import { useToken } from '@/hooks/use-session';
import { api, EchoWeek } from '@/lib/api';

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function times(n: number) {
  return n === 1 ? 'once' : n === 2 ? 'twice' : `${n} times`;
}

/** "Nov 9 – 15" from the week's seven dates. */
function weekRange(days: EchoWeek['days']) {
  if (!days.length) return '';
  const fmt = (iso: string, withMonth: boolean) =>
    new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, withMonth ? { month: 'short', day: 'numeric' } : { day: 'numeric' });
  const first = days[0].date;
  const last = days[days.length - 1].date;
  return `${fmt(first, true)} – ${fmt(last, first.slice(5, 7) !== last.slice(5, 7))}`;
}

export default function EchoesScreen() {
  const token = useToken();
  const client = useMemo(() => api(token), [token]);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [week, setWeek] = useState<EchoWeek | null>(null);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

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

  const wins = week
    ? [
        week.wins.tasks_finished ? `Finished ${plural(week.wins.tasks_finished, 'task')}` : null,
        week.wins.steps_done ? `Ticked off ${plural(week.wins.steps_done, 'step')}` : null,
        week.wins.started_when_hard ? `Got going ${times(week.wins.started_when_hard)} when it felt hard` : null,
      ].filter((w): w is string => w !== null)
    : [];

  return (
    <View style={styles.screen}>
      <BrandHeader topInset={insets.top} />
      {week === null ? (
        <View style={styles.center}>
          <BuddyBlob width={140} mood={failed ? 'worried' : 'default'} label={failed ? 'Buddy, worried: can’t reach the server' : 'Buddy'} />
          <Txt variant="hand">{failed ? 'Couldn’t load your week.' : 'Looking back at your week…'}</Txt>
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
            <Txt variant="hand" style={styles.subtitle}>{`~ this week · ${weekRange(week.days)} ~`}</Txt>
          </View>

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
              <Txt variant="semi">Nothing to count yet this week, and that’s okay.</Txt>
            )}
          </Card>

          <View style={styles.days} accessibilityLabel="Days you showed up this week">
            <View style={styles.dayRow}>
              {week.days.map((d, i) => (
                <View
                  key={d.date}
                  style={styles.dayCell}
                  accessible
                  accessibilityLabel={`${DAY_NAMES[i]}: ${d.active ? 'showed up' : 'rest day'}`}>
                  <View style={[styles.dayDot, { backgroundColor: d.active ? Palette.pop : Palette.white }]}>
                    {d.active ? <Hatch color={Ink} style={[Wobble.round, styles.dayHatch]} /> : null}
                  </View>
                  <Txt variant="hand" importantForAccessibility="no">{DAY_NAMES[i][0]}</Txt>
                </View>
              ))}
            </View>
            {week.total_days > 0 ? (
              <Txt variant="small" style={styles.centerText}>{`You’ve shown up ${plural(week.total_days, 'day')} since you started.`}</Txt>
            ) : null}
          </View>

          <View style={styles.lineRow}>
            <BuddyBlob width={52} mood="happy" animated={false} style={styles.lineAvatar} />
            <View style={styles.quote}>
              <Txt variant="hand" style={styles.quoteText}>{`“${week.line}”`}</Txt>
            </View>
          </View>

          {week.helped.length ? (
            <Card wobble="b" shadow="none" dashed style={styles.helped}>
              <Txt variant="hand" style={styles.helpedTitle}>What helped</Txt>
              {week.helped.map((h) => (
                <Txt key={h.cause} style={styles.helpedText}>{h.text}</Txt>
              ))}
            </Card>
          ) : null}

          <SketchButton label="talk to buddy about my week" onPress={() => router.push('/chat')} style={styles.talk} textStyle={styles.talkText} />
        </ScrollView>
      )}
    </View>
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
