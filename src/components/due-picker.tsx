// "When's it due?": No date / Today / Tomorrow / Pick a date, and a hand-drawn calendar for the last one
// (approved mockup, EditTask board). No date-picker package: a native one would clash with the sketch look.
// Used by the add-task row on home and the edit sheet; onboarding's first task will use it too.

import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';

import { Chip, Txt } from '@/components/sketch';
import { Font, Wobble, type Colors } from '@/constants/sketch';
import { useColors, useThemedStyles } from '@/hooks/use-theme';
import { dateOfKey, DayKey, daysFromToday, MONTHS, monthCells, prettyDay } from '@/lib/dates';

type Props = {
  value: DayKey | null;
  onChange: (day: DayKey | null) => void;
  /** called when the calendar opens, e.g. to close the keyboard so it fits */
  onOpenCalendar?: () => void;
};

export function DuePicker({ value, onChange, onOpenCalendar }: Props) {
  const c = useColors();
  const styles = useThemedStyles(makeStyles);
  const today = daysFromToday(0);
  const tomorrow = daysFromToday(1);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const custom = value !== null && value !== today && value !== tomorrow;

  function pick(day: DayKey | null) {
    setCalendarOpen(false);
    onChange(day);
  }

  function toggleCalendar() {
    if (!calendarOpen) onOpenCalendar?.();
    setCalendarOpen(!calendarOpen);
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.chips} accessibilityRole="radiogroup" accessibilityLabel="Due date">
        <Chip label="No date" selected={value === null && !calendarOpen} onPress={() => pick(null)} />
        <Chip label="Today" selected={value === today && !calendarOpen} onPress={() => pick(today)} />
        <Chip label="Tomorrow" selected={value === tomorrow && !calendarOpen} onPress={() => pick(tomorrow)} />
        <Chip
          label={custom ? prettyDay(value) : 'Pick a date'}
          accessibilityLabel={custom ? `Due ${prettyDay(value)}. Change the date` : 'Pick a date'}
          selected={custom || calendarOpen}
          onPress={toggleCalendar}
          icon={<CalendarIcon color={custom || calendarOpen ? c.onPop : c.ink} />}
        />
      </View>
      {calendarOpen ? <Calendar picked={value} today={today} onPick={pick} /> : null}
    </View>
  );
}

function Calendar({ picked, today, onPick }: { picked: DayKey | null; today: DayKey; onPick: (day: DayKey) => void }) {
  const c = useColors();
  const styles = useThemedStyles(makeStyles);
  const now = dateOfKey(today);
  // Open on the picked day's month, unless that's in the past: you can't go back before this month.
  const start = picked && picked >= today ? dateOfKey(picked) : now;
  const [view, setView] = useState({ y: start.getFullYear(), m: start.getMonth() });
  const atStart = view.y === now.getFullYear() && view.m === now.getMonth();
  const monthLabel = `${MONTHS[view.m]} ${view.y}`;

  const prev = () => !atStart && setView(({ y, m }) => (m === 0 ? { y: y - 1, m: 11 } : { y, m: m - 1 }));
  const next = () => setView(({ y, m }) => (m === 11 ? { y: y + 1, m: 0 } : { y, m: m + 1 }));

  return (
    <View style={styles.calendar}>
      <View style={styles.calendarHead}>
        <Arrow direction="left" label="Previous month" onPress={prev} disabled={atStart} />
        <Txt variant="hand" style={styles.month} accessibilityLiveRegion="polite">{monthLabel}</Txt>
        <Arrow direction="right" label="Next month" onPress={next} />
      </View>
      <View style={styles.grid} importantForAccessibility="no-hide-descendants">
        {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
          <View key={i} style={styles.cell}>
            <Txt variant="hand" style={styles.weekday}>{d}</Txt>
          </View>
        ))}
      </View>
      <View style={styles.grid} accessibilityLabel={monthLabel}>
        {monthCells(view.y, view.m).map((day, i) => {
          if (!day) return <View key={`blank-${i}`} style={styles.cell} />;
          const isToday = day === today;
          const isPicked = day === picked;
          const past = day < today;
          const n = dateOfKey(day).getDate();
          return (
            <View key={day} style={styles.cell}>
              <Pressable
                onPress={() => onPick(day)}
                disabled={past}
                accessibilityRole="button"
                accessibilityLabel={`${MONTHS[view.m]} ${n}${isToday ? ', today' : ''}`}
                accessibilityState={{ selected: isPicked, disabled: past }}
                style={({ pressed }) => [
                  styles.day,
                  isToday && styles.today,
                  isPicked && styles.picked,
                  pressed && !past && styles.dayPressed,
                ]}>
                <Txt style={[styles.dayText, past && { color: c.pastDay }, isPicked && { fontFamily: Font.bold, color: c.onPop }]}>{n}</Txt>
              </Pressable>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function Arrow({ direction, label, onPress, disabled }: { direction: 'left' | 'right'; label: string; onPress: () => void; disabled?: boolean }) {
  const styles = useThemedStyles(makeStyles);
  const c = useColors();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled }}
      style={({ pressed }) => [styles.arrow, disabled && { opacity: 0.3 }, pressed && styles.dayPressed]}>
      <Svg width={18} height={18} viewBox="0 0 18 18">
        <Path
          d={direction === 'left' ? 'M11.5 3 L5.5 9 L11.5 15' : 'M6.5 3 L12.5 9 L6.5 15'}
          fill="none"
          stroke={c.ink}
          strokeWidth={2.6}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
    </Pressable>
  );
}

function CalendarIcon({ color }: { color: string }) {
  return (
    <Svg width={18} height={18} viewBox="0 0 18 18">
      <Rect x={2} y={3.5} width={14} height={12.5} rx={2.5} fill="none" stroke={color} strokeWidth={2} />
      <Path d="M2 7.5 H16 M6 1.5 V5 M12 1.5 V5" stroke={color} strokeWidth={2} strokeLinecap="round" />
    </Svg>
  );
}

const makeStyles = (c: Colors) =>
  StyleSheet.create({
  wrap: { gap: 10 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  calendar: {
    backgroundColor: c.bg,
    borderWidth: 2,
    borderColor: c.ink,
    paddingHorizontal: 10,
    paddingTop: 6,
    paddingBottom: 8,
    ...Wobble.c,
  },
  calendarHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  month: { fontSize: 23, lineHeight: 27 },
  arrow: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  cell: { width: `${100 / 7}%`, padding: 1, alignItems: 'stretch' },
  weekday: { textAlign: 'center', fontSize: 16, lineHeight: 22, color: c.muted },
  day: {
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: 'transparent',
    borderTopLeftRadius: 12,
    borderTopRightRadius: 8,
    borderBottomRightRadius: 13,
    borderBottomLeftRadius: 7,
  },
  today: { borderColor: c.ink, borderStyle: 'dashed' },
  picked: { backgroundColor: c.pop, borderColor: c.ink, borderStyle: 'solid' },
  dayPressed: { backgroundColor: c.soft },
  dayText: { fontFamily: Font.semi, fontSize: 15, lineHeight: 20 },
});
