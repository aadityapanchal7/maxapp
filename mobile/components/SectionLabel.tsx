/**
 * SectionLabel — refined section header with a tiny accent indicator.
 *
 * Replaces the bare `Text>SECTION</Text>` pattern. A short vertical
 * pill in the maxx accent color sits next to the uppercase label,
 * tying the section to the rest of the page's visual identity.
 *
 *   ▍ COURSE
 *   ▍ MODULES
 */

import React from 'react';
import { StyleSheet, Text, View, type ViewStyle } from 'react-native';
import { colors, fonts, spacing } from '../theme/dark';

export type SectionLabelProps = {
    label: string;
    accent?: string;
    style?: ViewStyle;
};

export default function SectionLabel({ label, accent = colors.foreground, style }: SectionLabelProps) {
    return (
        <View style={[styles.row, style]}>
            <View style={[styles.bar, { backgroundColor: accent }]} />
            <Text style={styles.text}>{label}</Text>
        </View>
    );
}

const styles = StyleSheet.create({
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: spacing.md,
    },
    bar: {
        width: 3,
        height: 14,
        borderRadius: 2,
        marginRight: 10,
    },
    text: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        letterSpacing: 1.4,
        textTransform: 'uppercase',
        color: colors.textMuted,
    },
});
