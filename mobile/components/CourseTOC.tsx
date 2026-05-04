/**
 * CourseTOC — type-driven, editorial table of contents.
 *
 * Visual language matches the rest of the app: hairline dividers, Playfair
 * serif titles, generous whitespace, accent color used very sparingly.
 * No card chrome around each chapter — the only structure is the
 * divider between rows.
 *
 *   01 ─────────────────────────────  ▾
 *      Skin Foundations
 *      Start here. What skin is, what changes.
 *      5 LESSONS
 *
 *      ·  1.1   What Skin Actually Is             3 min
 *      ·  1.2   Type vs Condition                 2 min
 *      ·  1.3   Four Layers You Can Affect        3 min
 *      ·  1.4   Why Most Routines Fail            2 min
 *      ·  1.5   Realistic Timelines               2 min
 *
 *   02 ─────────────────────────────  ›
 *      Reading Your Skin
 *      Diagnosis comes before any product.
 *      5 LESSONS
 *
 * Tap header → opens reader at chapter's first section.
 * Tap chevron → toggle section list inline.
 * Tap section → opens reader at that section.
 */

import React, { useCallback, useState } from 'react';
import {
    LayoutAnimation,
    Platform,
    StyleSheet,
    Text,
    TouchableOpacity,
    UIManager,
    View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { CourseChapter, CourseModule } from '../data/courseContent';
import { colors, fonts, spacing, typography } from '../theme/dark';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
    UIManager.setLayoutAnimationEnabledExperimental(true);
}

export type CourseTOCProps = {
    course: CourseModule;
    /** Open the reader at a specific section. */
    onOpenSection: (sectionId: string) => void;
};

export default function CourseTOC({ course, onOpenSection }: CourseTOCProps) {
    const [expanded, setExpanded] = useState<Set<string>>(
        new Set([course.chapters[0]?.id])
    );

    const toggle = useCallback((id: string) => {
        LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
        setExpanded((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }, []);

    return (
        <View style={styles.wrap}>
            {course.chapters.map((ch, i) => (
                <ChapterRow
                    key={ch.id}
                    chapter={ch}
                    accent={course.accent}
                    isFirst={i === 0}
                    expanded={expanded.has(ch.id)}
                    onToggle={() => toggle(ch.id)}
                    onOpenSection={onOpenSection}
                />
            ))}
        </View>
    );
}

/* ── Chapter row ──────────────────────────────────────────────────────── */

type ChapterRowProps = {
    chapter: CourseChapter;
    accent: string;
    isFirst: boolean;
    expanded: boolean;
    onToggle: () => void;
    onOpenSection: (sectionId: string) => void;
};

function ChapterRow({
    chapter,
    accent,
    isFirst,
    expanded,
    onToggle,
    onOpenSection,
}: ChapterRowProps) {
    const numberLabel = chapter.number.toString().padStart(2, '0');
    const lessonsLabel = `${chapter.sections.length} LESSON${chapter.sections.length === 1 ? '' : 'S'}`;

    return (
        <View style={[styles.chapterWrap, !isFirst && styles.chapterDivider]}>
            <View style={styles.headerRow}>
                <TouchableOpacity
                    style={styles.headerCopyTap}
                    activeOpacity={0.55}
                    onPress={() => onOpenSection(chapter.sections[0].id)}
                >
                    <Text style={[styles.numberLabel, { color: accent }]}>{numberLabel}</Text>
                    <View style={styles.copyBlock}>
                        <Text style={styles.chapterTitle} numberOfLines={2}>
                            {chapter.title}
                        </Text>
                        <Text style={styles.chapterSubtitle} numberOfLines={2}>
                            {chapter.subtitle}
                        </Text>
                        <Text style={styles.lessonsLabel}>{lessonsLabel}</Text>
                    </View>
                </TouchableOpacity>

                <TouchableOpacity
                    onPress={onToggle}
                    style={styles.chevronBtn}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    accessibilityLabel={expanded ? 'Collapse chapter' : 'Expand chapter'}
                >
                    <Ionicons
                        name={expanded ? 'chevron-up' : 'chevron-down'}
                        size={16}
                        color={expanded ? accent : colors.textMuted}
                    />
                </TouchableOpacity>
            </View>

            {expanded && (
                <View style={styles.sectionList}>
                    {chapter.sections.map((s) => (
                        <TouchableOpacity
                            key={s.id}
                            style={styles.sectionRow}
                            activeOpacity={0.55}
                            onPress={() => onOpenSection(s.id)}
                        >
                            <View style={[styles.sectionMark, { backgroundColor: accent }]} />
                            <Text style={styles.sectionNumber}>{s.number}</Text>
                            <Text style={styles.sectionTitle} numberOfLines={1}>
                                {s.title}
                            </Text>
                            {s.eta ? <Text style={styles.sectionEta}>{s.eta}</Text> : null}
                        </TouchableOpacity>
                    ))}
                </View>
            )}
        </View>
    );
}

/* ── Styles ───────────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
    wrap: {
        marginTop: 4,
    },
    caption: {
        ...typography.label,
        marginBottom: spacing.lg,
    },

    chapterWrap: {
        paddingVertical: spacing.lg,
    },
    chapterDivider: {
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.border,
    },

    headerRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
    },
    headerCopyTap: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'flex-start',
    },
    numberLabel: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 1.6,
        marginRight: 18,
        marginTop: 4,
        width: 26,
    },
    copyBlock: {
        flex: 1,
        paddingRight: spacing.sm,
    },
    chapterTitle: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        letterSpacing: -0.4,
        lineHeight: 28,
        color: colors.foreground,
    },
    chapterSubtitle: {
        ...typography.bodySmall,
        color: colors.textSecondary,
        marginTop: 6,
        lineHeight: 19,
    },
    lessonsLabel: {
        ...typography.caption,
        marginTop: 10,
        letterSpacing: 1.4,
        color: colors.textMuted,
    },

    chevronBtn: {
        width: 32,
        height: 32,
        alignItems: 'center',
        justifyContent: 'center',
        marginTop: 2,
    },

    sectionList: {
        marginTop: spacing.lg,
        marginLeft: 44,
    },
    sectionRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 9,
    },
    sectionMark: {
        width: 4,
        height: 4,
        borderRadius: 2,
        marginRight: 14,
    },
    sectionNumber: {
        fontFamily: fonts.sansMedium,
        fontSize: 11,
        color: colors.textMuted,
        letterSpacing: 0.6,
        width: 32,
    },
    sectionTitle: {
        flex: 1,
        fontFamily: fonts.sans,
        fontSize: 14,
        color: colors.textPrimary,
        letterSpacing: -0.05,
    },
    sectionEta: {
        fontFamily: fonts.sans,
        fontSize: 11,
        color: colors.textMuted,
        marginLeft: 8,
        letterSpacing: 0.2,
    },
});
