/**
 * CourseReader — full-screen reader. Editorial / magazine layout.
 *
 * Drops the icon-on-disc visual in favor of typography. The accent color
 * appears only as a hairline rule, a tiny bullet mark, and the next-arrow
 * tint. Everything else is type and whitespace.
 *
 *   ┌──────────────────────────────────────┐
 *   │  CH 07 · § 7.3                    ✕  │
 *   │  Actives — The Power Tools           │   small chapter title
 *   │  ─────                                │   thin accent rule
 *   │                                       │
 *   │  Retinoids                            │   massive serif
 *   │  The single best-studied anti-aging   │   subtitle
 *   │  + acne ingredient.                   │
 *   │                                       │
 *   │   ·  OTC: adapalene 0.1% — best entry │
 *   │   ·  Stronger: tretinoin 0.025–0.1%   │
 *   │   ·  Start 2× / week, ramp slowly     │
 *   │                                       │
 *   │  Retinoids accelerate cell turnover…  │   body in italic serif
 *   │                                       │
 *   ├──────────────────────────────────────┤
 *   │  ‹       12 / 64           accent →  │
 *   │  ▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱                  │
 *   └──────────────────────────────────────┘
 *
 * Pager flows seamlessly across chapter boundaries; chapter title in the
 * top bar updates as the user crosses one.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    FlatList,
    Modal,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
    type LayoutChangeEvent,
    type NativeScrollEvent,
    type NativeSyntheticEvent,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';

import {
    flattenSections,
    type CourseChapter,
    type CourseModule,
    type CourseSection,
} from '../data/courseContent';
import { colors, fonts, spacing, typography } from '../theme/dark';

/** Convert `#rrggbb` → `rgba(r,g,b,a)` for use in LinearGradient stops. */
function hexToRgba(hex: string, alpha: number): string {
    const h = hex.replace('#', '');
    const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const r = parseInt(full.slice(0, 2), 16);
    const g = parseInt(full.slice(2, 4), 16);
    const b = parseInt(full.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export type CourseReaderProps = {
    visible: boolean;
    course: CourseModule | null;
    initialSectionId: string | null;
    onClose: () => void;
};

export default function CourseReader({
    visible,
    course,
    initialSectionId,
    onClose,
}: CourseReaderProps) {
    const insets = useSafeAreaInsets();
    const flatRef = useRef<FlatList<any>>(null);
    const [containerWidth, setContainerWidth] = useState(0);
    const [activeIndex, setActiveIndex] = useState(0);

    const slides = useMemo(
        () => (course ? flattenSections(course) : []),
        [course]
    );

    useEffect(() => {
        if (!visible || !course || !slides.length) return;
        const start = initialSectionId
            ? Math.max(0, slides.findIndex((s) => s.section.id === initialSectionId))
            : 0;
        setActiveIndex(start);
        const t = setTimeout(() => {
            try {
                flatRef.current?.scrollToIndex({ index: start, animated: false });
            } catch {
                /* not laid out yet */
            }
        }, 50);
        return () => clearTimeout(t);
    }, [visible, course, initialSectionId, slides.length]);

    const onLayout = useCallback((e: LayoutChangeEvent) => {
        setContainerWidth(e.nativeEvent.layout.width);
    }, []);

    const onMomentumScrollEnd = useCallback(
        (e: NativeSyntheticEvent<NativeScrollEvent>) => {
            if (!containerWidth) return;
            const idx = Math.round(e.nativeEvent.contentOffset.x / containerWidth);
            if (idx !== activeIndex) setActiveIndex(idx);
        },
        [activeIndex, containerWidth]
    );

    const goPrev = useCallback(() => {
        if (activeIndex <= 0) return;
        flatRef.current?.scrollToIndex({ index: activeIndex - 1, animated: true });
        setActiveIndex(activeIndex - 1);
    }, [activeIndex]);

    const goNext = useCallback(() => {
        if (activeIndex >= slides.length - 1) return;
        flatRef.current?.scrollToIndex({ index: activeIndex + 1, animated: true });
        setActiveIndex(activeIndex + 1);
    }, [activeIndex, slides.length]);

    const renderItem = useCallback(
        ({ item }: { item: { chapter: CourseChapter; section: CourseSection } }) => (
            <Slide
                chapter={item.chapter}
                section={item.section}
                course={course!}
                width={containerWidth}
            />
        ),
        [course, containerWidth]
    );

    if (!course) return null;

    const current = slides[activeIndex];
    const progress = slides.length ? (activeIndex + 1) / slides.length : 0;
    const atStart = activeIndex <= 0;
    const atEnd = activeIndex >= slides.length - 1;

    return (
        <Modal
            visible={visible}
            transparent={false}
            animationType="slide"
            onRequestClose={onClose}
            statusBarTranslucent
        >
            <View style={[styles.root, { paddingTop: insets.top }]} onLayout={onLayout}>
                {/* ── Top bar ─────────────────────────────────────────── */}
                <View style={styles.topBar}>
                    <Text style={styles.topMeta}>
                        {`CH ${current?.chapter.number.toString().padStart(2, '0')}  ·  § ${current?.section.number}`}
                    </Text>
                    <TouchableOpacity
                        onPress={onClose}
                        style={styles.closeBtn}
                        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                        accessibilityLabel="Close reader"
                    >
                        <Ionicons name="close" size={20} color={colors.textSecondary} />
                    </TouchableOpacity>
                </View>

                <View style={styles.chapterRow}>
                    <Text style={styles.chapterTitleSmall} numberOfLines={1}>
                        {current?.chapter.title}
                    </Text>
                    <View style={[styles.accentRule, { backgroundColor: course.accent }]} />
                </View>

                {/* ── Pager ───────────────────────────────────────────── */}
                {containerWidth > 0 && (
                    <FlatList
                        ref={flatRef}
                        horizontal
                        pagingEnabled
                        showsHorizontalScrollIndicator={false}
                        data={slides}
                        keyExtractor={(s) => s.section.id}
                        renderItem={renderItem}
                        initialScrollIndex={activeIndex}
                        getItemLayout={(_, i) => ({
                            length: containerWidth,
                            offset: containerWidth * i,
                            index: i,
                        })}
                        onMomentumScrollEnd={onMomentumScrollEnd}
                        windowSize={3}
                        initialNumToRender={1}
                        maxToRenderPerBatch={2}
                    />
                )}

                {/* ── Bottom controls ─────────────────────────────────── */}
                <View
                    style={[
                        styles.bottomBar,
                        { paddingBottom: Math.max(insets.bottom + 6, spacing.md) },
                    ]}
                >
                    <View style={styles.controlsRow}>
                        <TouchableOpacity
                            onPress={goPrev}
                            disabled={atStart}
                            style={styles.arrowBtn}
                            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                            accessibilityLabel="Previous section"
                        >
                            <Ionicons
                                name="arrow-back"
                                size={18}
                                color={atStart ? colors.textMuted : colors.foreground}
                            />
                        </TouchableOpacity>

                        <Text style={styles.progressText}>
                            <Text style={styles.progressBold}>{activeIndex + 1}</Text>
                            <Text style={styles.progressSlash}> / </Text>
                            {slides.length}
                        </Text>

                        <TouchableOpacity
                            onPress={goNext}
                            disabled={atEnd}
                            style={styles.arrowBtn}
                            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                            accessibilityLabel="Next section"
                        >
                            <Ionicons
                                name="arrow-forward"
                                size={18}
                                color={atEnd ? colors.textMuted : course.accent}
                            />
                        </TouchableOpacity>
                    </View>

                    <View style={styles.progressTrack}>
                        <View
                            style={[
                                styles.progressFill,
                                {
                                    width: `${progress * 100}%`,
                                    backgroundColor: course.accent,
                                },
                            ]}
                        />
                    </View>
                </View>
            </View>
        </Modal>
    );
}

/* ── Slide ────────────────────────────────────────────────────────────── */

type SlideProps = {
    chapter: CourseChapter;
    section: CourseSection;
    course: CourseModule;
    width: number;
};

function Slide({ section, course, width }: SlideProps) {
    const { accent, accentSoft, accentMid } = course;

    return (
        <View style={[slide.outer, { width }]}>
            <ScrollView
                contentContainerStyle={slide.scroll}
                showsVerticalScrollIndicator={false}
            >
                {/* ── Hero visual block ───────────────────────────────
                    Soft accent gradient backdrop, two concentric accent
                    rings (decorative depth), filled accent-tinted disc
                    at center, icon at 40pt in accent color. The whole
                    block is purely decorative — no interactivity. */}
                <View style={slide.visualBlock}>
                    <LinearGradient
                        pointerEvents="none"
                        colors={[
                            hexToRgba(accent, 0.10),
                            hexToRgba(accent, 0.04),
                            hexToRgba(accent, 0.0),
                        ]}
                        locations={[0, 0.6, 1]}
                        style={StyleSheet.absoluteFill}
                    />
                    <View style={[slide.ringOuter, { borderColor: accentSoft }]}>
                        <View style={[slide.ringInner, { borderColor: accentMid }]}>
                            <View style={[slide.disc, { backgroundColor: accentSoft }]}>
                                <Ionicons
                                    name={section.icon as any}
                                    size={40}
                                    color={accent}
                                />
                            </View>
                        </View>
                    </View>
                </View>

                <Text style={[slide.eyebrow, { color: accent }]}>
                    {section.number.toUpperCase()}
                    {section.eta ? `   ·   ${section.eta.toUpperCase()}` : ''}
                </Text>

                <Text style={slide.title}>{section.title}</Text>
                <Text style={slide.subtitle}>{section.subtitle}</Text>

                <View style={slide.bullets}>
                    {section.bullets.map((b, i) => (
                        <View key={i} style={slide.bulletRow}>
                            <View style={[slide.bulletMark, { backgroundColor: accent }]} />
                            <Text style={slide.bulletText}>{b}</Text>
                        </View>
                    ))}
                </View>

                {section.body ? (
                    <Text style={slide.body}>{section.body}</Text>
                ) : null}
            </ScrollView>
        </View>
    );
}

/* ── Styles ───────────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
    root: {
        flex: 1,
        backgroundColor: colors.background,
    },
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
        paddingBottom: 6,
    },
    topMeta: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        letterSpacing: 1.6,
        color: colors.textSecondary,
    },
    closeBtn: {
        width: 30,
        height: 30,
        alignItems: 'center',
        justifyContent: 'center',
    },
    chapterRow: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.lg,
    },
    chapterTitleSmall: {
        fontFamily: fonts.serif,
        fontSize: 16,
        fontWeight: '400',
        letterSpacing: -0.2,
        color: colors.foreground,
        marginBottom: 10,
    },
    accentRule: {
        width: 28,
        height: 2,
        borderRadius: 1,
    },

    bottomBar: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
    },
    controlsRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 10,
    },
    arrowBtn: {
        width: 36,
        height: 36,
        alignItems: 'center',
        justifyContent: 'center',
    },
    progressText: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        letterSpacing: 1.4,
        color: colors.textSecondary,
    },
    progressBold: {
        color: colors.foreground,
        fontFamily: fonts.sansSemiBold,
    },
    progressSlash: {
        color: colors.textMuted,
    },
    progressTrack: {
        height: StyleSheet.hairlineWidth,
        backgroundColor: colors.border,
        overflow: 'hidden',
    },
    progressFill: {
        height: 1,
    },
});

const slide = StyleSheet.create({
    outer: {
        flex: 1,
        paddingHorizontal: spacing.lg,
    },
    scroll: {
        paddingTop: spacing.xs,
        paddingBottom: spacing.lg,
    },
    /* Hero visual: gradient backdrop + concentric accent rings + icon disc */
    visualBlock: {
        height: 168,
        marginHorizontal: -spacing.lg, // bleed past slide padding for full-width feel
        marginTop: -spacing.xs,
        marginBottom: spacing.lg,
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
    },
    ringOuter: {
        width: 132,
        height: 132,
        borderRadius: 66,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
    },
    ringInner: {
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
    eyebrow: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        letterSpacing: 1.8,
        marginBottom: spacing.md,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 34,
        fontWeight: '400',
        letterSpacing: -0.8,
        color: colors.foreground,
        lineHeight: 40,
        marginBottom: 10,
    },
    subtitle: {
        fontFamily: fonts.sans,
        fontSize: 16,
        lineHeight: 24,
        color: colors.textSecondary,
        marginBottom: spacing.lg,
    },
    bullets: {
        marginTop: spacing.xs,
    },
    bulletRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        paddingVertical: 8,
    },
    bulletMark: {
        width: 4,
        height: 4,
        borderRadius: 2,
        marginTop: 9,
        marginRight: 14,
    },
    bulletText: {
        flex: 1,
        fontFamily: fonts.sans,
        fontSize: 15,
        lineHeight: 22,
        color: colors.textPrimary,
        letterSpacing: -0.05,
    },
    body: {
        marginTop: spacing.lg,
        fontFamily: fonts.serifItalic,
        fontSize: 14.5,
        lineHeight: 22,
        color: colors.textSecondary,
    },
});
