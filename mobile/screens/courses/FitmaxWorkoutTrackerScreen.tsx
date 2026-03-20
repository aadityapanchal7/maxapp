import React, { useMemo, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';
import { defaultWorkoutLibrary, fitmaxAccent } from '../../features/fitmax/fitmax';

export default function FitmaxWorkoutTrackerScreen() {
  const navigation = useNavigation<any>();
  const workouts = useMemo(() => defaultWorkoutLibrary(), []);
  const [exerciseIndex, setExerciseIndex] = useState(0);
  const [setIndex, setSetIndex] = useState(0);
  const [reps, setReps] = useState(10);
  const [weight, setWeight] = useState(40);
  const [restSeconds, setRestSeconds] = useState(90);
  const [showRest, setShowRest] = useState(false);

  const activeWorkout = workouts.Push;
  const current = activeWorkout[Math.min(exerciseIndex, activeWorkout.length - 1)];
  const totalSets = Number((current.setsReps || '3').split('×')[0].trim() || 3);

  const logSet = async () => {
    if (showRest) return;
    const nextSet = setIndex + 1;
    if (nextSet < totalSets) {
      setSetIndex(nextSet);
      setShowRest(true);
      return;
    }

    const nextExercise = exerciseIndex + 1;
    if (nextExercise < activeWorkout.length) {
      setExerciseIndex(nextExercise);
      setSetIndex(0);
      setShowRest(false);
      return;
    }

    try {
      await api.sendChatMessage(`just finished push day. logged session with ${activeWorkout.length} exercises.`, undefined, undefined, 'fitmax');
    } catch (e) {
      console.error(e);
    }
    navigation.goBack();
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn}><Ionicons name="arrow-back" size={22} color={colors.foreground} /></TouchableOpacity>
        <Text style={styles.headerTitle}>Live Workout Tracker</Text>
        <View style={{ width: 36 }} />
      </View>

      <View style={styles.card}>
        <Text style={styles.exerciseName}>{current.name}</Text>
        <Text style={styles.setLabel}>Set {setIndex + 1} of {totalSets}</Text>

        <View style={styles.metricRow}>
          <View style={styles.metricCard}>
            <Text style={styles.metricTitle}>Reps</Text>
            <Text style={styles.metricValue}>{reps}</Text>
            <View style={styles.stepRow}>
              <TouchableOpacity style={styles.stepBtn} onPress={() => setReps(Math.max(1, reps - 1))}><Text style={styles.stepTxt}>-</Text></TouchableOpacity>
              <TouchableOpacity style={styles.stepBtn} onPress={() => setReps(reps + 1)}><Text style={styles.stepTxt}>+</Text></TouchableOpacity>
            </View>
          </View>

          <View style={styles.metricCard}>
            <Text style={styles.metricTitle}>Weight</Text>
            <Text style={styles.metricValue}>{weight}</Text>
            <View style={styles.stepRow}>
              <TouchableOpacity style={styles.stepBtn} onPress={() => setWeight(Math.max(0, weight - 5))}><Text style={styles.stepTxt}>-</Text></TouchableOpacity>
              <TouchableOpacity style={styles.stepBtn} onPress={() => setWeight(weight + 5)}><Text style={styles.stepTxt}>+</Text></TouchableOpacity>
            </View>
          </View>
        </View>

        <TouchableOpacity style={styles.logButton} onPress={logSet}><Text style={styles.logText}>Log Set</Text></TouchableOpacity>
      </View>

      {showRest ? (
        <View style={styles.restCard}>
          <Text style={styles.restLabel}>Rest Timer</Text>
          <Text style={styles.restValue}>{restSeconds}s</Text>
          <View style={styles.restBtns}>
            <TouchableOpacity style={styles.restBtn} onPress={() => setRestSeconds(Math.max(30, restSeconds - 30))}><Text style={styles.restBtnText}>-30s</Text></TouchableOpacity>
            <TouchableOpacity style={styles.restBtn} onPress={() => setRestSeconds(restSeconds + 30)}><Text style={styles.restBtnText}>+30s</Text></TouchableOpacity>
            <TouchableOpacity style={styles.readyBtn} onPress={() => setShowRest(false)}><Text style={styles.readyText}>Ready</Text></TouchableOpacity>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, paddingHorizontal: spacing.lg },
  header: { paddingTop: 60, paddingBottom: spacing.lg, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  headerTitle: { ...typography.h3 },
  card: { backgroundColor: colors.card, borderRadius: borderRadius.xl, padding: spacing.lg, ...shadows.md },
  exerciseName: { fontSize: 28, fontWeight: '700', color: colors.foreground },
  setLabel: { ...typography.bodySmall, marginTop: 6 },
  metricRow: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  metricCard: { flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md },
  metricTitle: { ...typography.caption },
  metricValue: { marginTop: 6, fontSize: 34, fontWeight: '700', color: colors.foreground, letterSpacing: -1 },
  stepRow: { marginTop: spacing.sm, flexDirection: 'row', gap: 8 },
  stepBtn: { flex: 1, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border, alignItems: 'center', paddingVertical: 6, backgroundColor: colors.card },
  stepTxt: { fontSize: 16, fontWeight: '700', color: colors.textSecondary },
  logButton: { marginTop: spacing.lg, height: 56, borderRadius: borderRadius.lg, alignItems: 'center', justifyContent: 'center', backgroundColor: fitmaxAccent },
  logText: { color: colors.buttonText, fontSize: 16, fontWeight: '700' },
  restCard: { marginTop: spacing.lg, backgroundColor: colors.card, borderRadius: borderRadius.xl, padding: spacing.lg, ...shadows.md },
  restLabel: { ...typography.caption, textAlign: 'center' },
  restValue: { marginTop: 4, textAlign: 'center', fontSize: 42, fontWeight: '700', color: fitmaxAccent },
  restBtns: { marginTop: spacing.md, flexDirection: 'row', gap: 8 },
  restBtn: { flex: 1, paddingVertical: 10, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center' },
  restBtnText: { fontSize: 12, fontWeight: '700', color: colors.textSecondary },
  readyBtn: { flex: 1, paddingVertical: 10, borderRadius: borderRadius.full, backgroundColor: fitmaxAccent, alignItems: 'center' },
  readyText: { fontSize: 12, fontWeight: '700', color: colors.buttonText },
});
