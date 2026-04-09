import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fonts } from '../../theme/dark';
import { useAuth } from '../../context/AuthContext';

const BENEFITS = [
    { icon: 'scan-outline' as const, label: 'AI-powered analysis' },
    { icon: 'timer-outline' as const, label: 'Takes 30 seconds' },
    { icon: 'shield-checkmark-outline' as const, label: 'Private & secure' },
];

export default function FeaturesIntroScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { user, isPaid } = useAuth();

    const hasScan = user?.first_scan_completed;

    return (
        <View style={s.container}>
            <View style={[s.topBar, { paddingTop: Math.max(insets.top, 12) }]}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={s.backBtn}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    accessibilityLabel="Back"
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>
            </View>

            <View style={s.body}>
                <View style={s.iconCircle}>
                    <Ionicons name="scan" size={44} color={colors.foreground} />
                </View>

                <Text style={s.headline}>See your{'\n'}true score</Text>

                <Text style={s.subline}>
                    Three angles. Instant AI analysis.{'\n'}
                    Discover where you stand — and how to level up.
                </Text>

                <View style={s.benefitsRow}>
                    {BENEFITS.map((b, i) => (
                        <View key={i} style={s.benefitCell}>
                            <Ionicons name={b.icon} size={20} color={colors.foreground} />
                            <Text style={s.benefitLabel}>{b.label}</Text>
                        </View>
                    ))}
                </View>
            </View>

            <View style={[s.footer, { paddingBottom: Math.max(insets.bottom, spacing.xl) }]}>
                {hasScan && !isPaid ? (
                    <TouchableOpacity
                        style={s.ctaPrimary}
                        onPress={() => navigation.navigate('FaceScanResults')}
                        activeOpacity={0.8}
                        accessibilityRole="button"
                        accessibilityLabel="View my results"
                    >
                        <Text style={s.ctaPrimaryText}>View my results</Text>
                        <Ionicons name="arrow-forward" size={18} color={colors.background} />
                    </TouchableOpacity>
                ) : (
                    <TouchableOpacity
                        style={s.ctaPrimary}
                        onPress={() => navigation.navigate('FaceScan')}
                        activeOpacity={0.8}
                        accessibilityRole="button"
                        accessibilityLabel="Start face scan"
                    >
                        <Text style={s.ctaPrimaryText}>Start scan</Text>
                        <Ionicons name="arrow-forward" size={18} color={colors.background} />
                    </TouchableOpacity>
                )}
            </View>
        </View>
    );
}

const s = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.background,
    },
    topBar: {
        paddingHorizontal: spacing.lg,
    },
    backBtn: {
        width: 40,
        height: 40,
        justifyContent: 'center',
    },

    body: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: spacing.xl,
    },
    iconCircle: {
        width: 96,
        height: 96,
        borderRadius: 48,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: spacing.xl + spacing.md,
    },
    headline: {
        fontFamily: fonts.serif,
        fontSize: 36,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.8,
        textAlign: 'center',
        lineHeight: 42,
    },
    subline: {
        fontSize: 15,
        color: colors.textSecondary,
        textAlign: 'center',
        lineHeight: 22,
        marginTop: spacing.md,
        maxWidth: 300,
    },

    benefitsRow: {
        flexDirection: 'row',
        justifyContent: 'center',
        gap: spacing.xl,
        marginTop: spacing.xl + spacing.lg,
    },
    benefitCell: {
        alignItems: 'center',
        gap: 6,
        maxWidth: 90,
    },
    benefitLabel: {
        fontSize: 11,
        fontWeight: '500',
        color: colors.textMuted,
        textAlign: 'center',
        letterSpacing: 0.2,
    },

    footer: {
        paddingHorizontal: spacing.xl,
        paddingTop: spacing.lg,
    },
    ctaPrimary: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: 16,
    },
    ctaPrimaryText: {
        fontSize: 16,
        fontWeight: '600',
        color: colors.background,
        letterSpacing: 0.1,
    },
});
