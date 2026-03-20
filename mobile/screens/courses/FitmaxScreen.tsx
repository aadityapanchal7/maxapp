import React, { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';
import { FITMAX_MODULES, fitmaxPhaseProgress } from '../../features/fitmax/modules';
import { fitmaxAccent } from '../../features/fitmax/fitmax';
import FitmaxChatPanel from '../../features/fitmax/FitmaxChatPanel';

export default function FitmaxScreen() {
  const navigation = useNavigation<any>();
  const modules = useMemo(() => FITMAX_MODULES, []);
  const progress = useMemo(() => fitmaxPhaseProgress(modules), [modules]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn}><Ionicons name="arrow-back" size={22} color={colors.foreground} /></TouchableOpacity>
        <Text style={styles.title}>Fitmax</Text>
        <View style={{ width: 36 }} />
      </View>

      <View style={styles.courseSection}>
        <Text style={styles.sectionLabel}>Course</Text>
        <Text style={styles.progressText}>{progress.currentPhase} · {progress.completed} of {progress.total} modules complete</Text>
        <View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${Math.max(4, progress.ratio * 100)}%` }]} /></View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.moduleRow}>
          {modules.map(module => {
            const accent = module.phase === 'Foundation' ? '#0ea5e9' : module.phase === 'Execution' ? '#22c55e' : module.phase === 'Optimization' ? '#f59e0b' : '#a855f7';
            const status = module.status === 'complete' ? 'Complete' : module.status === 'in_progress' ? 'In Progress' : module.status === 'available' ? 'Available' : 'Locked';
            return (
              <TouchableOpacity
                key={module.id}
                style={[styles.moduleCard, module.status === 'locked' && styles.lockedCard]}
                onPress={() => navigation.navigate('FitmaxModule', { title: `Module ${module.id} · ${module.title}`, content: module.content })}
                activeOpacity={0.8}
              >
                <View style={[styles.moduleAccent, { backgroundColor: accent }]} />
                <Text style={styles.moduleNum}>Module {module.id}</Text>
                <Text style={styles.moduleTitle} numberOfLines={2}>{module.title}</Text>
                <Text style={styles.moduleMeta}>{module.phase}</Text>
                <Text style={[styles.moduleStatus, module.status === 'complete' && { color: colors.success }]}>{status}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      <View style={styles.chatSection}>
        <Text style={styles.sectionLabel}>Chat</Text>
        <FitmaxChatPanel
          onOpenPlan={() => navigation.navigate('FitmaxPlan')}
          onOpenCalorieLog={() => navigation.navigate('FitmaxCalorieLog')}
          onOpenProgress={() => navigation.navigate('FitmaxProgress')}
          onOpenWorkout={() => navigation.navigate('FitmaxWorkoutTracker')}
          onOpenModule={(moduleId) => {
            const module = modules.find(m => m.id === moduleId) || modules[0];
            navigation.navigate('FitmaxModule', { title: `Module ${module.id} · ${module.title}`, content: module.content });
          }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  title: { ...typography.h3 },
  sectionLabel: { ...typography.label, marginBottom: spacing.xs },
  courseSection: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  progressText: { ...typography.bodySmall },
  progressTrack: { marginTop: 6, height: 6, borderRadius: 999, backgroundColor: colors.surface, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: fitmaxAccent },
  moduleRow: { paddingTop: spacing.md, paddingBottom: spacing.sm, gap: spacing.sm, paddingRight: spacing.lg },
  moduleCard: { width: 190, backgroundColor: colors.card, borderRadius: borderRadius.lg, padding: spacing.md, ...shadows.md },
  lockedCard: { opacity: 0.7 },
  moduleAccent: { width: 26, height: 4, borderRadius: 4, marginBottom: 8 },
  moduleNum: { ...typography.caption },
  moduleTitle: { fontSize: 14, fontWeight: '700', color: colors.foreground, marginTop: 4 },
  moduleMeta: { ...typography.caption, marginTop: 6 },
  moduleStatus: { fontSize: 11, fontWeight: '700', color: fitmaxAccent, marginTop: 4 },
  chatSection: { flex: 1, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
});
