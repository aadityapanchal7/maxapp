import React, { useEffect, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { deriveCalorieLogFromMessages, fitmaxAccent } from '../../features/fitmax/fitmax';
import { borderRadius, colors, spacing, typography } from '../../theme/dark';

export default function FitmaxCalorieLogScreen() {
  const navigation = useNavigation<any>();
  const [messages, setMessages] = useState<any[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.getChatHistory();
        setMessages(res.messages || []);
      } catch (e) {
        console.error(e);
      }
    })();
  }, []);

  const log = useMemo(() => deriveCalorieLogFromMessages(messages), [messages]);
  const remaining = Math.max(0, log.targetCalories - log.consumedCalories);
  const pct = Math.min(1, log.consumedCalories / Math.max(1, log.targetCalories));

  const grouped = {
    Breakfast: log.meals.filter(m => m.bucket === 'Breakfast'),
    Lunch: log.meals.filter(m => m.bucket === 'Lunch'),
    Dinner: log.meals.filter(m => m.bucket === 'Dinner'),
    Snacks: log.meals.filter(m => m.bucket === 'Snacks'),
  } as const;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn}><Ionicons name="arrow-back" size={22} color={colors.foreground} /></TouchableOpacity>
        <Text style={styles.headerTitle}>Calorie Log</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.ringCard}>
          <Text style={styles.ringTop}>Today</Text>
          <Text style={styles.ringMain}>{remaining}</Text>
          <Text style={styles.ringSub}>calories remaining</Text>
          <View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${pct * 100}%` }]} /></View>
          <Text style={styles.ringFoot}>{log.consumedCalories} / {log.targetCalories}</Text>
        </View>

        <View style={styles.macroCard}>
          <MacroBar label="Protein" value={log.protein} target={185} />
          <MacroBar label="Carbs" value={log.carbs} target={245} />
          <MacroBar label="Fat" value={log.fat} target={70} />
        </View>

        {(['Breakfast', 'Lunch', 'Dinner', 'Snacks'] as const).map(section => (
          <View key={section} style={styles.mealCard}>
            <Text style={styles.mealTitle}>{section}</Text>
            {grouped[section].length === 0 ? (
              <Text style={styles.empty}>No items logged yet.</Text>
            ) : (
              grouped[section].map((item, idx) => (
                <View key={`${section}-${idx}`} style={styles.mealRow}>
                  <Text style={styles.itemText}>{item.item}</Text>
                  <Text style={styles.itemCal}>{item.calories} cal</Text>
                </View>
              ))
            )}
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

function MacroBar({ label, value, target }: { label: string; value: number; target: number }) {
  const pct = Math.min(1, value / Math.max(1, target));
  return (
    <View style={styles.macroRow}>
      <View style={styles.macroRowHeader}>
        <Text style={styles.macroLabel}>{label}</Text>
        <Text style={styles.macroValue}>{value}g / {target}g</Text>
      </View>
      <View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${pct * 100}%` }]} /></View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  headerTitle: { ...typography.h3 },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  ringCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    padding: spacing.lg,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  ringTop: { ...typography.caption },
  ringMain: { marginTop: 8, fontSize: 44, fontWeight: '700', color: fitmaxAccent, letterSpacing: -1 },
  ringSub: { ...typography.bodySmall },
  ringFoot: { marginTop: 8, ...typography.caption },
  macroCard: {
    marginTop: spacing.md,
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  macroRow: { marginBottom: spacing.md },
  macroRowHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  macroLabel: { fontSize: 13, fontWeight: '700', color: colors.foreground },
  macroValue: { ...typography.caption },
  progressTrack: { width: '100%', height: 8, borderRadius: 999, backgroundColor: colors.surface, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: fitmaxAccent },
  mealCard: {
    marginTop: spacing.md,
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  mealTitle: { fontSize: 15, fontWeight: '700', color: colors.foreground, marginBottom: spacing.sm },
  empty: { ...typography.caption },
  mealRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  itemText: { ...typography.bodySmall, color: colors.textPrimary },
  itemCal: { ...typography.bodySmall },
});
