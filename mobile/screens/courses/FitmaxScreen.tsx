import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';
import { FITMAX_MODULES, fitmaxPhaseProgress } from '../../features/fitmax/modules';
import { fitmaxAccent } from '../../features/fitmax/fitmax';

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

  useEffect(() => {
    let mounted = true;
    const loadSchedule = async () => {
      try {
        const scheduleRes = await api.getMaxxSchedule('fitmax');
        if (mounted) setActiveSchedule(scheduleRes?.schedule || null);
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

        <Text style={styles.headerTitle}>Fitmax</Text>
        <Text style={styles.headerDescription}>
          Your course modules live here. Schedule changes happen with your coach in Chat.
        </Text>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.scheduleActions}>
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

          {loadingSchedule ? (
            <View style={styles.scheduleLoadingRow}>
              <ActivityIndicator size="small" color={colors.textMuted} />
              <Text style={styles.scheduleLoadingText}>Checking your schedule...</Text>
            </View>
          ) : activeSchedule ? (
            <TouchableOpacity
              style={styles.viewScheduleButton}
              activeOpacity={0.85}
              onPress={() => navigation.navigate('Schedule', { scheduleId: activeSchedule.id })}
            >
              <Ionicons name="eye-outline" size={20} color={colors.foreground} />
              <Text style={styles.viewScheduleText}>View Schedule</Text>
            </TouchableOpacity>
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
  headerTitle: { fontSize: 28, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
  headerDescription: { ...typography.bodySmall, marginTop: spacing.xs },
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
