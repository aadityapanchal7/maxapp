/**
 * ModuleHero — editorial top of a maxx detail page.
 *
 * Composition reasoning (top-down):
 *   1. back arrow              — navigation, light footprint
 *   2. serif title             — module identity, single statement
 *   3. accent rule             — the only signature decoration
 *   4. subtitle                — one-sentence framing, muted grey
 *   5. stats display           — serif numbers (echo title) + tracked labels
 *
 * No eyebrow that repeats the title; no icon when type can do the work.
 * The serif numbers in the stats row visually rhyme with the title above
 * so the whole top reads as one composed feature opener.
 */

import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View, type ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';

import { colors, fonts, spacing } from '../theme/dark';

/** Convert `#rrggbb` → `rgba(r,g,b,a)` for use in LinearGradient stops. */
function hexToRgba(hex: string, alpha: number): string {
    const h = hex.replace('#', '');
    const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const r = parseInt(full.slice(0, 2), 16);
    const g = parseInt(full.slice(2, 4), 16);
    const b = parseInt(full.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export type HeroStat = {
    /** Big serif number — string OR number; rendered as-is. */
    number: string | number;
    /** Small tracked uppercase caption beneath. */
    label: string;
};

export type ModuleHeroProps = {
    title: string;
    accent: string;
    /** Accepted for API stability — not rendered. */
    accentSoft?: string;
    /** Accepted for API stability — not rendered. */
    iconName?: string;
    onBack: () => void;
    description?: string;
    /** Two or three at most; more crowds the column. */
    stats?: HeroStat[];
    /** Deprecated string form, kept for callers still using it.
     *  Each item is rendered as a single tracked uppercase line. */
    metaItems?: string[];
    style?: ViewStyle;
};

export default function ModuleHero({
    title,
    accent,
    onBack,
    description,
    stats,
    metaItems,
    style,
}: ModuleHeroProps) {
    const insets = useSafeAreaInsets();

    // Backwards-compat: callers still passing string metaItems get a
    // single-line tracked row at the bottom (no big numbers).
    const fallbackMeta = !stats?.length && metaItems?.length ? metaItems : null;

    return (
        <View style={[styles.wrap, style]}>
            {/* Soft accent veil — vertical fade from ~10% accent at the very
                top to transparent over ~280 px. Frames the title without
                competing with it. The page bg shows through everywhere
                else, so the rest of the screen stays neutral. */}
            <LinearGradient
                pointerEvents="none"
                colors={[
                    hexToRgba(accent, 0.12),
                    hexToRgba(accent, 0.05),
                    hexToRgba(accent, 0.0),
                ]}
                locations={[0, 0.55, 1]}
                style={styles.gradient}
            />
            <View style={[styles.content, { paddingTop: Math.max(insets.top, 12) + 6 }]}>
                <TouchableOpacity
                    onPress={onBack}
                    style={styles.backBtn}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    accessibilityLabel="Back"
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>

                <Text style={styles.title}>{title}</Text>
                <View style={[styles.accentRule, { backgroundColor: accent }]} />

                {description ? (
                    <Text style={styles.caption} numberOfLines={3}>
                        {description}
                    </Text>
                ) : null}

                {stats && stats.length > 0 ? (
                    <View style={styles.statsRow}>
                        {stats.slice(0, 3).map((s, i) => (
                            <View
                                key={`${s.label}-${i}`}
                                style={[styles.statBlock, i > 0 && styles.statBlockSpacer]}
                            >
                                <Text style={styles.statNumber}>{s.number}</Text>
                                <Text style={styles.statLabel}>{s.label.toUpperCase()}</Text>
                            </View>
                        ))}
                    </View>
                ) : null}

                {fallbackMeta ? (
                    <View style={styles.metaRow}>
                        {fallbackMeta.map((item, i) => (
                            <React.Fragment key={`${item}-${i}`}>
                                {i > 0 && (
                                    <View style={[styles.metaDot, { backgroundColor: accent }]} />
                                )}
                                <Text style={styles.metaText}>{item.toUpperCase()}</Text>
                            </React.Fragment>
                        ))}
                    </View>
                ) : null}
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    wrap: {
        backgroundColor: colors.background,
        position: 'relative',
        overflow: 'hidden',
    },
    gradient: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: 280,
    },
    content: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.lg,
    },
    backBtn: {
        width: 32,
        height: 32,
        alignItems: 'flex-start',
        justifyContent: 'center',
        marginLeft: -4,
        marginBottom: spacing.lg,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 40,
        fontWeight: '400',
        letterSpacing: -1,
        lineHeight: 46,
        color: colors.foreground,
    },
    accentRule: {
        width: 28,
        height: 2,
        borderRadius: 1,
        marginTop: 12,
        marginBottom: spacing.lg,
    },
    caption: {
        fontFamily: fonts.sans,
        fontSize: 15,
        lineHeight: 22,
        color: colors.textSecondary,
        maxWidth: 360,
    },

    /* Editorial stats — serif numbers rhyme with title */
    statsRow: {
        flexDirection: 'row',
        marginTop: spacing.lg,
    },
    statBlock: {
        alignItems: 'flex-start',
    },
    statBlockSpacer: {
        marginLeft: 36,
    },
    statNumber: {
        fontFamily: fonts.serif,
        fontSize: 26,
        fontWeight: '400',
        letterSpacing: -0.4,
        color: colors.foreground,
        lineHeight: 30,
    },
    statLabel: {
        fontFamily: fonts.sansMedium,
        fontSize: 10.5,
        letterSpacing: 1.6,
        color: colors.textMuted,
        marginTop: 5,
    },

    /* Fallback string meta (used by non-course maxxes still on metaItems) */
    metaRow: {
        flexDirection: 'row',
        alignItems: 'center',
        flexWrap: 'wrap',
        marginTop: spacing.md,
    },
    metaText: {
        fontFamily: fonts.sansMedium,
        fontSize: 10.5,
        letterSpacing: 1.5,
        color: colors.textMuted,
    },
    metaDot: {
        width: 3,
        height: 3,
        borderRadius: 2,
        marginHorizontal: 10,
    },
});
