import React, { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { useNavigation, useFocusEffect, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { buildMaxxMaps, mergeSchedules, type MergedScheduleTask } from '../../utils/scheduleAggregation';

function formatTimeTo12Hour(time24: string) {
  if (!time24 || typeof time24 !== 'string' || !time24.includes(':')) return time24 || '';
  try {
    const [hoursStr, minutesStr] = time24.split(':');
    const hours = parseInt(hoursStr, 10);
    const minutes = parseInt(minutesStr, 10);
    if (isNaN(hours) || isNaN(minutes)) return time24;
    const period = hours >= 12 ? 'PM' : 'AM';
    const hours12 = hours % 12 || 12;
    return `${hours12}:${minutes.toString().padStart(2, '0')} ${period}`;
  } catch {
    return time24;
  }
}

function getTaskIcon(type: string) {
  switch (type) {
    case 'exercise':
      return 'barbell-outline';
    case 'routine':
      return 'refresh-outline';
    case 'reminder':
      return 'notifications-outline';
    case 'checkpoint':
      return 'flag-outline';
    default:
      return 'ellipse-outline';
  }
}

export default function MasterScheduleScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const insets = useSafeAreaInsets();
  const isTab = route.name === 'MasterScheduleTab';

  const [schedules, setSchedules] = useState<any[]>([]);
  const [maxxes, setMaxxes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedDate, setSelectedDate] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);

  const { labels: maxxLabels, colors: maxxColorMap } = useMemo(() => buildMaxxMaps(maxxes), [maxxes]);

  const merged = useMemo(
    () => mergeSchedules(schedules, maxxLabels, maxxColorMap),
    [schedules, maxxLabels, maxxColorMap],
  );

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [full, maxxRes] = await Promise.all([
        api.getActiveSchedulesFull(),
        api.getMaxxes().catch(() => ({ maxes: [] as any[] })),
      ]);
      setSchedules(full.schedules || []);
      setMaxxes(maxxRes.maxes || []);
    } catch (e: any) {
      console.error('Master schedule load failed', e);
      setSchedules([]);
      const msg =
        e?.response?.data?.detail ||
        e?.message ||
        'Could not load schedules. Check your connection and try again.';
      setLoadError(String(msg));
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  useEffect(() => {
    if (merged.dates.length === 0) {
      setSelectedDate('');
      return;
    }
    setSelectedDate((d) => {
      if (d && merged.dates.includes(d)) return d;
      const today = new Date().toISOString().split('T')[0];
      return merged.dates.includes(today) ? today : merged.dates[0];
    });
  }, [merged.dates]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const goHome = () => {
    if (isTab) navigation.navigate('Home');
    else navigation.navigate('Main', { screen: 'Home' });
  };

  const headerBack = () => {
    if (isTab) return;
    if (navigation.canGoBack()) navigation.goBack();
  };

  const tasksForDay = selectedDate ? merged.byDate[selectedDate] || [] : [];
  const completedCount = tasksForDay.filter((t) => t.status === 'completed').length;
  const totalCount = tasksForDay.length;

  const handleComplete = async (scheduleId: string, taskId: string) => {
    try {
      await api.completeScheduleTask(scheduleId, taskId);
      await load();
    } catch (e) {
      console.error('complete task', e);
    }
  };

  const openScheduleDetail = (task: MergedScheduleTask) => {
    navigation.navigate('Schedule', { scheduleId: task.scheduleId });
  };

  const HeaderChrome = ({
    title,
    subtitle,
    legend,
  }: {
    title: string;
    subtitle?: string;
    legend?: ReactNode;
  }) => (
    <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
      {isTab ? (
        <View style={styles.backButton} />
      ) : (
        <TouchableOpacity onPress={headerBack} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color={colors.foreground} />
        </TouchableOpacity>
      )}
      <View style={styles.headerCenter}>
        <Text style={styles.headerTitle}>{title}</Text>
        {subtitle ? <Text style={styles.subhead}>{subtitle}</Text> : null}
        {legend ? <View style={styles.legendWrap}>{legend}</View> : null}
      </View>
      <View style={styles.backButton} />
    </View>
  );

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color={colors.foreground} />
      </View>
    );
  }

  if (loadError) {
    return (
      <View style={styles.container}>
        <HeaderChrome title="Master schedule" />
        <View style={[styles.emptyState, styles.center]}>
          <Ionicons name="cloud-offline-outline" size={56} color={colors.error} />
          <Text style={styles.emptyTitle}>Couldn&apos;t load schedules</Text>
          <Text style={styles.emptySubtitle}>{loadError}</Text>
          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={async () => {
              setLoading(true);
              await load();
            }}
            activeOpacity={0.7}
          >
            <Text style={styles.primaryBtnText}>Try again</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (schedules.length === 0 || merged.dates.length === 0) {
    return (
      <View style={styles.container}>
        <HeaderChrome title="Master schedule" subtitle="All tasks across your active programs" />
        <View style={[styles.emptyState, styles.center]}>
          <Ionicons name="layers-outline" size={64} color={colors.textMuted} />
          <Text style={styles.emptyTitle}>No active schedules</Text>
          <Text style={styles.emptySubtitle}>
            Start a schedule from each Maxx on Home. When you have one or more running, every task shows up here,
            color-coded by program.
          </Text>
          <TouchableOpacity style={styles.primaryBtn} onPress={goHome} activeOpacity={0.7}>
            <Text style={styles.primaryBtnText}>Go to Home</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  const legendChips =
    merged.legend.length > 0 ? (
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.legendScroll}
        contentContainerStyle={styles.legendRowInHeader}
      >
        {merged.legend.map((item) => (
          <View key={item.id} style={styles.legendChip}>
            <View style={[styles.legendDot, { backgroundColor: item.color }]} />
            <Text style={styles.legendText} numberOfLines={1}>
              {item.label}
            </Text>
          </View>
        ))}
      </ScrollView>
    ) : null;

  return (
    <View style={styles.container}>
      <HeaderChrome
        title="Master schedule"
        subtitle="All tasks across your active programs"
        legend={legendChips}
      />

      <View style={styles.bodyBelowHeader}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.dayStripScroll}
        contentContainerStyle={styles.daySelectorContainer}
      >
        {merged.dates.map((dateStr) => {
          const isSelected = dateStr === selectedDate;
          const date = new Date(dateStr + 'T00:00:00');
          const dayName = date.toLocaleDateString('en-US', { weekday: 'short' });
          const dayNum = date.getDate();
          const dayTasks = merged.byDate[dateStr] || [];
          const dayDone = dayTasks.length > 0 && dayTasks.every((t) => t.status === 'completed');
          return (
            <TouchableOpacity
              key={dateStr}
              style={[styles.dayPill, isSelected && styles.dayPillActive, dayDone && styles.dayPillDone]}
              onPress={() => setSelectedDate(dateStr)}
              activeOpacity={0.7}
            >
              <Text style={[styles.dayPillLabel, isSelected && styles.dayPillLabelActive]}>{dayName}</Text>
              <Text style={[styles.dayPillNumber, isSelected && styles.dayPillNumberActive]}>{dayNum}</Text>
              {dayDone && <View style={styles.dayCompleteDot} />}
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <ScrollView
        style={styles.taskList}
        contentContainerStyle={{ paddingBottom: 100 }}
        showsVerticalScrollIndicator={false}
        nestedScrollEnabled
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.foreground} />
        }
      >
        <View style={styles.progressRow}>
          <Text style={styles.progressText}>
            {completedCount}/{totalCount} done · {merged.legend.length} program{merged.legend.length !== 1 ? 's' : ''}
          </Text>
          <View style={styles.progressBar}>
            <View
              style={[
                styles.progressFill,
                { width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` },
              ]}
            />
          </View>
        </View>

        {tasksForDay.map((task) => {
          const isDone = task.status === 'completed';
          return (
            <View key={`${task.scheduleId}-${task.task_id}`} style={[styles.taskCard, isDone && styles.taskCardDone]}>
              <View style={[styles.moduleAccent, { backgroundColor: task.moduleColor }]} />
              <TouchableOpacity
                style={[styles.taskCheck, isDone && styles.taskCheckDone]}
                onPress={() => {
                  if (!isDone) handleComplete(task.scheduleId, task.task_id);
                }}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                {isDone && <Ionicons name="checkmark" size={14} color={colors.buttonText} />}
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.taskContent}
                onPress={() => openScheduleDetail(task)}
                activeOpacity={0.75}
              >
                <View style={styles.taskHeader}>
                  <Text style={[styles.taskTime, isDone && styles.taskTimeDone]}>
                    {formatTimeTo12Hour(task.time)}
                  </Text>
                  <View style={styles.taskTypeBadge}>
                    <Ionicons name={getTaskIcon(task.task_type) as any} size={12} color={colors.textMuted} />
                    <Text style={styles.taskTypeText}>{task.duration_minutes}m</Text>
                  </View>
                </View>
                <View style={styles.modulePill}>
                  <View style={[styles.modulePillDot, { backgroundColor: task.moduleColor }]} />
                  <Text style={styles.modulePillText} numberOfLines={1}>
                    {task.moduleLabel}
                  </Text>
                </View>
                <Text style={[styles.taskTitle, isDone && styles.taskTitleDone]}>{task.title}</Text>
                <Text style={styles.taskDescription} numberOfLines={2}>
                  {task.description}
                </Text>
                <Text style={styles.openHint}>Tap for full schedule →</Text>
              </TouchableOpacity>
            </View>
          );
        })}
      </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xs,
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
    paddingHorizontal: spacing.xs,
    minWidth: 0,
  },
  backButton: { width: 40, padding: spacing.xs },
  headerTitle: { ...typography.h3, textAlign: 'center', width: '100%' },
  subhead: {
    ...typography.bodySmall,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 2,
    marginBottom: spacing.xs,
    lineHeight: 18,
    width: '100%',
  },
  /** Horizontal legend must not grow (web flex); keeps chips tight under title. */
  legendScroll: {
    flexGrow: 0,
    flexShrink: 0,
    maxHeight: 32,
    width: '100%',
  },
  legendRowInHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: 0,
    paddingHorizontal: 0,
    justifyContent: 'center',
  },
  legendChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.card,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.full,
    maxWidth: 200,
    ...shadows.sm,
  },
  legendDot: { width: 6, height: 6, borderRadius: 3 },
  legendText: { fontSize: 11, fontWeight: '600', color: colors.foreground, flexShrink: 1 },
  daySelectorContainer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xs,
    gap: spacing.sm,
  },
  dayPill: {
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: borderRadius.md,
    backgroundColor: colors.card,
    minWidth: 44,
  },
  dayPillActive: { backgroundColor: colors.foreground },
  dayPillDone: { borderWidth: 1.5, borderColor: colors.success },
  dayPillLabel: { ...typography.caption, fontSize: 10, marginBottom: 1 },
  dayPillLabelActive: { color: colors.buttonText },
  dayPillNumber: { fontSize: 14, fontWeight: '600', color: colors.foreground },
  dayPillNumberActive: { color: colors.buttonText },
  dayCompleteDot: {
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: colors.success,
    marginTop: 3,
  },
  taskList: { flex: 1, minHeight: 0, paddingHorizontal: spacing.lg },
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginBottom: spacing.md,
    marginTop: spacing.sm,
  },
  progressText: { ...typography.caption, flexShrink: 0, maxWidth: '48%' },
  progressBar: {
    flex: 1,
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: colors.success, borderRadius: 2 },
  taskCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: colors.card,
    padding: spacing.md,
    paddingLeft: 0,
    borderRadius: borderRadius.lg,
    marginBottom: spacing.sm,
    overflow: 'hidden',
    ...shadows.sm,
  },
  taskCardDone: { opacity: 0.62 },
  moduleAccent: {
    width: 4,
    alignSelf: 'stretch',
    borderTopLeftRadius: borderRadius.lg,
    borderBottomLeftRadius: borderRadius.lg,
    minHeight: 48,
  },
  taskCheck: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
    marginLeft: spacing.xs,
  },
  taskCheckDone: { backgroundColor: colors.success, borderColor: colors.success },
  taskContent: { flex: 1, paddingRight: spacing.xs },
  taskHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  taskTime: { fontSize: 12, fontWeight: '700', color: colors.foreground, letterSpacing: 0.3 },
  taskTimeDone: { textDecorationLine: 'line-through', color: colors.textMuted },
  taskTypeBadge: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  taskTypeText: { ...typography.caption },
  modulePill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    backgroundColor: colors.surface,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: borderRadius.md,
    marginBottom: 6,
    maxWidth: '100%',
  },
  modulePillDot: { width: 6, height: 6, borderRadius: 3 },
  modulePillText: { fontSize: 11, fontWeight: '600', color: colors.textSecondary, flexShrink: 1 },
  taskTitle: { fontSize: 15, fontWeight: '600', color: colors.foreground, marginBottom: 2 },
  taskTitleDone: { textDecorationLine: 'line-through', color: colors.textMuted },
  taskDescription: { ...typography.bodySmall },
  openHint: {
    ...typography.caption,
    color: colors.textMuted,
    marginTop: 8,
    fontSize: 11,
  },
  emptyState: { flex: 1, paddingHorizontal: spacing.xl },
  emptyTitle: { ...typography.h2, marginTop: spacing.lg, marginBottom: spacing.sm, textAlign: 'center' },
  emptySubtitle: { ...typography.bodySmall, textAlign: 'center', marginBottom: spacing.xl },
  primaryBtn: {
    backgroundColor: colors.foreground,
    paddingHorizontal: spacing.xl,
    paddingVertical: 14,
    borderRadius: borderRadius.full,
    ...shadows.md,
  },
  primaryBtnText: { ...typography.button },
});
