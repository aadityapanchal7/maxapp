import React, { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Platform,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { buildMaxxMaps, mergeSchedules, type MergedScheduleTask } from '../../utils/scheduleAggregation';
import { useMaxxesQuery, useActiveSchedulesFullQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { useAuth } from '../../context/AuthContext';
import { getItemAsync, setItemAsync } from '../../services/storage';
import {
  ensureAppNotificationPermission,
  scheduleScheduleReminder,
  cancelScheduleReminder,
} from '../../services/localScheduleNotifications';
import { StreakFireBadge } from '../../components/StreakFireBadge';

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

function parseTimeToHHMM(time: string): { hh: number; mm: number } | null {
  const s = (time || '').trim();
  if (!s) return null;
  const m24 = /^(\d{1,2}):(\d{2})$/.exec(s);
  if (!m24) return null;
  const hh = parseInt(m24[1], 10);
  const mm = parseInt(m24[2], 10);
  if (Number.isNaN(hh) || Number.isNaN(mm) || hh < 0 || hh > 23 || mm < 0 || mm > 59) return null;
  return { hh, mm };
}

type ActiveSchedulesFullCache = {
  schedules: any[];
  schedule_streak?: unknown;
  today_date?: string;
};

/** Patch active/full schedules cache so checklist toggles feel instant (merged view updates from schedules[].days[].tasks). */
function patchSchedulesFullTaskStatus(
  data: ActiveSchedulesFullCache | undefined,
  scheduleId: string,
  taskId: string,
  nextStatus: 'completed' | 'pending',
): ActiveSchedulesFullCache | undefined {
  if (!data?.schedules?.length) return data;
  return {
    ...data,
    schedules: data.schedules.map((s) => {
      if (s.id !== scheduleId) return s;
      const days = (s.days || []).map((day: { tasks?: any[]; [k: string]: unknown }) => ({
        ...day,
        tasks: (day.tasks || []).map((t: any) => {
          if (t.task_id !== taskId) return t;
          if (nextStatus === 'completed') {
            return { ...t, status: 'completed', completed_at: new Date().toISOString() };
          }
          const { completed_at: _c, ...rest } = t;
          return { ...rest, status: 'pending' };
        }),
      }));
      return { ...s, days };
    }),
  };
}

function mergeScheduleStreakFromToggleResponse(
  data: ActiveSchedulesFullCache | undefined,
  res: { schedule_streak?: { current?: number; today_date?: string; last_perfect_date?: string | null } },
): ActiveSchedulesFullCache | undefined {
  if (!data || !res?.schedule_streak) return data;
  const streak = res.schedule_streak;
  return {
    ...data,
    schedule_streak: streak,
    today_date: streak.today_date ?? data.today_date,
  };
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
  const queryClient = useQueryClient();
  const isTab = route.name === 'MasterScheduleTab';
  const { user } = useAuth();
  const appNotificationsOptIn = user?.onboarding?.app_notifications_opt_in !== false;

  const notifIdMapRef = useRef<Record<string, string>>({});
  const taskToggleInFlightRef = useRef<Set<string>>(new Set());
  const notifStorageKey = 'max_local_schedule_reminder_notif_map_v1';

  const maxesQuery = useMaxxesQuery();
  const schedulesQuery = useActiveSchedulesFullQuery();

  const [refreshing, setRefreshing] = useState(false);
  const [selectedDate, setSelectedDate] = useState('');
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);

  const schedules = schedulesQuery.data?.schedules ?? [];
  const maxxes = maxesQuery.data?.maxes ?? [];
  const loading =
    (maxesQuery.isPending && !maxesQuery.data) || (schedulesQuery.isPending && !schedulesQuery.data);

  const loadError = useMemo(() => {
    if (schedulesQuery.isError && schedulesQuery.error) {
      const e = schedulesQuery.error as { response?: { data?: { detail?: string } }; message?: string };
      return String(e?.response?.data?.detail || e?.message || 'Could not load schedules.');
    }
    return null;
  }, [schedulesQuery.isError, schedulesQuery.error]);

  const scheduleStreak = useMemo(
    () => ({ current: schedulesQuery.data?.schedule_streak?.current ?? 0 }),
    [schedulesQuery.data?.schedule_streak?.current],
  );

  const calendarTodayKey = useMemo(
    () =>
      schedulesQuery.data?.today_date ||
      schedulesQuery.data?.schedule_streak?.today_date ||
      '',
    [schedulesQuery.data?.today_date, schedulesQuery.data?.schedule_streak?.today_date],
  );

  const { labels: maxxLabels, colors: maxxColorMap } = useMemo(() => buildMaxxMaps(maxxes), [maxxes]);

  const merged = useMemo(
    () => mergeSchedules(schedules, maxxLabels, maxxColorMap),
    [schedules, maxxLabels, maxxColorMap],
  );

  const refetchAll = useCallback(async () => {
    await Promise.all([maxesQuery.refetch(), schedulesQuery.refetch()]);
  }, [maxesQuery, schedulesQuery]);

  useEffect(() => {
    if (merged.dates.length === 0) {
      setSelectedDate('');
      return;
    }
    setSelectedDate((d) => {
      if (d && merged.dates.includes(d)) return d;
      const today = calendarTodayKey || new Date().toISOString().split('T')[0];
      return merged.dates.includes(today) ? today : merged.dates[0];
    });
  }, [merged.dates, calendarTodayKey]);

  // App notifications: schedule local reminder notifications for upcoming pending tasks.
  useEffect(() => {
    if (Platform.OS === 'web') return;
    if (!appNotificationsOptIn) return;
    if (!user?.is_paid) return;
    if (loading) return;
    if (!merged.dates.length) return;

    let cancelled = false;
    (async () => {
      try {
        const granted = await ensureAppNotificationPermission();
        if (!granted || cancelled) return;

        const stored = await getItemAsync(notifStorageKey);
        let notifMap: Record<string, string> = {};
        if (stored) {
          try {
            notifMap = JSON.parse(stored) || {};
          } catch {
            notifMap = {};
          }
        }
        notifIdMapRef.current = notifMap;

        const schedulePrefsById = new Map<string, any>();
        for (const s of schedules) schedulePrefsById.set(s.id, s.preferences || {});

        const pendingKeys = new Set<string>();
        const pendingEntries: Record<string, { fireDate: Date; title: string; body: string }> = {};

        const nowMs = Date.now();
        const datesToConsider = merged.dates.slice(0, 14); // keep it bounded
        const MAX_NOTIFICATIONS = 120;

        for (const dateStr of datesToConsider) {
          const dayTasks = merged.byDate[dateStr] || [];
          for (const task of dayTasks) {
            if (task.status !== 'pending') continue;
            const parts = parseTimeToHHMM(task.time);
            if (!parts) continue;

            const key = `${task.scheduleId}:${task.task_id}`;
            if (pendingKeys.size >= MAX_NOTIFICATIONS) break;

            const hh = String(parts.hh).padStart(2, '0');
            const mm = String(parts.mm).padStart(2, '0');
            const scheduledAt = new Date(`${dateStr}T${hh}:${mm}:00`);
            const prefs = schedulePrefsById.get(task.scheduleId) || {};
            const offsetMin = prefs.notification_minutes_before ?? 5;
            const fireDate = new Date(scheduledAt.getTime() - offsetMin * 60 * 1000);

            // Skip anything already in the past (including notification lead-time).
            if (fireDate.getTime() <= nowMs) continue;

            pendingKeys.add(key);
            pendingEntries[key] = {
              fireDate,
              title: task.moduleLabel ? `Max (${task.moduleLabel})` : 'Max',
              body: task.description ? `${task.title}\n${task.description}` : task.title,
            };
          }
        }

        // Cancel notifications no longer pending.
        const existingKeys = Object.keys(notifMap);
        for (const key of existingKeys) {
          if (!pendingKeys.has(key)) {
            const existingId = notifMap[key];
            if (existingId) await cancelScheduleReminder(existingId);
            delete notifMap[key];
          }
        }

        // Schedule new notifications.
        for (const key of pendingKeys) {
          if (notifMap[key]) continue;
          const entry = pendingEntries[key];
          if (!entry) continue;
          const id = await scheduleScheduleReminder({
            title: entry.title,
            body: entry.body,
            fireDate: entry.fireDate,
          });
          notifMap[key] = id;
        }

        notifIdMapRef.current = notifMap;
        await setItemAsync(notifStorageKey, JSON.stringify(notifMap));
      } catch (e) {
        // Best-effort only: don't block schedule UI if scheduling fails.
        console.error('Local notification scheduling failed:', e);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [appNotificationsOptIn, user?.id, user?.is_paid, loading, merged, schedules]);

  // If the user opted out, cancel any previously scheduled local reminders.
  useEffect(() => {
    if (Platform.OS === 'web') return;
    if (appNotificationsOptIn) return;

    let cancelled = false;
    (async () => {
      try {
        const stored = await getItemAsync(notifStorageKey);
        let notifMap: Record<string, string> = {};
        if (stored) {
          try {
            notifMap = JSON.parse(stored) || {};
          } catch {
            notifMap = {};
          }
        }
        if (cancelled) return;

        const ids = Object.values(notifMap);
        for (const id of ids) {
          if (id) await cancelScheduleReminder(id);
        }

        notifIdMapRef.current = {};
        await setItemAsync(notifStorageKey, JSON.stringify({}));
      } catch {
        // Best-effort.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [appNotificationsOptIn]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await refetchAll();
    } finally {
      setRefreshing(false);
    }
  }, [refetchAll]);

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

  const goToChatForTask = (task: MergedScheduleTask) => {
    const initQuestion =
      `Can you help me with this task?` +
      `\n\nTask: ${task.title}` +
      `\nProgram: ${task.moduleLabel}` +
      `\nWhen: ${task.time}` +
      `\nDetails: ${task.description}`;
    if (isTab) {
      navigation.navigate('Chat', { initQuestion });
    } else {
      navigation.navigate('Main', { screen: 'Chat', params: { initQuestion } });
    }
  };

  const toggleTaskComplete = async (task: MergedScheduleTask) => {
    const key = `${task.scheduleId}-${task.task_id}`;
    if (taskToggleInFlightRef.current.has(key)) return;
    if (Platform.OS !== 'web') {
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }

    const nextStatus: 'completed' | 'pending' = task.status === 'completed' ? 'pending' : 'completed';
    const previous = queryClient.getQueryData(queryKeys.schedulesActiveFull) as ActiveSchedulesFullCache | undefined;
    queryClient.setQueryData(queryKeys.schedulesActiveFull, (old) =>
      patchSchedulesFullTaskStatus(old as ActiveSchedulesFullCache | undefined, task.scheduleId, task.task_id, nextStatus),
    );

    taskToggleInFlightRef.current.add(key);
    try {
      const res =
        nextStatus === 'completed'
          ? await api.completeScheduleTask(task.scheduleId, task.task_id)
          : await api.uncompleteScheduleTask(task.scheduleId, task.task_id);

      queryClient.setQueryData(queryKeys.schedulesActiveFull, (old) =>
        mergeScheduleStreakFromToggleResponse(old as ActiveSchedulesFullCache | undefined, res),
      );

      if (nextStatus === 'completed') {
        const notifKey = `${task.scheduleId}:${task.task_id}`;
        const notifId = notifIdMapRef.current[notifKey];
        if (notifId) {
          void (async () => {
            try {
              await cancelScheduleReminder(notifId);
              delete notifIdMapRef.current[notifKey];
              await setItemAsync(notifStorageKey, JSON.stringify(notifIdMapRef.current));
            } catch {
              // Best-effort.
            }
          })();
        }
      }
    } catch (e) {
      console.error('toggle task complete', e);
      queryClient.setQueryData(queryKeys.schedulesActiveFull, previous);
    } finally {
      taskToggleInFlightRef.current.delete(key);
    }
  };

  const HeaderChrome = ({
    title,
    subtitle,
    headerRight,
    legend,
  }: {
    title: string;
    subtitle?: string;
    headerRight?: ReactNode;
    legend?: ReactNode;
  }) => (
    <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
      {isTab ? (
        <View style={styles.headerSide} />
      ) : (
        <TouchableOpacity onPress={headerBack} style={styles.headerSide} hitSlop={{ top: 8, bottom: 8, right: 8 }}>
          <Ionicons name="arrow-back" size={22} color={colors.foreground} />
        </TouchableOpacity>
      )}
      <View style={styles.headerCenter}>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.subhead} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
        {legend ? <View style={styles.legendWrap}>{legend}</View> : null}
      </View>
      <View style={styles.headerRightSlot}>{headerRight ?? <View style={styles.headerSide} />}</View>
    </View>
  );

  const headerStreakRight = <StreakFireBadge streakDays={scheduleStreak.current} />;

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
        <HeaderChrome
          title="Schedule"
          subtitle="All your active tasks"
          headerRight={headerStreakRight}
        />
        <View style={[styles.emptyState, styles.center]}>
          <Ionicons name="cloud-offline-outline" size={56} color={colors.error} />
          <Text style={styles.emptyTitle}>Couldn&apos;t load your schedule</Text>
          <Text style={styles.emptySubtitle}>{loadError}</Text>
          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={() => void refetchAll()}
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
        <HeaderChrome
          title="Schedule"
          subtitle="All your active tasks, in one place"
          headerRight={headerStreakRight}
        />
        <View style={[styles.emptyState, styles.center]}>
          <Ionicons name="layers-outline" size={64} color={colors.textMuted} />
          <Text style={styles.emptyTitle}>No active schedules</Text>
          <Text style={styles.emptySubtitle}>
            Start a schedule from a Maxx on Home. Once it&apos;s active, it&apos;ll show up here automatically.
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
        title="Schedule"
        subtitle="All your active tasks, in one place"
        headerRight={headerStreakRight}
        legend={legendChips}
      />
      {legendChips ? <View style={styles.legendBar}>{legendChips}</View> : null}

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
                accessibilityRole="button"
                accessibilityLabel={`Select ${dayName} ${dayNum}`}
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
              {scheduleStreak.current > 0
                ? `🔥 ${scheduleStreak.current} day${scheduleStreak.current === 1 ? '' : 's'} streak · `
                : ''}
              {completedCount}/{totalCount} completed
              {merged.legend.length > 0
                ? ` · ${merged.legend.length} program${merged.legend.length !== 1 ? 's' : ''}`
                : ''}
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
            const isExpanded = expandedTaskId === task.task_id;
            return (
              <View key={`${task.scheduleId}-${task.task_id}`} style={[styles.taskCard, isDone && styles.taskCardDone]}>
                <View style={styles.taskCardInner}>
                  <View style={styles.accentColumn}>
                    <View style={[styles.scheduleTaskAccent, { backgroundColor: task.moduleColor }]} />
                  </View>
                  <View style={styles.taskCardMainCol}>
                    <View style={styles.taskTopRow}>
                      <TouchableOpacity
                        style={[styles.taskCheck, isDone && styles.taskCheckDone]}
                        onPress={() => void toggleTaskComplete(task)}
                        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                        accessibilityRole="checkbox"
                        accessibilityLabel={
                          isDone ? `Mark task not done: ${task.title}` : `Mark task done: ${task.title}`
                        }
                        accessibilityState={{ checked: isDone }}
                      >
                        {isDone ? (
                          <Ionicons name="checkmark" size={14} color={colors.buttonText} />
                        ) : null}
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={styles.taskMainPress}
                        onPress={() => setExpandedTaskId((prev) => (prev === task.task_id ? null : task.task_id))}
                        activeOpacity={0.75}
                        accessibilityRole="button"
                        accessibilityLabel={`${isExpanded ? 'Collapse' : 'Expand'} details for ${task.title}`}
                      >
                        <View style={styles.taskHeader}>
                          <Text style={[styles.taskTime, isDone && styles.taskTimeDone]}>
                            {formatTimeTo12Hour(task.time)}
                          </Text>
                          <View style={styles.taskHeaderRight}>
                            <View style={styles.taskTypeBadge}>
                              <Ionicons name={getTaskIcon(task.task_type) as any} size={12} color={colors.textMuted} />
                              <Text style={styles.taskTypeText}>{task.duration_minutes}m</Text>
                            </View>
                            <Ionicons
                              name={isExpanded ? 'chevron-up' : 'chevron-down'}
                              size={16}
                              color={colors.textMuted}
                            />
                          </View>
                        </View>
                        <Text style={styles.taskModuleLabel} numberOfLines={1}>
                          {task.moduleLabel}
                        </Text>
                        <Text
                          style={[styles.taskTitle, isDone && styles.taskTitleDone]}
                          numberOfLines={isExpanded ? undefined : 2}
                        >
                          {task.title}
                        </Text>
                      </TouchableOpacity>
                    </View>

                    {isExpanded && (
                      <View style={styles.taskExpanded}>
                        {task.description ? (
                          <Text style={styles.taskDescriptionFull}>{task.description}</Text>
                        ) : null}
                        <TouchableOpacity
                          style={styles.askChatRow}
                          onPress={() => goToChatForTask(task)}
                          activeOpacity={0.75}
                          accessibilityRole="button"
                          accessibilityLabel={`Ask Max about ${task.title}`}
                        >
                          <Ionicons name="chatbubble-ellipses-outline" size={14} color={colors.foreground} />
                          <Text style={styles.askChatLabel}>Ask Max</Text>
                          <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
                        </TouchableOpacity>
                      </View>
                    )}
                  </View>
                </View>
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
    paddingBottom: spacing.sm,
  },
  headerSide: {
    width: 40,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xs,
  },
  headerCenter: {
    flex: 1,
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    minWidth: 0,
  },
  headerRightSlot: {
    width: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: -0.4,
    color: colors.foreground,
    textAlign: 'center',
    width: '100%',
  },
  subhead: {
    ...typography.bodySmall,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 4,
    lineHeight: 18,
    width: '100%',
  },
  legendWrap: {
    width: '100%',
    maxHeight: 22,
    overflow: 'hidden',
  },
  legendBar: {
    paddingBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderLight,
  },
  legendScroll: {
    flexGrow: 0,
    maxHeight: 26,
    width: '100%',
  },
  legendRowInHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.lg,
    paddingTop: 2,
  },
  legendChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: colors.card,
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: borderRadius.full,
    maxWidth: 200,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  legendDot: { width: 4, height: 4, borderRadius: 2 },
  legendText: { fontSize: 9, fontWeight: '600', color: colors.foreground, flexShrink: 1, lineHeight: 12 },
  /** Match ScheduleScreen day strip */
  daySelectorContainer: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
    flexGrow: 1,
    justifyContent: 'center',
  },
  dayPill: {
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.lg,
    backgroundColor: colors.card,
    minWidth: 52,
  },
  dayPillActive: { backgroundColor: colors.foreground },
  dayPillDone: { borderWidth: 1.5, borderColor: colors.success },
  dayPillLabel: { ...typography.caption, marginBottom: 2 },
  dayPillLabelActive: { color: colors.buttonText },
  dayPillNumber: { fontSize: 16, fontWeight: '600', color: colors.foreground },
  dayPillNumberActive: { color: colors.buttonText },
  dayCompleteDot: {
    width: 5,
    height: 5,
    borderRadius: 3,
    backgroundColor: colors.success,
    marginTop: 3,
  },
  bodyBelowHeader: {
    flex: 1,
    minHeight: 0,
  },
  dayStripScroll: {
    flexGrow: 0,
    flexShrink: 0,
  },
  taskList: { flex: 1, minHeight: 0, paddingHorizontal: spacing.lg },
  progressRow: {
    width: '100%',
    alignItems: 'center',
    marginBottom: spacing.md,
    marginTop: spacing.sm,
  },
  progressText: { ...typography.caption, textAlign: 'center', marginBottom: spacing.sm },
  progressBar: {
    width: '100%',
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: colors.success, borderRadius: 2 },
  /** Match ScheduleScreen task cards */
  taskCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    marginBottom: spacing.sm,
    ...shadows.sm,
    overflow: 'hidden',
  },
  taskCardDone: { opacity: 0.6 },
  taskCardInner: {
    flexDirection: 'row',
    alignItems: 'stretch',
    width: '100%',
  },
  accentColumn: {
    width: 4,
  },
  scheduleTaskAccent: {
    flex: 1,
    minHeight: 56,
    borderRadius: 2,
  },
  taskCardMainCol: {
    flex: 1,
    minWidth: 0,
    paddingVertical: spacing.md,
    paddingLeft: spacing.sm,
    paddingRight: spacing.md,
  },
  taskTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  taskCheck: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  taskCheckDone: { backgroundColor: colors.success, borderColor: colors.success },
  taskMainPress: { flex: 1, minWidth: 0 },
  taskHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  taskHeaderRight: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  taskTime: { fontSize: 12, fontWeight: '700', color: colors.foreground, letterSpacing: 0.3 },
  taskTimeDone: { textDecorationLine: 'line-through', color: colors.textMuted },
  taskTypeBadge: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  taskTypeText: { ...typography.caption },
  taskModuleLabel: {
    ...typography.caption,
    color: colors.textMuted,
    fontWeight: '600',
    marginBottom: 2,
  },
  taskTitle: { fontSize: 15, fontWeight: '600', color: colors.foreground },
  taskTitleDone: { textDecorationLine: 'line-through', color: colors.textMuted },
  taskExpanded: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  taskDescriptionFull: {
    ...typography.bodySmall,
    color: colors.foreground,
    marginBottom: spacing.sm,
    lineHeight: 20,
  },
  askChatRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    backgroundColor: colors.background,
    alignSelf: 'stretch',
  },
  askChatLabel: {
    ...typography.caption,
    flex: 1,
    fontWeight: '600',
    color: colors.foreground,
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