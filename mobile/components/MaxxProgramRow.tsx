import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, type ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, typography } from '../theme/dark';

export function normalizeMaxxTintHex(color: string | undefined): string {
    return color && /^#[0-9A-Fa-f]{6}$/.test(color) ? color : colors.textMuted;
}

export type MaxxProgramRowAccent = 'rail' | 'stripe' | 'none';

export type MaxxProgramRowProps = {
    tintHex: string;
    iconName: string;
    title: string;
    description?: string | null;
    onPress: () => void;
    trailing: React.ReactNode;
    accent?: MaxxProgramRowAccent;
    flat?: boolean;
    selected?: boolean;
    selectedVariant?: 'brand' | 'uniform';
    brandColor?: string;
    activeOpacity?: number;
    accessibilityRole?: 'button' | 'checkbox';
    accessibilityState?: { checked?: boolean; selected?: boolean; disabled?: boolean };
    style?: ViewStyle;
};

export function MaxxProgramRow({
    tintHex,
    iconName,
    title,
    description,
    onPress,
    trailing,
    accent = 'none',
    flat = false,
    selected = false,
    selectedVariant = 'brand',
    brandColor,
    activeOpacity = 0.75,
    accessibilityRole = 'button',
    accessibilityState,
    style,
}: MaxxProgramRowProps) {
    const tint = normalizeMaxxTintHex(tintHex);
    const brand = brandColor ?? tint;

    const outerBorder: ViewStyle = selected
        ? selectedVariant === 'uniform'
            ? {
                  borderWidth: 1,
                  borderColor: colors.foreground,
                  backgroundColor: colors.card,
              }
            : {
                  borderWidth: 1,
                  borderColor: brand,
                  backgroundColor: colors.card,
              }
        : {
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.card,
          };

    return (
        <TouchableOpacity
            style={[styles.outer, outerBorder, flat && styles.flat, style]}
            onPress={onPress}
            activeOpacity={activeOpacity}
            accessibilityRole={accessibilityRole}
            accessibilityState={accessibilityState}
        >
            <View style={styles.innerRow}>
                {accent === 'stripe' ? <View style={[styles.stripe, { backgroundColor: tint }]} pointerEvents="none" /> : null}
                <View style={[styles.contentShell, accent === 'rail' && styles.contentShellRail]}>
                    {accent === 'rail' ? (
                        <View style={[styles.rail, { backgroundColor: tint }]} pointerEvents="none" />
                    ) : null}
                    <View style={styles.row}>
                        <View style={[styles.iconTile, { backgroundColor: `${tint}0c`, borderColor: `${tint}18` }]}>
                            <Ionicons name={iconName as any} size={20} color={tint} />
                        </View>
                        <View style={styles.copy}>
                            <Text style={styles.title} numberOfLines={1}>
                                {title}
                            </Text>
                            {description ? (
                                <Text style={styles.desc} numberOfLines={2}>
                                    {description}
                                </Text>
                            ) : null}
                        </View>
                        {trailing}
                    </View>
                </View>
            </View>
        </TouchableOpacity>
    );
}

const styles = StyleSheet.create({
    outer: {
        borderRadius: borderRadius.xl,
        marginBottom: spacing.sm,
        overflow: 'hidden',
    },
    flat: {
        shadowColor: 'transparent',
        shadowOpacity: 0,
        shadowRadius: 0,
        shadowOffset: { width: 0, height: 0 },
        elevation: 0,
    },
    innerRow: {
        flexDirection: 'row',
        alignItems: 'stretch',
        minHeight: 68,
    },
    stripe: {
        width: 3,
        flexShrink: 0,
    },
    contentShell: {
        flex: 1,
        position: 'relative',
        paddingVertical: spacing.md,
        paddingRight: spacing.lg,
        paddingLeft: spacing.lg,
        justifyContent: 'center',
    },
    contentShellRail: {
        paddingLeft: spacing.lg + 6,
    },
    rail: {
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: 3,
        borderTopLeftRadius: borderRadius.xl,
        borderBottomLeftRadius: borderRadius.xl,
    },
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        zIndex: 1,
    },
    iconTile: {
        width: 42,
        height: 42,
        borderRadius: borderRadius.md,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
    },
    copy: { flex: 1, minWidth: 0 },
    title: {
        fontSize: 15,
        fontWeight: '500',
        color: colors.foreground,
        letterSpacing: -0.15,
    },
    desc: {
        ...typography.bodySmall,
        fontSize: 13,
        color: colors.textSecondary,
        marginTop: 3,
        lineHeight: 18,
    },
});
