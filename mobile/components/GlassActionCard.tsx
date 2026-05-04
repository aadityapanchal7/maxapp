/**
 * GlassActionCard — wrapper for the schedule action group on a maxx
 * detail page.
 *
 * Originally a frosted accent surface (gradient + blur + accent border).
 * Restyled to a plain hairline-bordered card so the page top stays
 * minimalist and lets the hero typography lead. Accent is no longer
 * used as a background tint — the buttons inside carry the color.
 *
 * Component name + props kept stable for caller compatibility.
 */

import React, { type PropsWithChildren } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { borderRadius, colors, spacing } from '../theme/dark';

export type GlassActionCardProps = PropsWithChildren<{
    /** Accepted for API stability; no longer affects rendering. */
    accent?: string;
    accentSoft?: string;
    style?: ViewStyle;
}>;

export default function GlassActionCard({ style, children }: GlassActionCardProps) {
    return (
        <View style={[styles.outer, style]}>
            <View style={styles.inner}>{children}</View>
        </View>
    );
}

const styles = StyleSheet.create({
    outer: {
        borderRadius: borderRadius.md,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        backgroundColor: colors.card,
        overflow: 'hidden',
    },
    inner: {
        padding: spacing.md,
        gap: spacing.sm,
    },
});
