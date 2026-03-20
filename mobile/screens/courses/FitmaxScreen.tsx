import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';
import { FITMAX_MODULES, fitmaxPhaseProgress } from '../../features/fitmax/modules';
import { defaultFitmaxMacroSummary, deriveCalorieLogFromMessages, fitmaxAccent } from '../../features/fitmax/fitmax';

const MODULE_PHASE_ACCENTS: Record<string, string> = {
  Foundation: '#0ea5e9',
  Execution: '#22c55e',
  Optimization: '#f59e0b',
  'Identity & Mastery': '#a855f7',
};

function moduleStatusLabel(status: 'locked' | 'available' | 'in_progress' | 'complete') {
  if (status === 'complete') return 'Complete';
  if (status === 'in_progress') return 'In Progress';
  if (status === 'available') return 'Available';
  return 'Locked';
}

function modulePreview(content: string) {
  const cleaned = content.replace(/\s+/g, ' ').trim();
  return cleaned.length > 140 ? `${cleaned.slice(0, 140)}...` : cleaned;
}

export default function FitmaxScreen() {
  const navigation = useNavigation<any>();
  const modules = useMemo(() => FITMAX_MODULES, []);
  const progress = useMemo(() => fitmaxPhaseProgress(modules), [modules]);
  const [loadingSchedule, setLoadingSchedule] = useState(true);
  const [activeSchedule, setActiveSchedule] = useState<any>(null);
  const [activeCount, setActiveCount] = useState(0);
  const [activeLabels, setActiveLabels] = useState<string[]>([]);
  const atLimit = !activeSchedule && activeCount >= 2;
  const [macroSnapshot, setMacroSnapshot] = useState({
    caloriesTarget: defaultFitmaxMacroSummary().calories,
    caloriesConsumed: 0,
    proteinTarget: defaultFitmaxMacroSummary().protein,
    proteinConsumed: 0,
    carbsTarget: defaultFitmaxMacroSummary().carbs,
    carbsConsumed: 0,
    fatTarget: defaultFitmaxMacroSummary().fat,
    fatConsumed: 0,
  });

  useEffect(() => {
    let mounted = true;
    const loadSchedule = async () => {
      try {
        const [scheduleRes, chatRes] = await Promise.all([
          api.getMaxxSchedule('fitmax'),
          api.getChatHistory(),
        ]);

        if (mounted) setActiveSchedule(scheduleRes?.schedule || null);

        try {
          const activeRes = await api.getActiveSchedules();
          if (mounted) { setActiveCount(activeRes.count); setActiveLabels(activeRes.labels); }
        } catch {}

        const context = scheduleRes?.schedule?.schedule_context || {};
        const targetCalories = Number(context.calories ?? context.calorie_target ?? context.target_calories ?? defaultFitmaxMacroSummary().calories);
        const targetProtein = Number(context.protein_g ?? context.protein ?? defaultFitmaxMacroSummary().protein);
        const targetCarbs = Number(context.carbs_g ?? context.carbs ?? defaultFitmaxMacroSummary().carbs);
        const targetFat = Number(context.fat_g ?? context.fat ?? defaultFitmaxMacroSummary().fat);

        const derived = deriveCalorieLogFromMessages(chatRes?.messages || []);
        if (mounted) {
          setMacroSnapshot({
            caloriesTarget: Number.isFinite(targetCalories) ? targetCalories : defaultFitmaxMacroSummary().calories,
            caloriesConsumed: derived.consumedCalories,
            proteinTarget: Number.isFinite(targetProtein) ? targetProtein : defaultFitmaxMacroSummary().protein,
            proteinConsumed: derived.protein,
            carbsTarget: Number.isFinite(targetCarbs) ? targetCarbs : defaultFitmaxMacroSummary().carbs,
            carbsConsumed: derived.carbs,
            fatTarget: Number.isFinite(targetFat) ? targetFat : defaultFitmaxMacroSummary().fat,
            fatConsumed: derived.fat,
          });
        }
      } catch (error) {
        console.error('Failed to load Fitmax schedule', error);
      } finally {
        if (mounted) setLoadingSchedule(false);
      }
    };

    loadSchedule();
    return () => {
      mounted = false;
    };
  }, []);

  const doStopSchedule = async () => {
    if (!activeSchedule) return;
    try {
      await api.stopSchedule(activeSchedule.id);
      setActiveSchedule(null);
      try {
        const r = await api.getActiveSchedules();
        setActiveCount(r.count);
        setActiveLabels(r.labels);
      } catch {}
    } catch {
      if (Platform.OS === 'web') {
        window.alert('Could not stop schedule. Try again.');
      } else {
        Alert.alert('Error', 'Could not stop schedule. Try again.');
      }
    }
  };

  const handleStopSchedule = () => {
    if (!activeSchedule) return;
    if (Platform.OS === 'web') {
      const ok = window.confirm('Stop your fitmax schedule? You can restart it anytime.');
      if (ok) doStopSchedule();
    } else {
      Alert.alert(
        'Stop fitmax schedule?',
        'This will deactivate your fitmax schedule. You can restart it anytime.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Stop', style: 'destructive', onPress: () => doStopSchedule() },
        ]
      );
    }
  };

  const remainingCalories = Math.max(0, macroSnapshot.caloriesTarget - macroSnapshot.caloriesConsumed);
  const proteinLeft = Math.max(0, macroSnapshot.proteinTarget - macroSnapshot.proteinConsumed);
  const carbsLeft = Math.max(0, macroSnapshot.carbsTarget - macroSnapshot.carbsConsumed);
  const fatLeft = Math.max(0, macroSnapshot.fatTarget - macroSnapshot.fatConsumed);

  return (
    <View style={styles.container}>
      <View style={styles.headerWrap}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backButton}
          hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
        >
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </TouchableOpacity>

        <View style={styles.headerIcon}>
          <Ionicons name="barbell-outline" size={28} color={fitmaxAccent} />
        </View>

        <View style={styles.macroChip}>
          <Text style={styles.macroChipTitle}>Today</Text>
          <Text style={styles.macroChipCalories}>{remainingCalories} cal left</Text>
          <Text style={styles.macroChipMacros}>P {proteinLeft}g · C {carbsLeft}g · F {fatLeft}g</Text>
        </View>

        <Text style={styles.headerTitle}>Fitmax</Text>
        <Text style={styles.headerDescription}>
          Your course modules live here. Schedule changes happen with your coach in Chat.
        </Text>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.scheduleActions}>
          {atLimit ? (
            <View style={styles.limitBanner}>
              <Ionicons name="alert-circle-outline" size={18} color="#f59e0b" />
              <Text style={styles.limitBannerText}>
                You have 2 active modules ({activeLabels.join(', ')}). Stop one to start fitmax.
              </Text>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.scheduleButton}
              activeOpacity={0.85}
              onPress={() => {
                navigation.navigate('Main', {
                  screen: 'Chat',
                  params: { initSchedule: 'fitmax' },
                });
              }}
            >
              <Ionicons name="calendar-outline" size={20} color={colors.buttonText} />
              <Text style={styles.scheduleButtonText}>{activeSchedule ? 'Update Schedule' : 'Start Schedule'}</Text>
            </TouchableOpacity>
          )}

          {loadingSchedule ? (
            <View style={styles.scheduleLoadingRow}>
              <ActivityIndicator size="small" color={colors.textMuted} />
              <Text style={styles.scheduleLoadingText}>Checking your schedule...</Text>
            </View>
          ) : activeSchedule ? (
            <>
              <TouchableOpacity
                style={styles.viewScheduleButton}
                activeOpacity={0.85}
                onPress={() => navigation.navigate('Schedule', { scheduleId: activeSchedule.id })}
              >
                <Ionicons name="eye-outline" size={20} color={colors.foreground} />
                <Text style={styles.viewScheduleText}>View Schedule</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.stopButton}
                activeOpacity={0.85}
                onPress={handleStopSchedule}
              >
                <Ionicons name="stop-circle-outline" size={20} color="#ef4444" />
                <Text style={styles.stopButtonText}>Stop Schedule</Text>
              </TouchableOpacity>
            </>
          ) : null}
        </View>

        <View style={styles.progressCard}>
          <Text style={styles.sectionLabel}>Course Progress</Text>
          <Text style={styles.progressText}>{progress.currentPhase} - {progress.completed} of {progress.total} modules complete</Text>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.max(4, progress.ratio * 100)}%` }]} />
          </View>
        </View>

        <Text style={styles.modulesLabel}>Modules</Text>

        {modules.map(module => {
          const phaseAccent = MODULE_PHASE_ACCENTS[module.phase] || fitmaxAccent;
          const statusLabel = moduleStatusLabel(module.status);
          const preview = modulePreview(module.content);

          return (
            <TouchableOpacity
              key={module.id}
              style={[styles.moduleCard, module.status === 'locked' && styles.moduleCardLocked]}
              activeOpacity={0.85}
              onPress={() =>
                navigation.navigate('FitmaxModule', {
                  title: `Module ${module.id} - ${module.title}`,
                  content: module.content,
                })
              }
            >
              <View style={styles.moduleHeaderRow}>
                <View style={[styles.phaseDot, { backgroundColor: phaseAccent }]} />
                <Text style={styles.moduleNumber}>Module {module.id}</Text>
                <Text style={[styles.moduleStatus, module.status === 'complete' && styles.moduleStatusComplete]}>{statusLabel}</Text>
              </View>

              <Text style={styles.moduleTitle}>{module.title}</Text>
              <Text style={styles.moduleMeta}>{module.phase} - {module.duration} - {module.level}</Text>
              <Text style={styles.modulePreview}>{preview}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  headerWrap: {
    paddingTop: 56,
    paddingBottom: spacing.lg,
    paddingHorizontal: spacing.lg,
    borderBottomLeftRadius: 24,
    borderBottomRightRadius: 24,
    backgroundColor: '#16a34a14',
  },
  backButton: { marginBottom: spacing.md },
  headerIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
    backgroundColor: '#16a34a1f',
  },
  headerTitle: { fontSize: 28, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5, paddingRight: 160 },
  headerDescription: { ...typography.bodySmall, marginTop: spacing.xs, paddingRight: 160 },
  macroChip: {
    position: 'absolute',
    right: spacing.lg,
    top: 64,
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 10,
    paddingVertical: 8,
    ...shadows.sm,
  },
  macroChipTitle: { ...typography.caption, color: colors.textMuted },
  macroChipCalories: { fontSize: 12, fontWeight: '700', color: colors.foreground, marginTop: 2 },
  macroChipMacros: { fontSize: 11, color: colors.textSecondary, marginTop: 2 },
  scroll: { flex: 1 },
  scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  sectionLabel: { ...typography.label, marginBottom: spacing.xs },
  progressCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    ...shadows.md,
  },
  progressText: { ...typography.bodySmall },
  progressTrack: { marginTop: 8, height: 6, borderRadius: 999, backgroundColor: colors.surface, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: fitmaxAccent },
  scheduleActions: { marginBottom: spacing.lg, gap: spacing.md },
  scheduleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: colors.foreground,
    paddingVertical: 14,
    borderRadius: borderRadius.xl,
    ...shadows.md,
  },
  scheduleButtonText: { fontSize: 16, fontWeight: '600', color: colors.buttonText },
  viewScheduleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 14,
  },
  viewScheduleText: { fontSize: 16, fontWeight: '600', color: colors.foreground },
  stopButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: '#ef444440',
    backgroundColor: '#ef444410',
  },
  stopButtonText: { fontSize: 16, fontWeight: '600', color: '#ef4444' },
  limitBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#f59e0b15',
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: '#f59e0b40',
    paddingVertical: 14,
    paddingHorizontal: spacing.lg,
  },
  limitBannerText: { flex: 1, fontSize: 14, color: colors.textSecondary, lineHeight: 20 },
  scheduleLoadingRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  scheduleLoadingText: { ...typography.bodySmall },
  modulesLabel: { ...typography.label, marginBottom: spacing.md },
  moduleCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    padding: spacing.lg,
    marginBottom: spacing.md,
    ...shadows.md,
  },
  moduleCardLocked: { opacity: 0.72 },
  moduleHeaderRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.sm },
  phaseDot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
  moduleNumber: { ...typography.caption, flex: 1 },
  moduleStatus: { fontSize: 11, fontWeight: '700', color: fitmaxAccent },
  moduleStatusComplete: { color: colors.success },
  moduleTitle: { fontSize: 17, lineHeight: 24, fontWeight: '700', color: colors.foreground },
  moduleMeta: { ...typography.caption, marginTop: 6 },
  modulePreview: { ...typography.bodySmall, marginTop: spacing.sm, lineHeight: 20 },
});
