import React, { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Platform,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
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
import MaxLoadingView from '../../components/MaxLoadingView';

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

/** Avoid showing “Skinmax” twice when the title already starts with the module label. */
/** Short, calm copy for schedule API failures (hides raw SQLAlchemy / pool noise). */
function scheduleErrorSubtitle(raw: string): string {
  const s = (raw || '').trim();
  if (!s) return 'Could not load your schedule. Check your connection and try again.';
  const lower = s.toLowerCase();
  if (
    lower.includes('queuepool') ||
    lower.includes('connection timed out') ||
    lower.includes('maxclients') ||
    lower.includes('timeout')
  ) {
    return 'We could not load your data in time. Check your connection and try again.';
  }
  if (s.length > 160) {
    return `${s.slice(0, 157).trim()}…`;
  }
  return s;
}

function stripDuplicateModulePrefix(title: string, moduleLabel: string): string {
  const t = (title || '').trim();
  const m = (moduleLabel || '').trim();
  if (!m || !t) return t;
  const escaped = m.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`^${escaped}\\s*([·•|\\-–:]\\s*)?`, 'i');
  const stripped = t.replace(re, '').trim();
  return stripped.length > 0 ? stripped : t;
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
  const skipLocalBecauseServerPush =
    Platform.OS === 'ios' && appNotificationsOptIn && user?.has_apns_token === true;

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

  // When iOS has a server-registered APNs token, rely on backend push — skip duplicate local reminders.
  useEffect(() => {
    if (Platform.OS === 'web') return;
    if (!skipLocalBecauseServerPush) return;

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
        for (const id of Object.values(notifMap)) {
          if (id) await cancelScheduleReminder(id);
        }
        notifIdMapRef.current = {};
        await setItemAsync(notifStorageKey, JSON.stringify({}));
      } catch {
        /* best-effort */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [skipLocalBecauseServerPush, notifStorageKey]);

  // App notifications: schedule local reminder notifications for upcoming pending tasks.
  useEffect(() => {
    if (Platform.OS === 'web') return;
    if (skipLocalBecauseServerPush) return;
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
  }, [
    appNotificationsOptIn,
    skipLocalBecauseServerPush,
    user?.id,
    user?.is_paid,
    loading,
    merged,
    schedules,
  ]);

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

  const goToChatForTask = (task: MergedScheduleTask) => {
    // Seed the chat with a directive question so the agent gives concrete,
    // numbered steps for how to actually do the task — not generic explainer
    // copy. The init_context tells the backend this is a "task help" request
    // so it can pull the catalog evidence_section + relevant RAG chunks.
    const initQuestion =
      `Walk me through how to actually do this task — give me a short numbered list of the exact steps, what to use, and any common mistakes to avoid. Keep it practical, no fluff.` +
      `\n\nTask: ${task.title}` +
      (task.moduleLabel ? `\nProgram: ${task.moduleLabel}` : '') +
      (task.time ? `\nWhen: ${task.time}` : '') +
      (task.description ? `\nDetails: ${task.description}` : '');
    const initContext = `task_help:${task.scheduleId}:${task.task_id}`;
    if (isTab) {
      navigation.navigate('Chat', { initQuestion, initContext });
    } else {
      navigation.navigate('Main', { screen: 'Chat', params: { initQuestion, initContext } });
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

  const groupedTasks = useMemo(() => {
    const morning: MergedScheduleTask[] = [];
    const afternoon: MergedScheduleTask[] = [];
    const evening: MergedScheduleTask[] = [];
    for (const t of tasksForDay) {
      const parts = parseTimeToHHMM(t.time);
      if (!parts || parts.hh < 12) morning.push(t);
      else if (parts.hh < 17) afternoon.push(t);
      else evening.push(t);
    }
    const groups: { label: string; tasks: MergedScheduleTask[] }[] = [];
    if (morning.length) groups.push({ label: 'Morning', tasks: morning });
    if (afternoon.length) groups.push({ label: 'Afternoon', tasks: afternoon });
    if (evening.length) groups.push({ label: 'Evening', tasks: evening });
    if (groups.length === 0 && tasksForDay.length > 0) groups.push({ label: 'Today', tasks: tasksForDay });
    return groups;
  }, [tasksForDay]);

  const HeaderChrome = ({
    title,
    headerRight,
  }: {
    title: string;
    headerRight?: ReactNode;
  }) => (
    <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
      {!isTab && (
        <TouchableOpacity onPress={headerBack} style={styles.backBtn} hitSlop={{ top: 8, bottom: 8, right: 8 }}>
          <Ionicons name="arrow-back" size={20} color={colors.foreground} />
        </TouchableOpacity>
      )}
      <View style={styles.headerTextCol}>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {title}
        </Text>
      </View>
      {headerRight}
    </View>
  );

  const headerStreakRight = <StreakFireBadge streakDays={scheduleStreak.current} />;

  if (loading) {
    return <MaxLoadingView />;
  }

  if (loadError) {
    return (
      <View style={styles.container}>
        <HeaderChrome title="Schedule" headerRight={headerStreakRight} />
        <View style={[styles.emptyStateMinimal, styles.center]}>
          <View style={styles.emptyIconCircle}>
            <Ionicons name="pulse-outline" size={22} color={colors.textMuted} />
          </View>
          <Text style={styles.emptyTitleMinimal}>Schedule unavailable</Text>
          <Text style={styles.emptySubtitleMinimal}>{scheduleErrorSubtitle(loadError)}</Text>
          <TouchableOpacity
            style={styles.minimalBtn}
            onPress={() => void refetchAll()}
            activeOpacity={0.65}
          >
            <Text style={styles.minimalBtnText}>Try again</Text>
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
          headerRight={headerStreakRight}
        />
        <View style={[styles.emptyStateMinimal, styles.center]}>
          <View style={styles.emptyIconCircle}>
            <Ionicons name="calendar-outline" size={22} color={colors.textMuted} />
          </View>
          <Text style={styles.emptyTitleMinimal}>No schedules yet</Text>
          <Text style={styles.emptySubtitleMinimal}>
            Start a plan from a Maxx on Home — it will appear here when active.
          </Text>
          <TouchableOpacity style={styles.minimalBtn} onPress={goHome} activeOpacity={0.65}>
            <Text style={styles.minimalBtnText}>Go to Home</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        {!isTab && (
          <TouchableOpacity onPress={headerBack} style={styles.backBtn} hitSlop={{ top: 8, bottom: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={20} color={colors.foreground} />
          </TouchableOpacity>
        )}
        <View style={styles.headerTextCol}>
          <Text style={styles.headerTitle}>Schedule</Text>
        </View>
        <StreakFireBadge streakDays={scheduleStreak.current} />
      </View>

      <View style={styles.bodyBelowHeader}>
        {selectedDate ? (
          <Text style={styles.monthLabel}>
            {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
          </Text>
        ) : null}
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
                style={styles.dayPill}
                onPress={() => setSelectedDate(dateStr)}
                activeOpacity={0.7}
                accessibilityRole="button"
                accessibilityLabel={`Select ${dayName} ${dayNum}`}
              >
                <Text style={[styles.dayPillLabel, isSelected && styles.dayPillLabelActive]}>{dayName}</Text>
                <Text style={[styles.dayPillNumber, isSelected && styles.dayPillNumberActive]}>{dayNum}</Text>
                {isSelected && <View style={styles.dayUnderline} />}
                {!isSelected && dayDone && <View style={styles.dayCompleteDot} />}
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
          {groupedTasks.map((group, gi) => (
            <View key={group.label}>
              {gi > 0 && <View style={styles.groupSpacer} />}
              <Text style={styles.timeGroupLabel}>{group.label}</Text>
              {group.tasks.map((task, index) => {
                const isDone = task.status === 'completed';
                const isExpanded = expandedTaskId === task.task_id;
                return (
                  <View key={`${task.scheduleId}-${task.task_id}`}>
                    {index > 0 && <View style={styles.taskDivider} />}
                    <TouchableOpacity
                      style={[styles.taskRow, isDone && styles.taskRowDone]}
                      onPress={() => setExpandedTaskId((prev) => (prev === task.task_id ? null : task.task_id))}
                      activeOpacity={0.75}
                      accessibilityRole="button"
                      accessibilityLabel={`${isExpanded ? 'Collapse' : 'Expand'} details for ${stripDuplicateModulePrefix(task.title, task.moduleLabel)}`}
                    >
                      <View style={[styles.scheduleTaskAccent, { backgroundColor: task.moduleColor }]} />
                      <TouchableOpacity
                        style={[styles.taskCheck, isDone && styles.taskCheckDone]}
                        onPress={(e) => { e.stopPropagation(); void toggleTaskComplete(task); }}
                        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                        accessibilityRole="checkbox"
                        accessibilityLabel={
                          isDone
                            ? `Mark task not done: ${stripDuplicateModulePrefix(task.title, task.moduleLabel)}`
                            : `Mark task done: ${stripDuplicateModulePrefix(task.title, task.moduleLabel)}`
                        }
                        accessibilityState={{ checked: isDone }}
                      >
                        {isDone ? (
                          <Ionicons name="checkmark" size={11} color={colors.buttonText} />
                        ) : null}
                      </TouchableOpacity>
                      <View style={styles.taskContent}>
                        <View style={styles.taskTopLine}>
                          <Text style={[styles.taskTime, isDone && styles.taskTimeDone]}>
                            {formatTimeTo12Hour(task.time)}
                          </Text>
                          <Text
                            style={[styles.taskTitle, isDone && styles.taskTitleDone]}
                            numberOfLines={isExpanded ? undefined : 1}
                          >
                            {stripDuplicateModulePrefix(task.title, task.moduleLabel)}
                          </Text>
                        </View>
                        {isExpanded && (
                          <>
                            <Text style={styles.taskMeta} numberOfLines={1}>
                              {task.moduleLabel}{task.duration_minutes ? `  ·  ${task.duration_minutes}m` : ''}
                            </Text>
                            {task.description ? (
                              <Text style={styles.taskDescription}>
                                {task.description}
                              </Text>
                            ) : null}
                            <TouchableOpacity
                              style={styles.askChatRow}
                              onPress={(e) => { e.stopPropagation(); goToChatForTask(task); }}
                              activeOpacity={0.75}
                              accessibilityRole="button"
                              accessibilityLabel={`Ask Max about ${stripDuplicateModulePrefix(task.title, task.moduleLabel)}`}
                            >
                              <Ionicons name="chatbubble-ellipses-outline" size={13} color={colors.textMuted} />
                              <Text style={styles.askChatLabel}>Ask Max</Text>
                            </TouchableOpacity>
                          </>
                        )}
                      </View>
                      <Ionicons
                        name={isExpanded ? 'chevron-up' : 'chevron-down'}
                        size={14}
                        color={colors.textMuted}
                      />
                    </TouchableOpacity>
                  </View>
                );
              })}
            </View>
          ))}
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
    paddingBottom: spacing.md,
  },
  backBtn: {
    width: 40,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xs,
  },
  headerTextCol: {
    flex: 1,
    paddingHorizontal: spacing.xs,
  },
  headerTitle: {
    fontFamily: fonts.serif,
    fontSize: 28,
    fontWeight: '400',
    letterSpacing: -0.4,
    color: colors.foreground,
  },
  daySelectorContainer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
    paddingBottom: spacing.md,
    gap: 20,
    flexGrow: 1,
    alignItems: 'center',
  },
  dayPill: {
    alignItems: 'center',
    paddingHorizontal: 6,
    paddingVertical: 6,
    minWidth: 40,
  },
  dayPillLabel: {
    fontSize: 10,
    fontWeight: '500',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: 2,
  },
  dayPillLabelActive: { color: colors.foreground, fontWeight: '700' },
  dayPillNumber: { fontSize: 14, fontWeight: '500', color: colors.textMuted },
  dayPillNumberActive: { color: colors.foreground, fontWeight: '700' },
  dayUnderline: {
    width: 16,
    height: 2,
    backgroundColor: colors.foreground,
    borderRadius: 1,
    marginTop: 5,
  },
  dayCompleteDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.textSecondary,
    marginTop: 5,
  },
  monthLabel: {
    fontSize: 11,
    fontWeight: '500',
    color: colors.textMuted,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.xs,
    marginTop: spacing.sm,
  },
  timeGroupLabel: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.textMuted,
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  groupSpacer: {
    height: spacing.md,
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
  taskDivider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginHorizontal: -spacing.lg,
  },
  taskRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 14,
    gap: 10,
  },
  taskRowDone: { opacity: 0.45 },
  scheduleTaskAccent: {
    width: 2,
    alignSelf: 'stretch',
    borderRadius: 1,
    opacity: 0.85,
    marginTop: 2,
  },
  taskCheck: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 1.2,
    borderColor: colors.textMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  taskCheckDone: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  taskContent: { flex: 1, minWidth: 0 },
  taskTopLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  taskTime: {
    fontSize: 12,
    fontWeight: '500',
    color: colors.textMuted,
    minWidth: 62,
  },
  taskTimeDone: { textDecorationLine: 'line-through' },
  taskTitle: { fontSize: 15, fontWeight: '500', color: colors.foreground, flex: 1 },
  taskTitleDone: { textDecorationLine: 'line-through', color: colors.textMuted },
  taskMeta: {
    ...typography.caption,
    color: colors.textMuted,
    marginTop: 4,
    marginLeft: 62 + spacing.sm,
  },
  taskDescription: {
    ...typography.bodySmall,
    marginTop: 8,
    lineHeight: 20,
    color: colors.textSecondary,
    marginLeft: 62 + spacing.sm,
  },
  askChatRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 10,
    marginLeft: 62 + spacing.sm,
    paddingVertical: 6,
    paddingHorizontal: 10,
    backgroundColor: colors.surface,
    borderRadius: borderRadius.sm,
    alignSelf: 'flex-start',
  },
  askChatLabel: {
    fontSize: 12,
    fontWeight: '500',
    color: colors.textMuted,
  },
  emptyState: { flex: 1, paddingHorizontal: spacing.xl },
  emptyStateMinimal: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    justifyContent: 'center',
    maxWidth: 360,
    alignSelf: 'center',
    width: '100%',
    paddingBottom: spacing.xxl,
  },
  emptyIconCircle: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.borderLight,
  },
  emptyTitleMinimal: {
    fontFamily: fonts.serif,
    fontSize: 22,
    fontWeight: '400',
    letterSpacing: -0.3,
    color: colors.foreground,
    textAlign: 'center',
  },
  emptySubtitleMinimal: {
    fontSize: 14,
    fontWeight: '400',
    lineHeight: 21,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
    paddingHorizontal: spacing.xs,
  },
  minimalBtn: {
    alignSelf: 'center',
    paddingVertical: 12,
    paddingHorizontal: 28,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.foreground,
    backgroundColor: 'transparent',
  },
  minimalBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.foreground,
    letterSpacing: 0.15,
  },
  emptyTitle: { ...typography.h2, marginTop: spacing.lg, marginBottom: spacing.sm, textAlign: 'center' },
  emptySubtitle: { ...typography.bodySmall, textAlign: 'center', marginBottom: spacing.xl },
  primaryBtn: {
    backgroundColor: colors.foreground,
    paddingHorizontal: spacing.xl,
    paddingVertical: 12,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.foreground,
  },
  primaryBtnText: { ...typography.button },
});