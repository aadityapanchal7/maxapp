import React, { useMemo } from 'react';
import { Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { borderRadius, colors, shadows, spacing, typography } from '../../theme/dark';

type CalloutTone = 'key' | 'tip' | 'mistake' | 'research';

type ContentBlock =
  | { type: 'title'; text: string }
  | { type: 'meta'; text: string }
  | { type: 'heading'; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'check'; text: string }
  | { type: 'list'; text: string }
  | { type: 'callout'; tone: CalloutTone; label: string; text: string }
  | { type: 'visual'; text: string }
  | { type: 'table'; text: string };

const TABLE_HINTS = [
  'Method Accuracy Cost Best For',
  'Activity LevelMultiplier',
  'RPEReps Left in TankWhat It Feels Like',
  'GoalTypeFrequencyDurationTiming',
  'ProtocolEvidence LevelEffectNotes',
  'Muscle GroupMEVMAVMRV',
  'Body Fat % (Male)What\'s Visible',
  'Body Fat % (Female)What\'s Visible',
  'Tight/Overactive (Needs Stretching)Weak/Underactive (Needs Strengthening)',
  'Tight/OveractiveWeak/Underactive',
  'SourceProtein per 100 calConvenienceCost',
  'CauseEvidence-Based Intervention',
  'MethodHowWhen',
  'EquipmentPrimary ExerciseAlternative',
  'MistakeWhy It HappensFix',
];

const CALLOUT_ICON_REGEX = /^[\u{1F535}\u{1F7E1}\u{1F534}\u{1F7E2}]\s*/u;

function isCalloutLine(line: string) {
  return CALLOUT_ICON_REGEX.test(line.trim());
}

function isLikelyHeading(text: string) {
  if (!text) return false;
  if (text.length > 90) return false;
  if (/[.!?]$/.test(text)) return false;
  if (/^\d+\./.test(text)) return false;
  if (/^\[.+\]$/.test(text)) return false;
  if (/^\u2610\s+/u.test(text)) return false;
  if (/^[A-Z][A-Za-z\s&/\-,:()'%]+$/.test(text)) return true;
  return /[-:]/.test(text) && text.split(' ').length <= 12;
}

function isTableHeader(line: string) {
  const normalized = line.replace(/\s+/g, ' ').trim();
  return TABLE_HINTS.some(hint => normalized.includes(hint)) || /^\s*Body Fat\s*%/.test(normalized);
}

function parseCallout(text: string): ContentBlock {
  const trimmed = text.trim();
  const body = trimmed.replace(CALLOUT_ICON_REGEX, '');

  if (trimmed.startsWith('\u{1F535}')) {
    return { type: 'callout', tone: 'key', label: 'Key Concept', text: body.replace(/^Key Concept:?\s*/i, '') };
  }

  if (trimmed.startsWith('\u{1F7E1}')) {
    return { type: 'callout', tone: 'tip', label: 'Coach Tip', text: body.replace(/^Coach Tip:?\s*/i, '') };
  }

  if (trimmed.startsWith('\u{1F534}')) {
    return { type: 'callout', tone: 'mistake', label: 'Common Mistake', text: body.replace(/^Common Mistake:?\s*/i, '') };
  }

  return { type: 'callout', tone: 'research', label: 'Research Note', text: body.replace(/^Research Note:?\s*/i, '') };
}

function parseBlocks(content: string): ContentBlock[] {
  const lines = content.replace(/\r/g, '').split('\n').map(line => line.replace(/\u00a0/g, ' ').trimEnd());
  const blocks: ContentBlock[] = [];

  let i = 0;
  while (i < lines.length) {
    const current = lines[i].trim();

    if (!current) {
      i += 1;
      continue;
    }

    if (isTableHeader(current)) {
      const tableLines: string[] = [current];
      i += 1;
      let blanks = 0;

      while (i < lines.length) {
        const next = lines[i].trim();

        if (!next) {
          blanks += 1;
          if (blanks >= 2) {
            i += 1;
            break;
          }
          tableLines.push('');
          i += 1;
          continue;
        }

        if (isCalloutLine(next) || /^\[.+\]$/.test(next)) {
          break;
        }

        if (blanks > 0 && /^[A-Z]/.test(next) && !/[★☆]/.test(next) && next.length > 70) {
          break;
        }

        blanks = 0;
        tableLines.push(next);
        i += 1;
      }

      blocks.push({ type: 'table', text: tableLines.join('\n').trim() });
      continue;
    }

    const paragraphLines: string[] = [current];
    i += 1;

    while (i < lines.length && lines[i].trim()) {
      if (isTableHeader(lines[i].trim())) break;
      paragraphLines.push(lines[i].trim());
      i += 1;
    }

    const paragraph = paragraphLines.join(' ').replace(/\s+/g, ' ').trim();
    if (!paragraph) continue;

    if (paragraph.startsWith('Module ')) {
      blocks.push({ type: 'title', text: paragraph });
      continue;
    }

    if (/^Phase\s+\d+/i.test(paragraph) || /^Personalization Banner:/i.test(paragraph)) {
      blocks.push({ type: 'meta', text: paragraph });
      continue;
    }

    if (isCalloutLine(paragraph)) {
      blocks.push(parseCallout(paragraph));
      continue;
    }

    if (/^\[.+\]$/.test(paragraph)) {
      blocks.push({ type: 'visual', text: paragraph.slice(1, -1) });
      continue;
    }

    if (/^\u2610\s+/u.test(paragraph)) {
      blocks.push({ type: 'check', text: paragraph.replace(/^\u2610\s+/u, '') });
      continue;
    }

    if (/^\d+\.\s+/.test(paragraph)) {
      blocks.push({ type: 'list', text: paragraph });
      continue;
    }

    if (isLikelyHeading(paragraph)) {
      blocks.push({ type: 'heading', text: paragraph });
      continue;
    }

    blocks.push({ type: 'paragraph', text: paragraph });
  }

  return blocks;
}

function calloutColors(tone: CalloutTone) {
  if (tone === 'key') return { border: '#0ea5e9', bg: '#0ea5e914' };
  if (tone === 'tip') return { border: '#f59e0b', bg: '#f59e0b16' };
  if (tone === 'mistake') return { border: '#ef4444', bg: '#ef444416' };
  return { border: '#22c55e', bg: '#22c55e16' };
}

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

  const blocks = useMemo(() => (parsedExercises ? [] : parseBlocks(content)), [content, parsedExercises]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn}>
          <Ionicons name="arrow-back" size={22} color={colors.foreground} />
        </TouchableOpacity>
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
            {blocks.map((block, idx) => {
              if (block.type === 'title') return <Text key={idx} style={styles.moduleTitle}>{block.text}</Text>;
              if (block.type === 'meta') return <Text key={idx} style={styles.metaText}>{block.text}</Text>;
              if (block.type === 'heading') return <Text key={idx} style={styles.headingText}>{block.text}</Text>;
              if (block.type === 'paragraph') return <Text key={idx} style={styles.bodyText}>{block.text}</Text>;
              if (block.type === 'list') return <Text key={idx} style={styles.listText}>{block.text}</Text>;

              if (block.type === 'check') {
                return (
                  <View key={idx} style={styles.checkRow}>
                    <Ionicons name="checkmark-circle-outline" size={18} color={colors.accent} />
                    <Text style={styles.checkText}>{block.text}</Text>
                  </View>
                );
              }

              if (block.type === 'visual') {
                return (
                  <View key={idx} style={styles.visualCard}>
                    <Ionicons name="images-outline" size={16} color={colors.textMuted} />
                    <Text style={styles.visualText}>{block.text}</Text>
                  </View>
                );
              }

              if (block.type === 'table') {
                return (
                  <View key={idx} style={styles.tableCard}>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                      <Text style={styles.tableText}>{block.text}</Text>
                    </ScrollView>
                  </View>
                );
              }

              const palette = calloutColors(block.tone);
              return (
                <View key={idx} style={[styles.callout, { borderColor: palette.border, backgroundColor: palette.bg }]}>
                  <Text style={styles.calloutLabel}>{block.label}</Text>
                  <Text style={styles.calloutText}>{block.text}</Text>
                </View>
              );
            })}
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
  moduleTitle: { fontSize: 24, lineHeight: 30, fontWeight: '700', color: colors.foreground, marginBottom: spacing.md },
  metaText: { ...typography.bodySmall, color: colors.textMuted, marginBottom: spacing.md },
  headingText: { fontSize: 18, lineHeight: 24, fontWeight: '700', color: colors.foreground, marginTop: spacing.sm, marginBottom: spacing.sm },
  bodyText: { ...typography.body, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.md },
  listText: { ...typography.body, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.sm },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: spacing.sm },
  checkText: { ...typography.body, color: colors.textSecondary, flex: 1 },
  callout: { borderLeftWidth: 4, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.md },
  calloutLabel: { fontSize: 12, lineHeight: 18, fontWeight: '700', color: colors.foreground, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 4 },
  calloutText: { ...typography.bodySmall, color: colors.textSecondary, lineHeight: 21 },
  visualCard: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.md },
  visualText: { ...typography.bodySmall, color: colors.textSecondary, flex: 1, lineHeight: 20 },
  tableCard: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.md },
  tableText: {
    color: colors.foreground,
    fontSize: 12,
    lineHeight: 20,
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }),
    minWidth: 320,
  },
  exerciseRow: { paddingBottom: spacing.md, marginBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  exerciseName: { fontSize: 16, fontWeight: '700', color: colors.foreground },
  exerciseMeta: { marginTop: 4, fontSize: 13, fontWeight: '600', color: colors.textSecondary },
  exerciseNote: { marginTop: 6, ...typography.bodySmall },
  tag: { marginTop: 8, alignSelf: 'flex-start', backgroundColor: colors.surface, borderRadius: borderRadius.full, paddingHorizontal: 10, paddingVertical: 4 },
  tagText: { ...typography.caption },
});
