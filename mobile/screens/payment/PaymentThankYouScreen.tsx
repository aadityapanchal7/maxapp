import React, { useState, useEffect, useRef } from 'react';
import { AppState, View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';

const UNLOCKED = [
    'All courses & Maxx programs',
    'AI schedules + SMS reminders',
    'Scans, progress, and community',
    'Agartha coach in-app & SMS',
];

const POLL_MAX = 20;

export default function PaymentThankYouScreen() {
    const { refreshUser, user } = useAuth();
    const [loading, setLoading] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const pollCount = useRef(0);

    const paid = user?.is_paid === true;

    /** Webhook can lag — refresh with backoff until paid, then navigator switches to main app. */
    useEffect(() => {
        if (paid) return;
        pollCount.current = 0;
        const appStateRef = { current: AppState.currentState };
        let timer: ReturnType<typeof setTimeout> | null = null;
        let cancelled = false;
        // Fast at first (2s) while webhook is likely in flight; then slow down.
        const nextDelay = () => {
            const n = pollCount.current;
            if (n < 5) return 2000;
            if (n < 10) return 4000;
            return 8000;
        };
        const doPoll = async () => {
            pollCount.current += 1;
            if (pollCount.current > POLL_MAX) return;
            try { await refreshUser(); } catch { /* ignore */ }
            if (!cancelled) timer = setTimeout(tick, nextDelay());
        };
        const tick = () => {
            if (appStateRef.current !== 'active') {
                timer = setTimeout(tick, nextDelay());
                return;
            }
            void doPoll();
        };
        timer = setTimeout(tick, 2000);
        const appSub = AppState.addEventListener('change', (next) => {
            const prev = appStateRef.current;
            appStateRef.current = next;
            if (prev.match(/inactive|background/) && next === 'active') {
                void doPoll();
            }
        });
        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
            appSub.remove();
        };
    }, [paid, refreshUser]);

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

    return (
        <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            keyboardShouldPersistTaps="handled"
        >
            <View style={styles.card}>
                <View style={styles.iconWrap}>
                    <Ionicons name="checkmark-circle" size={72} color={colors.success} />
                </View>
                <Text style={styles.title}>{paid ? 'You’re in' : 'Thanks — almost there'}</Text>
                <Text style={styles.subtitle}>
                    {paid
                        ? 'Your subscription is active. Everything in Agartha is unlocked for you.'
                        : 'If you just paid, Stripe may need a moment to tell us. Tap refresh below, or wait a few seconds and try again.'}
                </Text>

                <View style={styles.list}>
                    <Text style={styles.listTitle}>Included with your membership</Text>
                    {UNLOCKED.map((line, i) => (
                        <View key={i} style={styles.listRow}>
                            <Ionicons name="checkmark-circle" size={18} color={colors.foreground} />
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
                            <Text style={styles.buttonText}>Enter Agartha</Text>
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
                        <ActivityIndicator color={colors.foreground} size="small" />
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
        padding: spacing.xl,
        paddingVertical: spacing.xxl * 2,
    },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl + spacing.md,
        alignItems: 'center',
        maxWidth: 400,
        alignSelf: 'center',
        width: '100%',
        borderWidth: 1,
        borderColor: colors.border,
    },
    iconWrap: { marginBottom: spacing.md },
    title: {
        fontFamily: fonts.serif,
        fontSize: 26,
        fontWeight: '400',
        color: colors.foreground,
        marginBottom: spacing.md,
        textAlign: 'center',
        letterSpacing: -0.4,
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
        paddingVertical: 12,
        paddingHorizontal: spacing.xl,
        borderRadius: borderRadius.md,
        minWidth: 220,
        borderWidth: 1,
        borderColor: colors.foreground,
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
        color: colors.textSecondary,
        textAlign: 'center',
    },
});
