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

type ParsedGridTable = {
  columns: string[];
  rows: string[][];
};

type ModuleSection = {
  id: string;
  title: string;
  blocks: ContentBlock[];
};

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

  if (trimmed.startsWith('\u{1F535}')) return { type: 'callout', tone: 'key', label: 'Key Concept', text: body.replace(/^Key Concept:?\s*/i, '') };
  if (trimmed.startsWith('\u{1F7E1}')) return { type: 'callout', tone: 'tip', label: 'Coach Tip', text: body.replace(/^Coach Tip:?\s*/i, '') };
  if (trimmed.startsWith('\u{1F534}')) return { type: 'callout', tone: 'mistake', label: 'Common Mistake', text: body.replace(/^Common Mistake:?\s*/i, '') };
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

        if (isCalloutLine(next) || /^\[.+\]$/.test(next)) break;
        if (blanks > 0 && /^[A-Z]/.test(next) && !/[★☆]/.test(next) && next.length > 70) break;

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

function normalizeTableRows(rawText: string) {
  const lines = rawText.split('\n').map(line => line.trim()).filter(Boolean);
  if (lines.length <= 1) return lines;

  const mergedRows: string[] = [lines[0]];
  let current = '';

  for (const line of lines.slice(1)) {
    if (!current) {
      current = line;
      continue;
    }

    const isStandaloneStars = /^[★☆]+$/.test(line);
    const looksLikeNewRow = /[★☆]{2,}/.test(line) || /^([A-Za-z][A-Za-z\s/()\-+%]{2,40})\s+[×x]\s*\d/.test(line);

    if (isStandaloneStars) {
      current = `${current} ${line}`.trim();
      continue;
    }

    if (looksLikeNewRow) {
      mergedRows.push(current);
      current = line;
      continue;
    }

    current = `${current} ${line}`.trim();
  }

  if (current) mergedRows.push(current);
  return mergedRows;
}

function parseRecoveryTable(lines: string[]): ParsedGridTable | null {
  const rows: string[][] = [];
  const effects = ['Significant for DOMS', 'Significant', 'Massive', 'Moderate', 'Small'];

  for (const rowText of lines.slice(1)) {
    const starMatch = rowText.match(/([★☆]{2,})/);
    if (!starMatch || starMatch.index === undefined) continue;

    const protocol = rowText.slice(0, starMatch.index).trim();
    const evidence = starMatch[1].trim();
    const afterStars = rowText.slice(starMatch.index + starMatch[1].length).trim();
    const effect = effects.find(item => afterStars.startsWith(item));
    if (!effect) continue;

    const notes = afterStars.slice(effect.length).trim();
    rows.push([protocol, evidence, effect, notes]);
  }

  if (!rows.length) return null;
  return { columns: ['Protocol', 'Evidence Level', 'Effect', 'Notes'], rows };
}

function parseMethodTable(lines: string[]): ParsedGridTable | null {
  const rows: string[][] = [];
  const costTokens = ['$50–150 per scan', 'Free at many gyms', 'Cheap', 'Free'];

  for (const rowText of lines.slice(1)) {
    const starMatch = rowText.match(/([★☆]{2,})/);
    if (!starMatch || starMatch.index === undefined) continue;

    const method = rowText.slice(0, starMatch.index).trim();
    const accuracy = starMatch[1].trim();
    const afterStars = rowText.slice(starMatch.index + starMatch[1].length).trim();
    const cost = costTokens.find(token => afterStars.includes(token));
    if (!cost) continue;

    const costIndex = afterStars.indexOf(cost);
    const bestFor = afterStars.slice(costIndex + cost.length).trim();
    rows.push([method, accuracy, cost, bestFor]);
  }

  if (!rows.length) return null;
  return { columns: ['Method', 'Accuracy', 'Cost', 'Best For'], rows };
}

function parseTableGrid(rawText: string): ParsedGridTable | null {
  const rows = normalizeTableRows(rawText);
  const header = rows[0]?.replace(/\s+/g, ' ').trim() || '';

  if (header.includes('ProtocolEvidence LevelEffectNotes')) return parseRecoveryTable(rows);
  if (header.includes('Method Accuracy Cost Best For')) return parseMethodTable(rows);
  return null;
}

function calloutColors(tone: CalloutTone) {
  if (tone === 'key') return { border: '#0ea5e9', bg: '#0ea5e914' };
  if (tone === 'tip') return { border: '#f59e0b', bg: '#f59e0b16' };
  if (tone === 'mistake') return { border: '#ef4444', bg: '#ef444416' };
  return { border: '#22c55e', bg: '#22c55e16' };
}

function splitReadingChunks(text: string) {
  const sentences = text.split(/(?<=[.!?])\s+/).map(s => s.trim()).filter(Boolean);
  if (sentences.length <= 2) return [text];

  const chunks: string[] = [];
  for (let i = 0; i < sentences.length; i += 2) {
    chunks.push(sentences.slice(i, i + 2).join(' '));
  }
  return chunks;
}

function splitSections(blocks: ContentBlock[]) {
  const leadBlocks: ContentBlock[] = [];
  const sections: ModuleSection[] = [];
  let current: ModuleSection | null = null;

  blocks.forEach((block, idx) => {
    if (block.type === 'heading') {
      if (current && current.blocks.length) sections.push(current);
      current = { id: `section-${idx}`, title: block.text, blocks: [] };
      return;
    }

    if (!current) {
      leadBlocks.push(block);
      return;
    }

    current.blocks.push(block);
  });

  if (current) sections.push(current);

  if (!sections.length && leadBlocks.length) {
    return { leadBlocks: [] as ContentBlock[], sections: [{ id: 'section-content', title: 'Content', blocks: leadBlocks }] };
  }

  return { leadBlocks, sections };
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
  const { leadBlocks, sections } = useMemo(() => splitSections(blocks), [blocks]);

  const renderBlock = (block: ContentBlock, idxKey: string) => {
    if (block.type === 'title') return <Text key={idxKey} style={styles.moduleTitle}>{block.text}</Text>;
    if (block.type === 'meta') return <Text key={idxKey} style={styles.metaText}>{block.text}</Text>;

    if (block.type === 'paragraph') {
      const chunks = splitReadingChunks(block.text);
      return (
        <View key={idxKey} style={styles.paragraphGroup}>
          {chunks.map((chunk, chunkIdx) => (
            <Text key={`${idxKey}-${chunkIdx}`} style={styles.bodyText}>{chunk}</Text>
          ))}
        </View>
      );
    }

    if (block.type === 'list') return <Text key={idxKey} style={styles.listText}>{block.text}</Text>;

    if (block.type === 'check') {
      return (
        <View key={idxKey} style={styles.checkRow}>
          <Ionicons name="checkmark-circle-outline" size={18} color={colors.accent} />
          <Text style={styles.checkText}>{block.text}</Text>
        </View>
      );
    }

    if (block.type === 'visual') {
      return (
        <View key={idxKey} style={styles.visualCard}>
          <Ionicons name="images-outline" size={16} color={colors.textMuted} />
          <Text style={styles.visualText}>{block.text}</Text>
        </View>
      );
    }

    if (block.type === 'table') {
      const parsedTable = parseTableGrid(block.text);

      if (parsedTable) {
        return (
          <View key={idxKey} style={styles.tableCard}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View style={styles.tableGridWrap}>
                <View style={styles.tableRow}>
                  {parsedTable.columns.map((column, columnIdx) => (
                    <View key={`${idxKey}-header-${columnIdx}`} style={[styles.tableCell, styles.tableHeaderCell]}>
                      <Text style={styles.tableHeaderText}>{column}</Text>
                    </View>
                  ))}
                </View>

                {parsedTable.rows.map((row, rowIdx) => (
                  <View key={`${idxKey}-row-${rowIdx}`} style={styles.tableRow}>
                    {row.map((cell, cellIdx) => (
                      <View key={`${idxKey}-row-${rowIdx}-cell-${cellIdx}`} style={styles.tableCell}>
                        <Text style={styles.tableCellText}>{cell}</Text>
                      </View>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
          </View>
        );
      }

      return (
        <View key={idxKey} style={styles.tableCard}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <Text style={styles.tableText}>{block.text}</Text>
          </ScrollView>
        </View>
      );
    }

    if (block.type === 'heading') return null;

    const palette = calloutColors(block.tone);
    const calloutChunks = splitReadingChunks(block.text);
    return (
      <View key={idxKey} style={[styles.callout, { borderColor: palette.border, backgroundColor: palette.bg }]}>
        <Text style={styles.calloutLabel}>{block.label}</Text>
        {calloutChunks.map((chunk, chunkIdx) => (
          <Text key={`${idxKey}-callout-${chunkIdx}`} style={styles.calloutText}>{chunk}</Text>
        ))}
      </View>
    );
  };

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
            {leadBlocks.map((block, idx) => renderBlock(block, `lead-${idx}`))}

            {sections.map(section => {
              return (
                <View key={section.id} style={styles.sectionCard}>
                  <View style={styles.sectionHeader}>
                    <Text style={styles.headingText}>{section.title}</Text>
                  </View>

                  <View style={styles.sectionBody}>
                    {section.blocks.map((block, idx) => renderBlock(block, `${section.id}-${idx}`))}
                  </View>
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
  card: { backgroundColor: colors.card, borderRadius: borderRadius.xl, padding: spacing.xl, ...shadows.md },
  moduleTitle: { fontSize: 24, lineHeight: 30, fontWeight: '700', color: colors.foreground, marginBottom: spacing.md },
  metaText: { ...typography.bodySmall, color: colors.textMuted, marginBottom: spacing.lg },
  headingText: { fontSize: 18, lineHeight: 24, fontWeight: '700', color: colors.foreground, flex: 1, paddingRight: spacing.sm },
  sectionCard: { borderWidth: 1, borderColor: colors.border, borderRadius: borderRadius.md, marginBottom: spacing.md, overflow: 'hidden', backgroundColor: colors.background },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.surface },
  sectionBody: { paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.sm },
  paragraphGroup: { marginBottom: spacing.md },
  bodyText: { ...typography.body, color: colors.textSecondary, lineHeight: 26, marginBottom: spacing.sm },
  listText: { ...typography.body, color: colors.textSecondary, lineHeight: 26, marginBottom: spacing.md },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: spacing.sm },
  checkText: { ...typography.body, color: colors.textSecondary, flex: 1 },
  callout: { borderLeftWidth: 4, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.lg },
  calloutLabel: { fontSize: 12, lineHeight: 18, fontWeight: '700', color: colors.foreground, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 4 },
  calloutText: { ...typography.bodySmall, color: colors.textSecondary, lineHeight: 22, marginBottom: 6 },
  visualCard: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.md },
  visualText: { ...typography.bodySmall, color: colors.textSecondary, flex: 1, lineHeight: 20 },
  tableCard: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.md },
  tableGridWrap: { minWidth: 700, borderWidth: 1, borderColor: colors.border, borderRadius: borderRadius.sm, overflow: 'hidden', backgroundColor: colors.card },
  tableRow: { flexDirection: 'row' },
  tableCell: { flex: 1, minWidth: 170, paddingHorizontal: 10, paddingVertical: 10, borderRightWidth: 1, borderBottomWidth: 1, borderColor: colors.border },
  tableHeaderCell: { backgroundColor: colors.surface },
  tableHeaderText: { fontSize: 13, fontWeight: '700', color: colors.foreground, lineHeight: 18 },
  tableCellText: { ...typography.bodySmall, color: colors.textSecondary, lineHeight: 20 },
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


