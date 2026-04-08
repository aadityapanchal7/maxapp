import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, RefreshControl, Modal, TextInput, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { queryKeys } from '../../lib/queryClient';
import { useMaxxesQuery } from '../../hooks/useAppQueries';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { buildMaxxMaps, moduleColorForSchedule, moduleLabelForSchedule } from '../../utils/scheduleAggregation';


type Task = {
  task_id: string;
  time: string;
  title: string;
  description: string;
  task_type: string;
  duration_minutes: number;
  status: string;
  notification_sent: boolean;
};

type Day = {
  day_number: number;
  date: string;
  tasks: Task[];
  motivation_message: string;
};

/** Accepts 24h HH:MM or common 12h forms (e.g. 7:30am, 2 pm). */
function parseTimeTo24h(input: string): string | null {
  const s = input.trim();
  if (!s) return null;
  const m24 = /^(\d{1,2}):(\d{2})$/.exec(s);
  if (m24) {
    const h = parseInt(m24[1], 10);
    const mn = parseInt(m24[2], 10);
    if (h > 23 || mn > 59) return null;
    return `${String(h).padStart(2, '0')}:${String(mn).padStart(2, '0')}`;
  }
  const m12 = /^(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|am|pm)\s*$/i.exec(s);
  if (m12) {
    let h = parseInt(m12[1], 10);
    const mn = m12[2] ? parseInt(m12[2], 10) : 0;
    const ap = m12[3].toLowerCase().replace(/\./g, '');
    if (mn > 59 || h < 1 || h > 12) return null;
    let h24: number;
    if (ap.startsWith('a')) {
      h24 = h === 12 ? 0 : h;
    } else {
      h24 = h === 12 ? 12 : h + 12;
    }
    return `${String(h24).padStart(2, '0')}:${String(mn).padStart(2, '0')}`;
  }
  return null;
}

type Schedule = {
  id: string;
  user_id: string;
  schedule_type?: string;
  course_id?: string;
  course_title: string;
  module_number?: number;
  maxx_id?: string;
  days: Day[];
  preferences: any;
  schedule_context?: any;
  is_active: boolean;
  created_at: string;
  adapted_count: number;
};


const formatTimeTo12Hour = (time24: string) => {
  if (!time24 || typeof time24 !== 'string' || !time24.includes(':')) return time24 || '';
  try {
    const [hoursStr, minutesStr] = time24.split(':');
    const hours = parseInt(hoursStr, 10);
    const minutes = parseInt(minutesStr, 10);
    if (isNaN(hours) || isNaN(minutes)) return time24;

    const period = hours >= 12 ? 'PM' : 'AM';
    const hours12 = hours % 12 || 12;
    return `${hours12}:${minutes.toString().padStart(2, '0')} ${period}`;
  } catch (e) {
    return time24;
  }
};

export default function ScheduleScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const insets = useSafeAreaInsets();
  const queryClient = useQueryClient();
  const { courseId, moduleNumber, courseTitle, scheduleId: paramScheduleId, maxxId } = route.params || {};

  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [selectedDayIndex, setSelectedDayIndex] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  // Edit modal state
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [editTime, setEditTime] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editDuration, setEditDuration] = useState('');
  const [saving, setSaving] = useState(false);
  const maxxesQuery = useMaxxesQuery();
  const maxxes = maxxesQuery.data?.maxes ?? [];

  const { labels: maxxLabels, colors: maxxColors } = useMemo(() => buildMaxxMaps(maxxes), [maxxes]);
  const scheduleModuleColor = useMemo(
    () => moduleColorForSchedule(schedule, maxxColors),
    [schedule, maxxColors],
  );
  const scheduleModuleLabel = useMemo(
    () => moduleLabelForSchedule(schedule, maxxLabels),
    [schedule, maxxLabels],
  );

  useEffect(() => {
    loadSchedule();
  }, []);

  const loadSchedule = async () => {
    try {
      let result;
      if (paramScheduleId) {
        result = await api.getSchedule(paramScheduleId);
        if (result.schedule) {
          setSchedule(result.schedule);
        }
      } else if (maxxId) {
        result = await api.getMaxxSchedule(maxxId);
        if (result.schedule) {
          setSchedule(result.schedule);
        }
      } else {
        result = await api.getCurrentSchedule(courseId, moduleNumber);
        if (result.schedule) {
          setSchedule(result.schedule);
        }
      }
      if (result?.schedule) {
        const today = new Date().toISOString().split('T')[0];
        const todayIdx = result.schedule.days.findIndex((d: Day) => d.date === today);
        if (todayIdx >= 0) setSelectedDayIndex(todayIdx);
      }
    } catch (e) {
      console.error('Failed to load schedule:', e);
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadSchedule();
    setRefreshing(false);
  }, []);

  const handleGenerate = async () => {
    if (!courseId || !moduleNumber) {
      Alert.alert('Error', 'Missing course information');
      return;
    }
    setGenerating(true);
    try {
      const result = await api.generateSchedule(courseId, moduleNumber, 7);
      setSchedule(result.schedule);
      setSelectedDayIndex(0);
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Failed to generate schedule');
    } finally {
      setGenerating(false);
    }
  };

  const handleToggleTask = async (taskId: string, currentStatus: string) => {
    if (!schedule) return;
    const completing = currentStatus !== 'completed';
    setSchedule(prev => {
      if (!prev) return prev;
      return {
        ...prev, days: prev.days.map(day => ({
          ...day,
          tasks: day.tasks.map(t =>
            t.task_id === taskId
              ? { ...t, status: completing ? 'completed' : 'pending' }
              : t
          ),
        }))
      };
    });
    try {
      if (completing) {
        await api.completeScheduleTask(schedule.id, taskId);
      } else {
        await api.uncompleteScheduleTask(schedule.id, taskId);
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull });
      const mid = schedule.maxx_id || maxxId;
      if (mid) void queryClient.invalidateQueries({ queryKey: queryKeys.maxxSchedule(mid) });
    } catch (e) {
      console.error('Failed to toggle task:', e);
      setSchedule(prev => {
        if (!prev) return prev;
        return {
          ...prev, days: prev.days.map(day => ({
            ...day,
            tasks: day.tasks.map(t =>
              t.task_id === taskId
                ? { ...t, status: completing ? 'pending' : 'completed' }
                : t
            ),
          }))
        };
      });
    }
  };

  // ── Edit task ─────────────────────────────────────────────────────────────
  const openEditModal = (task: Task) => {
    setEditingTask(task);
    setEditTime(task.time);
    setEditTitle(task.title);
    setEditDescription(task.description);
    setEditDuration(String(task.duration_minutes));
  };

  const handleSaveEdit = async () => {
    if (!schedule || !editingTask) return;
    setSaving(true);
    try {
      const updates: any = {};

      // Basic time validation (24h or 12h natural)
      if (editTime !== editingTask.time) {
        const normalized = parseTimeTo24h(editTime);
        if (!normalized) {
          Alert.alert('Invalid time', 'Try something like 7:30am, 2:15pm, or 14:30');
          setSaving(false);
          return;
        }
        updates.time = normalized;
      }

      if (editTitle !== editingTask.title) updates.title = editTitle;
      if (editDescription !== editingTask.description) updates.description = editDescription;
      const dur = parseInt(editDuration);
      if (!isNaN(dur) && dur !== editingTask.duration_minutes) updates.duration_minutes = dur;

      if (Object.keys(updates).length === 0) {
        setEditingTask(null);
        return;
      }

      await api.editScheduleTask(schedule.id, editingTask.task_id, updates);

      // Optimistic update
      setSchedule(prev => {
        if (!prev) return prev;
        return {
          ...prev, days: prev.days.map(day => ({
            ...day,
            tasks: day.tasks.map(t =>
              t.task_id === editingTask.task_id
                ? { ...t, ...updates }
                : t
            ),
          }))
        };
      });
      setEditingTask(null);
    } catch (e) {
      Alert.alert('Error', 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  // ── Delete task ───────────────────────────────────────────────────────────
  const handleDeleteTask = (task: Task) => {
    Alert.alert(
      'Delete Task',
      `Remove "${task.title}" from your schedule?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive',
          onPress: async () => {
            if (!schedule) return;
            try {
              await api.deleteScheduleTask(schedule.id, task.task_id);
              setSchedule(prev => {
                if (!prev) return prev;
                return {
                  ...prev, days: prev.days.map(day => ({
                    ...day,
                    tasks: day.tasks.filter(t => t.task_id !== task.task_id),
                  }))
                };
              });
            } catch (e) {
              Alert.alert('Error', 'Failed to delete task');
            }
          },
        },
      ]
    );
  };

  const handleAdapt = () => {
    if (!schedule) return;
    Alert.prompt?.(
      'Adapt Schedule',
      'Tell the AI how to adjust your schedule (e.g., "too intense", "need more morning tasks")',
      async (feedback: string) => {
        if (!feedback) return;
        try {
          const result = await api.adaptSchedule(schedule.id, feedback);
          setSchedule(result.schedule);
          Alert.alert('✅ Schedule Adapted', 'Your schedule has been adjusted based on your feedback.');
        } catch (e) {
          Alert.alert('Error', 'Failed to adapt schedule');
        }
      }
    );
  };

  const selectedDay = schedule?.days?.[selectedDayIndex];
  const completedCount = selectedDay?.tasks?.filter(t => t.status === 'completed').length || 0;
  const totalCount = selectedDay?.tasks?.length || 0;
  const isFitmaxSchedule = (schedule?.maxx_id || '').toLowerCase() === 'fitmax' || (schedule?.course_title || '').toLowerCase().includes('fitmax');

  const fitmaxIndicators = (() => {
    if (!isFitmaxSchedule) return [] as Array<{ label: string; value: string }>;

    const context = schedule?.schedule_context || {};
    const calories = context.calories ?? context.calorie_target ?? context.target_calories;
    const protein = context.protein_g ?? context.protein;
    const carbs = context.carbs_g ?? context.carbs;
    const fat = context.fat_g ?? context.fat;
    const split = context.split ?? context.training_split;
    const days = context.weekly_training_days ?? context.training_days;

    const items: Array<{ label: string; value: string }> = [];
    if (calories !== undefined && calories !== null) items.push({ label: 'Calories', value: `${calories}` });
    if (protein !== undefined && protein !== null) items.push({ label: 'Protein', value: `${protein}g` });
    if (carbs !== undefined && carbs !== null) items.push({ label: 'Carbs', value: `${carbs}g` });
    if (fat !== undefined && fat !== null) items.push({ label: 'Fat', value: `${fat}g` });
    if (split) items.push({ label: 'Split', value: `${split}` });
    if (days !== undefined && days !== null) items.push({ label: 'Days/Week', value: `${days}` });
    return items;
  })();

  const getTaskIcon = (type: string) => {
    switch (type) {
      case 'exercise': return 'barbell-outline';
      case 'routine': return 'refresh-outline';
      case 'reminder': return 'notifications-outline';
      case 'checkpoint': return 'flag-outline';
      default: return 'ellipse-outline';
    }
  };

  // ── Empty / generating state ──────────────────────────────────────────────
  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color={colors.foreground} />
      </View>
    );
  }

  if (!schedule) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
            <Ionicons name="arrow-back" size={22} color={colors.foreground} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Schedule</Text>
          <View style={{ width: 40 }} />
        </View>
        <View style={[styles.emptyState, styles.center]}>
          <Ionicons name="calendar-outline" size={36} color={colors.textMuted} style={{ marginBottom: spacing.lg }} />
          <Text style={styles.emptyTitle}>No Active Schedule</Text>
          <TouchableOpacity
            style={styles.generateButton}
            onPress={handleGenerate}
            disabled={generating}
            activeOpacity={0.7}
          >
            {generating ? (
              <ActivityIndicator color={colors.foreground} />
            ) : (
              <Text style={styles.generateButtonText}>Generate Schedule</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ── Main schedule view ────────────────────────────────────────────────────
  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: Math.max(insets.top + spacing.sm, 56) }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color={colors.foreground} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>{schedule.course_title}</Text>
        <TouchableOpacity onPress={handleAdapt} style={styles.backButton}>
          <Ionicons name="options-outline" size={22} color={colors.foreground} />
        </TouchableOpacity>
      </View>

      {/* Day selector — compact strip aligned with Master Schedule */}
      <View style={styles.dayStripWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.daySelectorContainer}>
        {schedule.days.map((day, idx) => {
          const isSelected = idx === selectedDayIndex;
          const date = new Date(day.date + 'T00:00:00');
          const dayName = date.toLocaleDateString('en-US', { weekday: 'short' });
          const dayNum = date.getDate();
          const dayCompleted = (day.tasks?.length ?? 0) > 0 && day.tasks?.every(t => t.status === 'completed');
          return (
            <TouchableOpacity
              key={day.day_number}
              style={styles.dayPill}
              onPress={() => setSelectedDayIndex(idx)}
              activeOpacity={0.7}
            >
              <Text style={[styles.dayPillLabel, isSelected && styles.dayPillLabelActive]}>{dayName}</Text>
              <Text style={[styles.dayPillNumber, isSelected && styles.dayPillNumberActive]}>{dayNum}</Text>
              {isSelected && <View style={styles.dayUnderline} />}
              {!isSelected && dayCompleted && <View style={styles.dayCompleteDot} />}
            </TouchableOpacity>
          );
        })}
        </ScrollView>
      </View>

      {/* Tasks */}
      <ScrollView
        style={styles.taskList}
        contentContainerStyle={{ paddingBottom: 100 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.foreground} />}
      >
        {selectedDay?.motivation_message ? (
          <Text style={styles.motivationText}>{selectedDay.motivation_message}</Text>
        ) : null}

        <View style={styles.progressPanel}>
          <Text style={styles.progressText}>{completedCount}/{totalCount} completed</Text>
          <View style={styles.progressBar}>
            <View style={[styles.progressFill, { width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }]} />
          </View>
        </View>

        {fitmaxIndicators.length > 0 && (
          <View style={styles.fitmaxRow}>
            {fitmaxIndicators.map((item, i) => (
              <React.Fragment key={item.label}>
                {i > 0 && <Text style={styles.fitmaxDot}>·</Text>}
                <Text style={styles.fitmaxPair}>
                  <Text style={styles.fitmaxLabel}>{item.label} </Text>
                  <Text style={styles.fitmaxValue}>{item.value}</Text>
                </Text>
              </React.Fragment>
            ))}
          </View>
        )}

        {selectedDay?.tasks?.map((task, index) => {
          const isDone = task.status === 'completed';
          return (
            <View key={task.task_id}>
              {index > 0 && <View style={styles.taskDivider} />}
              <View style={[styles.taskRow, isDone && styles.taskRowDone]}>
                <View style={styles.taskRowLeft}>
                  <View style={[styles.scheduleTaskAccent, { backgroundColor: scheduleModuleColor }]} />
                  <TouchableOpacity
                    style={[styles.taskCheck, isDone && styles.taskCheckDone]}
                    onPress={() => handleToggleTask(task.task_id, task.status)}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    {isDone && <Ionicons name="checkmark" size={11} color={colors.buttonText} />}
                  </TouchableOpacity>
                </View>
                <View style={styles.taskContent}>
                  <Text style={[styles.taskTime, isDone && styles.taskTimeDone]}>
                    {formatTimeTo12Hour(task.time)}{task.duration_minutes ? ` · ${task.duration_minutes}m` : ''}
                  </Text>
                  <Text style={[styles.taskTitle, isDone && styles.taskTitleDone]}>{task.title}</Text>
                  {task.description ? (
                    <Text style={styles.taskDescription} numberOfLines={2}>{task.description}</Text>
                  ) : null}
                </View>
                {!isDone && (
                  <View style={styles.taskActions}>
                    <TouchableOpacity onPress={() => openEditModal(task)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                      <Ionicons name="pencil-outline" size={13} color={colors.textMuted} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => handleDeleteTask(task)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                      <Ionicons name="trash-outline" size={13} color={colors.textMuted} />
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            </View>
          );
        })}
      </ScrollView>

      {/* ── Edit Task Modal ───────────────────────────────────────────── */}
      <Modal
        visible={!!editingTask}
        transparent
        animationType="slide"
        onRequestClose={() => setEditingTask(null)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Edit Task</Text>
              <TouchableOpacity onPress={() => setEditingTask(null)}>
                <Ionicons name="close" size={24} color={colors.foreground} />
              </TouchableOpacity>
            </View>

            <Text style={styles.inputLabel}>TIME (24-HOUR FORMAT)</Text>
            <TextInput
              style={styles.input}
              value={editTime}
              onChangeText={setEditTime}
              placeholder="e.g. 14:30"
              placeholderTextColor={colors.textMuted}
            />
            <Text style={styles.caption}>Current display: {formatTimeTo12Hour(editTime) || 'Invalid'}</Text>

            <Text style={styles.inputLabel}>TITLE</Text>
            <TextInput
              style={styles.input}
              value={editTitle}
              onChangeText={setEditTitle}
              placeholder="Task title"
              placeholderTextColor={colors.textMuted}
            />

            <Text style={styles.inputLabel}>DESCRIPTION</Text>
            <TextInput
              style={[styles.input, styles.inputMultiline]}
              value={editDescription}
              onChangeText={setEditDescription}
              placeholder="Task description"
              placeholderTextColor={colors.textMuted}
              multiline
              numberOfLines={3}
            />

            <Text style={styles.inputLabel}>DURATION (MINUTES)</Text>
            <TextInput
              style={styles.input}
              value={editDuration}
              onChangeText={setEditDuration}
              placeholder="e.g. 15"
              placeholderTextColor={colors.textMuted}
              keyboardType="number-pad"
            />

            <TouchableOpacity
              style={styles.saveButton}
              onPress={handleSaveEdit}
              disabled={saving}
              activeOpacity={0.7}
            >
              {saving ? (
                <ActivityIndicator color={colors.buttonText} />
              ) : (
                <Text style={styles.saveButtonText}>Save Changes</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}


const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { justifyContent: 'center', alignItems: 'center' },

  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md + 4,
  },
  backButton: { padding: spacing.xs },
  headerTitle: { ...typography.h2, flex: 1, textAlign: 'center' },

  emptyState: { flex: 1, paddingHorizontal: spacing.xl },
  emptyTitle: {
    fontFamily: fonts.serif,
    fontSize: 22,
    color: colors.textPrimary,
    letterSpacing: -0.3,
    marginBottom: spacing.lg,
  },
  generateButton: {
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    borderWidth: 1,
    borderColor: colors.foreground,
    borderRadius: borderRadius.full,
  },
  generateButtonText: {
    fontSize: 13,
    fontWeight: '500' as const,
    color: colors.foreground,
    letterSpacing: 0.3,
  },

  dayStripWrap: {
    flexGrow: 0,
    flexShrink: 0,
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
    fontWeight: '500' as const,
    color: colors.textMuted,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.6,
    marginBottom: 2,
  },
  dayPillLabelActive: { color: colors.foreground, fontWeight: '700' as const },
  dayPillNumber: { fontSize: 14, fontWeight: '500' as const, color: colors.textMuted },
  dayPillNumberActive: { color: colors.foreground, fontWeight: '700' as const },
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

  taskList: { flex: 1, paddingHorizontal: spacing.lg },

  motivationText: {
    fontFamily: fonts.serif,
    fontSize: 16,
    color: colors.textSecondary,
    lineHeight: 26,
    fontStyle: 'italic' as const,
    marginTop: spacing.md,
    marginBottom: spacing.lg + spacing.sm,
    paddingHorizontal: spacing.xs,
  },

  progressPanel: {
    marginBottom: spacing.lg,
  },
  progressText: { ...typography.caption, color: colors.textMuted, marginBottom: spacing.sm },
  progressBar: {
    height: 1,
    backgroundColor: colors.border,
    overflow: 'hidden' as const,
    marginHorizontal: -spacing.lg,
  },
  progressFill: { height: '100%' as const, backgroundColor: colors.textSecondary },

  fitmaxRow: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    alignItems: 'center' as const,
    marginBottom: spacing.lg,
    gap: 6,
  },
  fitmaxDot: { fontSize: 14, color: colors.textMuted, lineHeight: 18 },
  fitmaxPair: { fontSize: 12, lineHeight: 18 },
  fitmaxLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '400' as const },
  fitmaxValue: { color: colors.foreground, fontSize: 12, fontWeight: '600' as const },

  taskDivider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
    marginHorizontal: -spacing.lg,
  },
  taskRow: {
    flexDirection: 'row' as const,
    alignItems: 'flex-start' as const,
    paddingVertical: 24,
    gap: spacing.md,
  },
  taskRowDone: { opacity: 0.5 },
  taskRowLeft: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 8,
    paddingTop: 2,
  },
  scheduleTaskAccent: {
    width: 2,
    height: 18,
    borderRadius: 1,
    opacity: 0.85,
  },
  taskCheck: {
    width: 20, height: 20, borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.textMuted,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  taskCheckDone: { backgroundColor: colors.foreground, borderColor: colors.foreground },

  taskContent: { flex: 1 },
  taskTime: {
    fontSize: 10,
    fontWeight: '500' as const,
    color: colors.textMuted,
    letterSpacing: 1,
    textTransform: 'uppercase' as const,
    marginBottom: 4,
  },
  taskTimeDone: { textDecorationLine: 'line-through' as const },
  taskTitle: {
    fontSize: 15,
    fontWeight: '500' as const,
    color: colors.foreground,
    marginBottom: 3,
  },
  taskTitleDone: { textDecorationLine: 'line-through' as const, color: colors.textMuted },
  taskDescription: { ...typography.bodySmall },

  taskActions: {
    flexDirection: 'row' as const,
    gap: 16,
    alignItems: 'center' as const,
    paddingTop: 2,
  },

  modalOverlay: {
    flex: 1, backgroundColor: colors.overlay,
    justifyContent: 'flex-end' as const,
  },
  modalContent: {
    backgroundColor: colors.background, borderTopLeftRadius: borderRadius['2xl'],
    borderTopRightRadius: borderRadius['2xl'], padding: spacing.lg,
    paddingBottom: Platform.OS === 'ios' ? 40 : spacing.lg,
  },
  modalHeader: {
    flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const,
    marginBottom: spacing.lg,
  },
  modalTitle: { ...typography.h2 },

  inputLabel: { ...typography.label, marginBottom: spacing.xs, marginTop: spacing.md },
  input: {
    backgroundColor: colors.card, borderRadius: borderRadius.md, padding: spacing.md,
    fontSize: 15, color: colors.foreground, borderWidth: 1, borderColor: colors.border,
  },
  inputMultiline: { minHeight: 80, textAlignVertical: 'top' as const },

  saveButton: {
    backgroundColor: colors.foreground,
    paddingVertical: 12,
    paddingHorizontal: spacing.lg,
    borderRadius: borderRadius.md,
    alignItems: 'center' as const,
    marginTop: spacing.xl,
  },
  saveButtonText: { ...typography.button },
  caption: { ...typography.caption, color: colors.textMuted, marginTop: 4 },
});
