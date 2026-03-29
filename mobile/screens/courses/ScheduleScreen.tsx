import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, RefreshControl, Modal, TextInput, Platform,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
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
  const [maxxes, setMaxxes] = useState<any[]>([]);

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

  useEffect(() => {
    api.getMaxxes().then((r) => setMaxxes(r.maxes || [])).catch(() => setMaxxes([]));
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

  const handleCompleteTask = async (taskId: string) => {
    if (!schedule) return;
    try {
      await api.completeScheduleTask(schedule.id, taskId);
      setSchedule(prev => {
        if (!prev) return prev;
        return {
          ...prev, days: prev.days.map(day => ({
            ...day,
            tasks: day.tasks.map(t =>
              t.task_id === taskId ? { ...t, status: 'completed' } : t
            ),
          }))
        };
      });
    } catch (e) {
      console.error('Failed to complete task:', e);
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
          <Ionicons name="calendar-outline" size={64} color={colors.textMuted} />
          <Text style={styles.emptyTitle}>No Active Schedule</Text>
          <Text style={styles.emptySubtitle}>
            Generate a personalised AI schedule for {courseTitle || 'your course module'}.
          </Text>
          <TouchableOpacity
            style={styles.generateButton}
            onPress={handleGenerate}
            disabled={generating}
            activeOpacity={0.7}
          >
            {generating ? (
              <ActivityIndicator color={colors.buttonText} />
            ) : (
              <>
                <Ionicons name="sparkles" size={18} color={colors.buttonText} />
                <Text style={styles.generateButtonText}>Generate AI Schedule</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ── Main schedule view ────────────────────────────────────────────────────
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color={colors.foreground} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>{schedule.course_title}</Text>
        <TouchableOpacity onPress={handleAdapt} style={styles.backButton}>
          <Ionicons name="options-outline" size={22} color={colors.foreground} />
        </TouchableOpacity>
      </View>

      {/* Day selector */}
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
              style={[styles.dayPill, isSelected && styles.dayPillActive, dayCompleted && styles.dayPillDone]}
              onPress={() => setSelectedDayIndex(idx)}
              activeOpacity={0.7}
            >
              <Text style={[styles.dayPillLabel, isSelected && styles.dayPillLabelActive]}>{dayName}</Text>
              <Text style={[styles.dayPillNumber, isSelected && styles.dayPillNumberActive]}>{dayNum}</Text>
              {dayCompleted && <View style={styles.dayCompleteDot} />}
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Tasks */}
      <ScrollView
        style={styles.taskList}
        contentContainerStyle={{ paddingBottom: 100 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.foreground} />}
      >
        {/* Motivation */}
        {selectedDay?.motivation_message ? (
          <View style={styles.motivationCard}>
            <Ionicons name="flash" size={18} color={colors.warning} />
            <Text style={styles.motivationText}>{selectedDay.motivation_message}</Text>
          </View>
        ) : null}

        {/* Progress bar */}
        <View style={styles.progressRow}>
          <Text style={styles.progressText}>{completedCount}/{totalCount} completed</Text>
          <View style={styles.progressBar}>
            <View style={[styles.progressFill, { width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }]} />
          </View>
        </View>

        {fitmaxIndicators.length > 0 && (
          <View style={styles.fitmaxIndicatorCard}>
            <Text style={styles.fitmaxIndicatorTitle}>Fitmax Targets</Text>
            <View style={styles.fitmaxIndicatorWrap}>
              {fitmaxIndicators.map((item) => (
                <View key={item.label} style={styles.fitmaxIndicatorChip}>
                  <Text style={styles.fitmaxIndicatorLabel}>{item.label}</Text>
                  <Text style={styles.fitmaxIndicatorValue}>{item.value}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Task cards */}
        {selectedDay?.tasks?.map((task) => {
          const isDone = task.status === 'completed';
          return (
            <View key={task.task_id} style={[styles.taskCard, isDone && styles.taskCardDone]}>
              <View style={[styles.scheduleTaskAccent, { backgroundColor: scheduleModuleColor }]} />
              {/* Checkbox */}
              <TouchableOpacity
                style={[styles.taskCheck, isDone && styles.taskCheckDone]}
                onPress={() => !isDone && handleCompleteTask(task.task_id)}
              >
                {isDone && <Ionicons name="checkmark" size={14} color={colors.buttonText} />}
              </TouchableOpacity>

              {/* Content */}
              <View style={styles.taskContent}>
                <View style={styles.taskHeader}>
                  <Text style={[styles.taskTime, isDone && styles.taskTimeDone]}>{formatTimeTo12Hour(task.time)}</Text>
                  <View style={styles.taskTypeBadge}>
                    <Ionicons name={getTaskIcon(task.task_type) as any} size={12} color={colors.textMuted} />
                    <Text style={styles.taskTypeText}>{task.duration_minutes}m</Text>
                  </View>
                </View>
                <Text style={[styles.taskTitle, isDone && styles.taskTitleDone]}>{task.title}</Text>
                <Text style={styles.taskDescription} numberOfLines={2}>{task.description}</Text>
              </View>

              {/* Edit / Delete buttons */}
              {!isDone && (
                <View style={styles.taskActions}>
                  <TouchableOpacity onPress={() => openEditModal(task)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                    <Ionicons name="pencil-outline" size={16} color={colors.textMuted} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleDeleteTask(task)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                    <Ionicons name="trash-outline" size={16} color={colors.error} />
                  </TouchableOpacity>
                </View>
              )}
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
    paddingHorizontal: spacing.lg, paddingTop: 64, paddingBottom: spacing.sm,
  },
  backButton: { padding: spacing.xs },
  headerTitle: { ...typography.h3, flex: 1, textAlign: 'center' },

  // Empty state
  emptyState: { flex: 1, paddingHorizontal: spacing.xl },
  emptyTitle: { ...typography.h2, marginTop: spacing.lg, marginBottom: spacing.sm },
  emptySubtitle: { ...typography.bodySmall, textAlign: 'center', marginBottom: spacing.xl },
  generateButton: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    backgroundColor: colors.foreground, paddingHorizontal: spacing.xl, paddingVertical: 14,
    borderRadius: borderRadius.full, ...shadows.md,
  },
  generateButtonText: { ...typography.button },

  // Day selector
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
    paddingVertical: spacing.xs, // slightly shorter height vs original
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
    width: 5, height: 5, borderRadius: 3, backgroundColor: colors.success, marginTop: 3,
  },

  // Tasks
  taskList: { flex: 1, paddingHorizontal: spacing.lg },

  motivationCard: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    backgroundColor: 'rgba(245, 158, 11, 0.08)', padding: spacing.md,
    borderRadius: borderRadius.md, marginBottom: spacing.md, marginTop: spacing.sm,
  },
  motivationText: { ...typography.bodySmall, color: colors.textPrimary, flex: 1, fontStyle: 'italic' },

  progressRow: {
    width: '100%',
    alignItems: 'center',
    marginBottom: spacing.md,
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
  fitmaxIndicatorCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    padding: spacing.md,
    marginBottom: spacing.md,
    ...shadows.sm,
  },
  fitmaxIndicatorTitle: {
    ...typography.label,
    marginBottom: spacing.sm,
  },
  fitmaxIndicatorWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  fitmaxIndicatorChip: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    minWidth: 96,
  },
  fitmaxIndicatorLabel: { ...typography.caption, color: colors.textMuted },
  fitmaxIndicatorValue: { fontSize: 13, fontWeight: '700', color: colors.foreground, marginTop: 2 },

  taskCard: {
    flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md,
    backgroundColor: colors.card, padding: spacing.md, borderRadius: borderRadius.lg,
    marginBottom: spacing.sm, ...shadows.sm,
  },
  taskCardDone: { opacity: 0.6 },
  scheduleTaskAccent: {
    width: 4,
    alignSelf: 'stretch',
    borderRadius: 2,
    minHeight: 44,
  },
  taskCheck: {
    width: 24, height: 24, borderRadius: 12, borderWidth: 2,
    borderColor: colors.border, alignItems: 'center', justifyContent: 'center', marginTop: 2, marginLeft: spacing.xs,
  },
  taskCheckDone: { backgroundColor: colors.success, borderColor: colors.success },

  taskContent: { flex: 1 },
  taskHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  taskTime: { fontSize: 12, fontWeight: '700', color: colors.foreground, letterSpacing: 0.3 },
  taskTimeDone: { textDecorationLine: 'line-through', color: colors.textMuted },
  taskTypeBadge: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  taskTypeText: { ...typography.caption },
  taskTitle: { fontSize: 15, fontWeight: '600', color: colors.foreground, marginBottom: 2 },
  taskTitleDone: { textDecorationLine: 'line-through', color: colors.textMuted },
  taskDescription: { ...typography.bodySmall },

  // Task action buttons (edit / delete)
  taskActions: { gap: 12, alignItems: 'center', paddingTop: 2 },

  // Edit modal
  modalOverlay: {
    flex: 1, backgroundColor: colors.overlay,
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: colors.background, borderTopLeftRadius: borderRadius['2xl'],
    borderTopRightRadius: borderRadius['2xl'], padding: spacing.lg,
    paddingBottom: Platform.OS === 'ios' ? 40 : spacing.lg,
  },
  modalHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: spacing.lg,
  },
  modalTitle: { ...typography.h2 },

  inputLabel: { ...typography.label, marginBottom: spacing.xs, marginTop: spacing.md },
  input: {
    backgroundColor: colors.card, borderRadius: borderRadius.md, padding: spacing.md,
    fontSize: 15, color: colors.foreground, borderWidth: 1, borderColor: colors.border,
  },
  inputMultiline: { minHeight: 80, textAlignVertical: 'top' },

  saveButton: {
    backgroundColor: colors.foreground, padding: spacing.md, borderRadius: borderRadius.full,
    alignItems: 'center', marginTop: spacing.xl, ...shadows.md,
  },
  saveButtonText: { ...typography.button },
  caption: { ...typography.caption, color: colors.textMuted, marginTop: 4 },
});
