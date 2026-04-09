import React, { useEffect, useMemo, useState } from 'react';
import { FlatList, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { deriveWeightTrend, fitmaxAccent } from '../../features/fitmax/fitmax';
import { borderRadius, colors, spacing, typography } from '../../theme/dark';

type Tab = 'Body' | 'Lifts' | 'Photos';

export default function FitmaxProgressScreen() {
  const navigation = useNavigation<any>();
  const [tab, setTab] = useState<Tab>('Body');
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

  const trend = useMemo(() => deriveWeightTrend(messages), [messages]);
  const latest = trend[trend.length - 1]?.weight;
  const earliest = trend[0]?.weight;
  const delta = latest != null && earliest != null ? (latest - earliest).toFixed(1) : null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn}><Ionicons name="arrow-back" size={22} color={colors.foreground} /></TouchableOpacity>
        <Text style={styles.headerTitle}>Progress</Text>
        <View style={{ width: 36 }} />
      </View>

      <View style={styles.tabRow}>
        {(['Body', 'Lifts', 'Photos'] as Tab[]).map(t => (
          <TouchableOpacity key={t} style={[styles.tab, tab === t && styles.tabActive]} onPress={() => setTab(t)}>
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'Body' ? (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Weight Trend</Text>
            <Text style={styles.cardMeta}>{trend.length ? `${trend.length} entries` : 'No weigh-ins yet'}</Text>
            {trend.length > 0 ? (
              <View style={styles.graphWrap}>
                {trend.map((p, idx) => {
                  const min = Math.min(...trend.map(v => v.weight));
                  const max = Math.max(...trend.map(v => v.weight));
                  const normalized = max === min ? 0.5 : (p.weight - min) / (max - min);
                  return <View key={`${p.date}-${idx}`} style={[styles.bar, { height: 40 + normalized * 80 }]} />;
                })}
              </View>
            ) : null}
            {delta ? <Text style={styles.delta}>Change: {delta} lbs</Text> : null}
          </View>

          <View style={styles.cardRow}>
            <View style={styles.sparkCard}><Text style={styles.sparkTitle}>Waist</Text><Text style={styles.sparkValue}>32.0 in</Text></View>
            <View style={styles.sparkCard}><Text style={styles.sparkTitle}>Arms</Text><Text style={styles.sparkValue}>15.1 in</Text></View>
          </View>
        </ScrollView>
      ) : null}

      {tab === 'Lifts' ? (
        <FlatList
          contentContainerStyle={styles.content}
          data={[
            { name: 'Bench Press', value: '185 x 5', trend: '+15 lbs / 8w' },
            { name: 'Back Squat', value: '245 x 5', trend: '+25 lbs / 8w' },
            { name: 'Deadlift', value: '305 x 3', trend: '+35 lbs / 8w' },
          ]}
          keyExtractor={(item) => item.name}
          renderItem={({ item }) => (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>{item.name}</Text>
              <Text style={styles.liftVal}>{item.value}</Text>
              <Text style={styles.cardMeta}>{item.trend}</Text>
            </View>
          )}
        />
      ) : null}

      {tab === 'Photos' ? (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Progress Photos</Text>
            <Text style={styles.cardMeta}>Use compare mode from chat cards after you log new photos.</Text>
            <View style={styles.photoGrid}>
              {[1, 2, 3, 4].map(i => (
                <View key={i} style={styles.photoCell}><Ionicons name="image-outline" size={18} color={colors.textMuted} /></View>
              ))}
            </View>
          </View>
        </ScrollView>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  headerTitle: { ...typography.h3 },
  tabRow: { flexDirection: 'row', gap: 8, paddingHorizontal: spacing.lg },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 8, borderRadius: borderRadius.full, backgroundColor: colors.surface },
  tabActive: { backgroundColor: fitmaxAccent },
  tabText: { fontSize: 12, fontWeight: '700', color: colors.textSecondary },
  tabTextActive: { color: colors.buttonText },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl, gap: spacing.md },
  card: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardTitle: { fontSize: 15, fontWeight: '700', color: colors.foreground },
  cardMeta: { ...typography.caption, marginTop: 4 },
  graphWrap: { marginTop: spacing.md, minHeight: 140, flexDirection: 'row', alignItems: 'flex-end', gap: 6 },
  bar: { flex: 1, borderRadius: 6, backgroundColor: fitmaxAccent },
  delta: { marginTop: spacing.sm, ...typography.bodySmall },
  cardRow: { flexDirection: 'row', gap: spacing.md },
  sparkCard: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  sparkTitle: { ...typography.caption },
  sparkValue: { marginTop: 6, fontSize: 18, fontWeight: '700', color: colors.foreground },
  liftVal: { marginTop: 8, fontSize: 24, fontWeight: '700', color: fitmaxAccent },
  photoGrid: { marginTop: spacing.md, flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  photoCell: { width: '48%', aspectRatio: 1, borderRadius: borderRadius.lg, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
});
