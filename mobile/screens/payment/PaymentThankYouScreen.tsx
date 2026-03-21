import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const UNLOCKED = [
    'All courses & Maxx programs',
    'AI schedules + SMS reminders',
    'Scans, progress, and community',
    'Max coach in-app & SMS',
];

export default function PaymentThankYouScreen() {
    const { refreshUser, user } = useAuth();
    const [loading, setLoading] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    const handleContinue = async () => {
        try {
            setLoading(true);
            await refreshUser();
        } finally {
            setLoading(false);
        }
    };

    const handleRefreshStatus = async () => {
        try {
            setRefreshing(true);
            await refreshUser();
        } finally {
            setRefreshing(false);
        }
    };

    const paid = user?.is_paid === true;

    return (
        <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            keyboardShouldPersistTaps="handled"
        >
            <View style={styles.card}>
                <View style={styles.iconWrap}>
                    <Ionicons name="checkmark-circle" size={72} color={colors.primary} />
                </View>
                <Text style={styles.title}>{paid ? 'You’re in' : 'Thanks — almost there'}</Text>
                <Text style={styles.subtitle}>
                    {paid
                        ? 'Your subscription is active. Everything in Max is unlocked for you.'
                        : 'If you just paid, Stripe may need a moment to tell us. Tap refresh below, or wait a few seconds and try again.'}
                </Text>

                <View style={styles.list}>
                    <Text style={styles.listTitle}>Included with your membership</Text>
                    {UNLOCKED.map((line, i) => (
                        <View key={i} style={styles.listRow}>
                            <Ionicons name="checkmark-circle" size={18} color={colors.accent} />
                            <Text style={styles.listText}>{line}</Text>
                        </View>
                    ))}
                </View>

                <TouchableOpacity
                    style={[styles.button, loading && styles.buttonDisabled]}
                    onPress={handleContinue}
                    disabled={loading}
                    activeOpacity={0.85}
                >
                    {loading ? (
                        <ActivityIndicator color={colors.background} />
                    ) : (
                        <>
                            <Text style={styles.buttonText}>Enter Max</Text>
                            <Ionicons name="arrow-forward" size={20} color={colors.background} />
                        </>
                    )}
                </TouchableOpacity>

                <TouchableOpacity
                    style={styles.secondary}
                    onPress={handleRefreshStatus}
                    disabled={refreshing}
                    activeOpacity={0.7}
                >
                    {refreshing ? (
                        <ActivityIndicator color={colors.accent} size="small" />
                    ) : (
                        <Text style={styles.secondaryText}>Payment still pending? Tap to refresh account</Text>
                    )}
                </TouchableOpacity>
            </View>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    scroll: { flex: 1, backgroundColor: colors.background },
    scrollContent: {
        flexGrow: 1,
        justifyContent: 'center',
        padding: spacing.lg,
        paddingVertical: spacing.xl * 2,
    },
    card: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        alignItems: 'center',
        maxWidth: 400,
        alignSelf: 'center',
        width: '100%',
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.md,
    },
    iconWrap: { marginBottom: spacing.md },
    title: {
        fontSize: 26,
        fontWeight: '700',
        color: colors.foreground,
        marginBottom: spacing.sm,
        textAlign: 'center',
        letterSpacing: -0.5,
    },
    subtitle: {
        fontSize: 15,
        lineHeight: 22,
        color: colors.textMuted,
        textAlign: 'center',
        marginBottom: spacing.xl,
    },
    list: {
        alignSelf: 'stretch',
        marginBottom: spacing.xl,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        gap: spacing.sm,
    },
    listTitle: {
        fontSize: 13,
        fontWeight: '700',
        color: colors.textSecondary,
        textTransform: 'uppercase',
        letterSpacing: 0.8,
        marginBottom: spacing.xs,
    },
    listRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    listText: { flex: 1, fontSize: 14, color: colors.foreground, lineHeight: 20 },
    button: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: spacing.md + 2,
        paddingHorizontal: spacing.xl,
        borderRadius: borderRadius.full,
        minWidth: 220,
        ...shadows.sm,
    },
    buttonDisabled: { opacity: 0.7 },
    buttonText: {
        ...typography.button,
        fontSize: 16,
        color: colors.background,
    },
    secondary: {
        marginTop: spacing.lg,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
    },
    secondaryText: {
        fontSize: 14,
        fontWeight: '600',
        color: colors.accent,
        textAlign: 'center',
    },
});
