/**
 * CourseChapterSwiper — horizontal pager of course chapters.
 *
 * Renders one card per chapter (`CourseChapter` from data/courseContent).
 * The deck snaps page-by-page; a row of dots tracks position. Each card
 * is a minimalist composition:
 *
 *   ┌───────────────────────────────┐
 *   │  ① CHAPTER 01   3 MIN         │   ← chip + eta
 *   │                               │
 *   │           ◯◯◯                 │   ← icon-on-disc (accent)
 *   │           ◯◯◯                 │     optional thin progress arc
 *   │                               │
 *   │  Skin Foundations             │   ← Playfair serif title
 *   │  How your skin actually       │   ← subtitle
 *   │  works and what you can       │
 *   │  change.                      │
 *   │                               │
 *   │  · barrier vs surface vs deep │   ← bullet list
 *   │  · skin type ≠ skin condition │
 *   │  · what lasts vs what's daily │
 *   └───────────────────────────────┘
 *           ●  ○  ○  ○  ○  ○         ← page indicator
 *
 * Aesthetic anchors:
 *   - One accent color per module (passed in)
 *   - Hairline borders, soft shadow, generous whitespace
 *   - Same iconography family throughout (Ionicons -outline)
 *   - Cards inherit app's serif title + sans body conventions
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
    Animated,
    FlatList,
    Platform,
    StyleSheet,
    Text,
    View,
    type LayoutChangeEvent,
    type NativeScrollEvent,
    type NativeSyntheticEvent,
    type ViewToken,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { CourseChapter, CourseModule } from '../data/courseContent';
import { borderRadius, colors, fonts, shadows, spacing, typography } from '../theme/dark';

export type CourseChapterSwiperProps = {
    course: CourseModule;
};

const CARD_GAP = spacing.md;
const SIDE_PADDING = spacing.lg;

export default function CourseChapterSwiper({ course }: CourseChapterSwiperProps) {
    const [containerWidth, setContainerWidth] = useState(0);
    const [activeIndex, setActiveIndex] = useState(0);

    const cardWidth = Math.max(240, containerWidth - SIDE_PADDING * 2);
    const snapInterval = cardWidth + CARD_GAP;

    const onLayout = useCallback((e: LayoutChangeEvent) => {
        setContainerWidth(e.nativeEvent.layout.width);
    }, []);

    const onMomentumScrollEnd = useCallback(
        (e: NativeSyntheticEvent<NativeScrollEvent>) => {
            if (snapInterval <= 0) return;
            const x = e.nativeEvent.contentOffset.x;
            const idx = Math.round(x / snapInterval);
            if (idx !== activeIndex) setActiveIndex(idx);
        },
        [activeIndex, snapInterval]
    );

    const renderItem = useCallback(
        ({ item, index }: { item: CourseChapter; index: number }) => (
            <ChapterCard
                chapter={item}
                accent={course.accent}
                accentSoft={course.accentSoft}
                width={cardWidth}
                isLast={index === course.chapters.length - 1}
                totalCount={course.chapters.length}
            />
        ),
        [cardWidth, course.accent, course.accentSoft, course.chapters.length]
    );

    return (
        <View onLayout={onLayout} style={styles.wrap}>
            {course.caption ? (
                <Text style={[styles.caption, { color: course.accent }]}>{course.caption}</Text>
            ) : null}

            {containerWidth > 0 && (
                <FlatList
                    horizontal
                    pagingEnabled={false}
                    snapToInterval={snapInterval}
                    snapToAlignment="start"
                    decelerationRate="fast"
                    showsHorizontalScrollIndicator={false}
                    data={course.chapters}
                    keyExtractor={(c) => c.id}
                    renderItem={renderItem}
                    ItemSeparatorComponent={() => <View style={{ width: CARD_GAP }} />}
                    contentContainerStyle={{ paddingHorizontal: SIDE_PADDING }}
                    onMomentumScrollEnd={onMomentumScrollEnd}
                    initialNumToRender={3}
                    maxToRenderPerBatch={3}
                    windowSize={5}
                />
            )}

            <View style={styles.dotsRow}>
                {course.chapters.map((c, i) => {
                    const active = i === activeIndex;
                    return (
                        <View
                            key={c.id}
                            style={[
                                styles.dot,
                                active && {
                                    backgroundColor: course.accent,
                                    width: 18,
                                },
                            ]}
                        />
                    );
                })}
            </View>
        </View>
    );
}

/* ── ChapterCard ─────────────────────────────────────────────────────── */

type ChapterCardProps = {
    chapter: CourseChapter;
    accent: string;
    accentSoft: string;
    width: number;
    isLast: boolean;
    totalCount: number;
};

function ChapterCard({ chapter, accent, accentSoft, width, totalCount }: ChapterCardProps) {
    const numberLabel = `CH ${String(chapter.number).padStart(2, '0')}`;
    const ofLabel = `${chapter.number}/${totalCount}`;

    return (
        <View style={[styles.card, { width }]}>
            {/* Top chip row */}
            <View style={styles.cardTopRow}>
                <View style={[styles.chip, { backgroundColor: accentSoft }]}>
                    <Text style={[styles.chipText, { color: accent }]}>{numberLabel}</Text>
                </View>
                {chapter.eta ? (
                    <View style={styles.etaPill}>
                        <Ionicons
                            name="time-outline"
                            size={10}
                            color={colors.textMuted}
                            style={{ marginRight: 4 }}
                        />
                        <Text style={styles.etaText}>{chapter.eta.toUpperCase()}</Text>
                    </View>
                ) : null}
            </View>

            {/* Visual — icon on tinted disc, optional progress arc */}
            <View style={styles.visualWrap}>
                <View style={[styles.discOuter, { borderColor: accentSoft }]}>
                    {typeof chapter.progress === 'number' && (
                        <ProgressArc
                            size={108}
                            stroke={3}
                            value={Math.max(0, Math.min(100, chapter.progress))}
                            color={accent}
                        />
                    )}
                    <View style={[styles.disc, { backgroundColor: accentSoft }]}>
                        <Ionicons
                            name={chapter.icon as any}
                            size={36}
                            color={accent}
                        />
                    </View>
                </View>
            </View>

            {/* Title + subtitle */}
            <Text style={styles.title} numberOfLines={2}>
                {chapter.title}
            </Text>
            <Text style={styles.subtitle} numberOfLines={3}>
                {chapter.subtitle}
            </Text>

            {/* Bullets */}
            <View style={styles.bulletsWrap}>
                {chapter.bullets.slice(0, 4).map((b, i) => (
                    <View key={i} style={styles.bulletRow}>
                        <View style={[styles.bulletDot, { backgroundColor: accent }]} />
                        <Text style={styles.bulletText} numberOfLines={2}>
                            {b}
                        </Text>
                    </View>
                ))}
            </View>

            {/* Footer: 1/N hint */}
            <View style={styles.cardFooter}>
                <Text style={[styles.footerText, { color: colors.textMuted }]}>{ofLabel}</Text>
            </View>
        </View>
    );
}

/* ── ProgressArc — pure SVG-free circular progress (CSS / View tricks) ── */
/**
 * Conic-gradient is the lightest way to draw a partial ring. It works on
 * web (which is the target right now). On native the conic gradient
 * polyfills, so we degrade to a static accent ring (`borderColor`).
 */
function ProgressArc({
    size,
    stroke,
    value,
    color,
}: {
    size: number;
    stroke: number;
    value: number;
    color: string;
}) {
    if (Platform.OS !== 'web') {
        return (
            <View
                style={{
                    position: 'absolute',
                    width: size,
                    height: size,
                    borderRadius: size / 2,
                    borderWidth: stroke,
                    borderColor: color,
                    opacity: 0.65,
                }}
            />
        );
    }
    const deg = (value / 100) * 360;
    const bg = `conic-gradient(${color} ${deg}deg, rgba(0,0,0,0.08) ${deg}deg)`;
    return (
        <View
            // @ts-expect-error — web-only style override
            style={{
                position: 'absolute',
                width: size,
                height: size,
                borderRadius: size / 2,
                background: bg,
                WebkitMask: `radial-gradient(circle, transparent ${(size - stroke * 2) / 2}px, black ${(size - stroke * 2) / 2 + 1}px)`,
                mask: `radial-gradient(circle, transparent ${(size - stroke * 2) / 2}px, black ${(size - stroke * 2) / 2 + 1}px)`,
            }}
        />
    );
}

/* ── Styles ──────────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
    wrap: {
        marginTop: spacing.md,
        marginBottom: spacing.lg,
        marginHorizontal: -spacing.lg, // bleed past the screen padding for full-width feel
    },
    caption: {
        ...typography.label,
        paddingHorizontal: SIDE_PADDING,
        marginBottom: 10,
    },

    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        padding: spacing.lg,
        ...shadows.sm,
    },
    cardTopRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.lg,
    },
    chip: {
        paddingHorizontal: 10,
        paddingVertical: 5,
        borderRadius: borderRadius.full,
    },
    chipText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 10,
        letterSpacing: 1.4,
    },
    etaPill: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
    },
    etaText: {
        fontFamily: fonts.sansMedium,
        fontSize: 9.5,
        letterSpacing: 1.2,
        color: colors.textMuted,
    },

    visualWrap: {
        alignItems: 'center',
        marginBottom: spacing.lg,
    },
    discOuter: {
        width: 108,
        height: 108,
        borderRadius: 54,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
    },
    disc: {
        width: 80,
        height: 80,
        borderRadius: 40,
        alignItems: 'center',
        justifyContent: 'center',
    },

    title: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        letterSpacing: -0.4,
        color: colors.foreground,
        marginBottom: 6,
    },
    subtitle: {
        ...typography.bodySmall,
        color: colors.textSecondary,
        marginBottom: spacing.md,
        lineHeight: 18,
    },

    bulletsWrap: {
        gap: 6,
    },
    bulletRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
    },
    bulletDot: {
        width: 4,
        height: 4,
        borderRadius: 2,
        marginTop: 7,
        marginRight: 10,
    },
    bulletText: {
        flex: 1,
        fontFamily: fonts.sans,
        fontSize: 12.5,
        lineHeight: 18,
        color: colors.textPrimary,
    },

    cardFooter: {
        marginTop: spacing.lg,
        flexDirection: 'row',
        justifyContent: 'flex-end',
    },
    footerText: {
        fontFamily: fonts.sansMedium,
        fontSize: 11,
        letterSpacing: 1,
    },

    /* dots */
    dotsRow: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        gap: 6,
        marginTop: spacing.md,
    },
    dot: {
        width: 6,
        height: 6,
        borderRadius: 3,
        backgroundColor: colors.border,
    },
});
