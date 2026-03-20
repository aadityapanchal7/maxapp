import React, { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';
import { defaultFitmaxMacroSummary, defaultFitmaxSplit, defaultWorkoutLibrary, fitmaxAccent } from '../../features/fitmax/fitmax';

export default function FitmaxPlanScreen() {
  const navigation = useNavigation<any>();
  const summary = useMemo(() => defaultFitmaxMacroSummary(), []);
  const split = useMemo(() => defaultFitmaxSplit(), []);
  const workouts = useMemo(() => defaultWorkoutLibrary(), []);
  const today = new Date().toLocaleDateString('en-US', { weekday: 'short' });

  const sendEditIntent = async () => {
    try {
      await api.sendChatMessage('I want to adjust my calorie targets', undefined, undefined, 'fitmax');
    } catch (e) {
      console.error(e);
    } finally {
      navigation.goBack();
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn}><Ionicons name="arrow-back" size={22} color={colors.foreground} /></TouchableOpacity>
        <Text style={styles.headerTitle}>Your Fitmax Plan</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.macroCard}>
          <TouchableOpacity style={styles.editBtn} onPress={sendEditIntent}>
            <Text style={styles.editText}>Edit</Text>
          </TouchableOpacity>
          <Text style={styles.calLabel}>Daily Target</Text>
          <Text style={styles.calValue}>{summary.calories.toLocaleString()}</Text>
          <Text style={styles.calUnit}>calories</Text>

          <View style={styles.pillRow}>
            <View style={styles.pill}><Text style={styles.pillText}>Protein {summary.protein}g</Text></View>
            <View style={styles.pill}><Text style={styles.pillText}>Carbs {summary.carbs}g</Text></View>
            <View style={styles.pill}><Text style={styles.pillText}>Fat {summary.fat}g</Text></View>
          </View>

          <Text style={styles.goal}>{summary.goalLabel}</Text>
        </View>

        <Text style={styles.sectionTitle}>Your Training Split</Text>
        <View style={styles.calendarRow}>
          {split.map(day => {
            const isToday = day.day === today;
            return (
              <View key={day.day} style={[styles.dayPill, day.type === 'training' ? styles.dayTrain : styles.dayRest, isToday && styles.todayPill]}>
                <Text style={[styles.dayLabel, day.type === 'training' && styles.dayLabelTrain]}>{day.day}</Text>
                <Text style={[styles.dayShort, day.type === 'training' && styles.dayLabelTrain]}>{day.short}</Text>
              </View>
            );
          })}
        </View>

        <View style={styles.listCard}>
          {split.filter(d => d.type === 'training').map(day => (
            <TouchableOpacity
              key={day.full}
              style={styles.row}
              onPress={() => navigation.navigate('FitmaxModule', { title: day.short, content: JSON.stringify(workouts[day.short as keyof typeof workouts] || []) })}
            >
              <View>
                <Text style={styles.rowTitle}>{day.short}</Text>
                <Text style={styles.rowSub}>{day.full}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  headerTitle: { ...typography.h3 },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  macroCard: { backgroundColor: colors.card, borderRadius: borderRadius.xl, padding: spacing.lg, ...shadows.md },
  editBtn: { position: 'absolute', top: spacing.md, right: spacing.md, paddingHorizontal: 10, paddingVertical: 4, borderRadius: borderRadius.full, backgroundColor: colors.surface },
  editText: { fontSize: 12, fontWeight: '600', color: colors.textSecondary },
  calLabel: { ...typography.caption, textAlign: 'center', marginTop: spacing.md },
  calValue: { fontSize: 44, fontWeight: '700', color: colors.foreground, textAlign: 'center', letterSpacing: -1 },
  calUnit: { ...typography.caption, textAlign: 'center' },
  pillRow: { flexDirection: 'row', gap: 8, marginTop: spacing.md },
  pill: { flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.full, paddingVertical: 8, alignItems: 'center' },
  pillText: { fontSize: 11, fontWeight: '600', color: colors.textSecondary },
  goal: { marginTop: spacing.md, textAlign: 'center', ...typography.bodySmall },
  sectionTitle: { ...typography.h3, marginTop: spacing.xl, marginBottom: spacing.md },
  calendarRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  dayPill: { width: '13%', minWidth: 48, borderRadius: borderRadius.lg, paddingVertical: 8, alignItems: 'center', borderWidth: 1 },
  dayTrain: { backgroundColor: `${fitmaxAccent}18`, borderColor: `${fitmaxAccent}55` },
  dayRest: { backgroundColor: colors.surface, borderColor: colors.border },
  todayPill: { borderWidth: 2, borderColor: fitmaxAccent },
  dayLabel: { ...typography.caption },
  dayLabelTrain: { color: fitmaxAccent, fontWeight: '700' },
  dayShort: { fontSize: 11, fontWeight: '600', color: colors.textSecondary, marginTop: 2 },
  listCard: { marginTop: spacing.md, backgroundColor: colors.card, borderRadius: borderRadius.xl, ...shadows.md },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowTitle: { fontSize: 14, fontWeight: '700', color: colors.foreground },
  rowSub: { ...typography.caption, marginTop: 2 },
});
