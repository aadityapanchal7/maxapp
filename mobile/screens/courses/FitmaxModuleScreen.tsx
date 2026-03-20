import React, { useMemo } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';

export default function FitmaxModuleScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const title: string = route.params?.title || 'Module';
  const content: string = route.params?.content || '';

  const parsedExercises = useMemo(() => {
    try {
      const maybe = JSON.parse(content);
      return Array.isArray(maybe) ? maybe : null;
    } catch {
      return null;
    }
  }, [content]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn}><Ionicons name="arrow-back" size={22} color={colors.foreground} /></TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>{title}</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {parsedExercises ? (
          <View style={styles.card}>
            {parsedExercises.map((exercise: any, idx: number) => (
              <View key={`${exercise.name}-${idx}`} style={styles.exerciseRow}>
                <Text style={styles.exerciseName}>{exercise.name}</Text>
                <Text style={styles.exerciseMeta}>{exercise.setsReps}</Text>
                <Text style={styles.exerciseNote}>{exercise.formNote}</Text>
                <View style={styles.tag}><Text style={styles.tagText}>{exercise.equipment}</Text></View>
              </View>
            ))}
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.bodyText}>{content}</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card },
  headerTitle: { ...typography.h3, flex: 1, textAlign: 'center', marginHorizontal: spacing.sm },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  card: { backgroundColor: colors.card, borderRadius: borderRadius.xl, padding: spacing.lg, ...shadows.md },
  bodyText: { ...typography.body, color: colors.textSecondary },
  exerciseRow: { paddingBottom: spacing.md, marginBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  exerciseName: { fontSize: 16, fontWeight: '700', color: colors.foreground },
  exerciseMeta: { marginTop: 4, fontSize: 13, fontWeight: '600', color: colors.textSecondary },
  exerciseNote: { marginTop: 6, ...typography.bodySmall },
  tag: { marginTop: 8, alignSelf: 'flex-start', backgroundColor: colors.surface, borderRadius: borderRadius.full, paddingHorizontal: 10, paddingVertical: 4 },
  tagText: { ...typography.caption },
});
