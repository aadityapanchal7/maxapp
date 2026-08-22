import React, { useState, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Platform, Linking } from 'react-native'
import { Alert } from '../../components/InAppAlert';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useFlag } from '../../constants/featureFlags';
import { useAuth } from '../../context/AuthContext';
import { useAppleSubscription } from '../../hooks/useAppleSubscription';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';

// Chad Lite is RETIRED (single-plan pivot, 2026-07): Chad is the only plan.
// Legacy Chadlite subscribers are grandfathered — same price, full Chad access.
const PREMIUM_FEATURES = [
    'Chatbot Pro: deeper, sharper coaching',
    '3 active programs',
    'Daily face scans',
    'Full course library',
    'Priority support',
];

function formatPeriodEnd(iso: string | null | undefined): string | null {
    if (!iso) return null;
    try {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return null;
        return d.toLocaleDateString(undefined, {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
            year: 'numeric',
        });
    } catch {
        return null;
    }
}

function formatApiError(e: unknown): string {
    const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
        return d.map((x: { msg?: string }) => x?.msg || JSON.stringify(x)).join('\n');
    }
    return (e as Error)?.message || 'Could not load subscription status.';
}

export default function ManageSubscriptionScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { user, refreshUser, subscriptionTier } = useAuth();
    const faceScanEnabled = useFlag('faceScan');
    // When the face-scan feature is off, strip every scan-related perk/line so the
    // paywall makes no promise the app can't keep. Flip the flag to fully restore.
    const premiumFeatures = faceScanEnabled ? PREMIUM_FEATURES : PREMIUM_FEATURES.filter((p) => !/scan/i.test(p));
    const apple = useAppleSubscription();
    const appleRestoring = 'restoring' in apple ? !!apple.restoring : false;
    const [loading, setLoading] = useState(true);
    const [statusError, setStatusError] = useState<string | null>(null);
    const [cancelAtPeriodEnd, setCancelAtPeriodEnd] = useState(false);
    const [periodEndIso, setPeriodEndIso] = useState<string | null>(null);
    const [actionBusy, setActionBusy] = useState<string | null>(null);
    const [stripeManageEnabled, setStripeManageEnabled] = useState(false);
    const [noStripeButPaid, setNoStripeButPaid] = useState(false);
    const [billingDegraded, setBillingDegraded] = useState(false);

    const loadStatus = useCallback(async () => {
        setLoading(true);
        setStatusError(null);
        setNoStripeButPaid(false);
        setBillingDegraded(false);
        try {
            const s = await api.getSubscriptionStatus();
            setCancelAtPeriodEnd(!!s.cancel_at_period_end);
            setPeriodEndIso(s.current_period_end_iso ?? null);
            const degraded = !!s.degraded;
            setBillingDegraded(degraded);
            const subId = s.subscription?.id;
            const hasStripe =
                s.has_stripe_subscription === true ||
                (s.has_stripe_subscription === undefined && !!subId);
            setStripeManageEnabled(hasStripe && !degraded && !!subId);
            setNoStripeButPaid(!!user?.is_paid && s.has_stripe_subscription === false);
        } catch (e: unknown) {
            if (user?.is_paid) {
                const raw = user?.subscription_end_date;
                if (raw) {
                    const d = new Date(raw);
                    setPeriodEndIso(!Number.isNaN(d.getTime()) ? d.toISOString() : null);
                } else {
                    setPeriodEndIso(null);
                }
                setCancelAtPeriodEnd(false);
                setStripeManageEnabled(false);
                setNoStripeButPaid(false);
                setBillingDegraded(true);
                setStatusError(null);
            } else {
                setStatusError(formatApiError(e));
            }
        } finally {
            setLoading(false);
        }
    }, [user?.is_paid, user?.subscription_end_date]);

    // Load once on mount; subscription status rarely changes between focuses and
    // refetching on every focus was a major source of redundant API calls.
    const loadedRef = useRef(false);
    useFocusEffect(
        useCallback(() => {
            if (loadedRef.current) return;
            loadedRef.current = true;
            void loadStatus();
        }, [loadStatus]),
    );

    const tier = (subscriptionTier || user?.subscription_tier || 'basic').toLowerCase() as 'basic' | 'premium';
    const periodLabel = formatPeriodEnd(periodEndIso);

    // Chad is the only plan (Lite retired). Legacy Chadlite subscribers show as
    // premium after the grandfather migration and keep their original price.
    const PLANS = [
        {
            tier: 'premium' as const,
            name: 'Chad',
            tag: 'Full stack',
            sub: faceScanEnabled
                ? 'Deeper coaching, daily scans, and the full library.'
                : 'Deeper coaching and the full library.',
            features: premiumFeatures,
            price: '$5.99',
        },
    ];

    const runResume = async () => {
        setActionBusy('resume');
        try {
            await api.resumeSubscription();
            await refreshUser();
            await loadStatus();
        } catch (e: unknown) {
            const msg =
                (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ||
                (e as Error)?.message ||
                'Could not resume.';
            Alert.alert('Error', String(msg));
        } finally {
            setActionBusy(null);
        }
    };

    // Lite is retired: the only tier change left is legacy-basic -> premium
    // (kept for any user whose grandfather migration hasn't landed yet).
    const runChangeTier = async (next: 'premium') => {
        setActionBusy(`tier-${next}`);
        try {
            await api.changeSubscriptionTier(next);
            await refreshUser();
            await loadStatus();
            Alert.alert('Plan updated', "You're on Chad.");
        } catch (e: unknown) {
            const msg =
                (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ||
                (e as Error)?.message ||
                'Could not change plan.';
            Alert.alert('Error', String(msg));
        } finally {
            setActionBusy(null);
        }
    };

    const confirmUpgrade = () => {
        Alert.alert(
            'Upgrade to Chad?',
            'Your payment method will be charged the Chad rate (prorated for the rest of this billing period).',
            [
                { text: 'Not now', style: 'cancel' },
                { text: 'Upgrade', onPress: () => void runChangeTier('premium') },
            ],
        );
    };

    const runCancel = (immediate: boolean) => {
        const title = immediate ? 'Cancel immediately?' : 'Cancel at period end?';
        const message = immediate
            ? 'You will lose access right away. This cannot be undone through the app.'
            : periodLabel
              ? `You keep access until ${periodLabel}. You can resume before then if you change your mind.`
              : 'You keep access until the end of the current billing period.';

        Alert.alert(title, message, [
            { text: 'Go back', style: 'cancel' },
            {
                text: immediate ? 'End now' : 'Schedule cancel',
                style: immediate ? 'destructive' : 'default',
                onPress: async () => {
                    setActionBusy(immediate ? 'cancel-now' : 'cancel-end');
                    try {
                        await api.cancelSubscription(immediate);
                        // The cancel SUCCEEDED past this line — a transient
                        // failure in the follow-up refreshes must NOT surface
                        // "Could not cancel" (retrying then 404s on the already-
                        // cleared subscription, compounding the confusion).
                        try {
                            // Refresh the screen's own status FIRST, then flip
                            // auth LAST: on an immediate cancel refreshUser()
                            // drops isPaid, treatAsFull flips, and the navigator
                            // REMOUNTS into the funnel stack — that remount IS
                            // the exit. The old manual reset here was dispatched
                            // after the remount on the unmounted navigator's
                            // prop and silently dropped, stranding the user on a
                            // stale screen until an app restart.
                            await loadStatus();
                            await refreshUser();
                        } catch (refreshErr) {
                            console.warn('[ManageSubscription] post-cancel refresh failed (cancel itself succeeded):', refreshErr);
                        }
                    } catch (e: unknown) {
                        const msg =
                            (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
                                ?.detail ||
                            (e as Error)?.message ||
                            'Could not cancel.';
                        Alert.alert('Error', String(msg));
                    } finally {
                        setActionBusy(null);
                    }
                },
            },
        ]);
    };

    const handleRestore = async () => {
        if (Platform.OS !== 'ios' || appleRestoring) return;
        try {
            await apple.restorePurchases();
            await refreshUser();
            await loadStatus();
        } catch (e: unknown) {
            const msg =
                (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ||
                (e as Error)?.message ||
                'Could not restore purchases.';
            Alert.alert('Restore failed', String(msg));
        }
    };

    const openCancelMenu = () => {
        Alert.alert('Cancel subscription', 'How would you like to cancel?', [
            { text: 'Close', style: 'cancel' },
            { text: 'End at period end', onPress: () => runCancel(false) },
            { text: 'End immediately', style: 'destructive', onPress: () => runCancel(true) },
        ]);
    };

    const headerTop = Math.max(insets.top, 12) + 48;

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: headerTop }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                </TouchableOpacity>
                <View style={styles.headerTitles}>
                    <Text style={styles.headerTitle}>Subscription</Text>
                    <Text style={styles.headerSubtitle}>Change your plan or cancel anytime.</Text>
                </View>
                <View style={{ width: 40 }} />
            </View>

            <ScrollView
                contentContainerStyle={[styles.scroll, { paddingBottom: spacing.xxxl + insets.bottom }]}
                showsVerticalScrollIndicator={false}
                keyboardShouldPersistTaps="handled"
            >
                {loading ? (
                    <View style={styles.centered}>
                        <ActivityIndicator color={colors.foreground} size="large" />
                        <Text style={styles.loadingHint}>Loading billing…</Text>
                    </View>
                ) : statusError ? (
                    <View style={styles.centered}>
                        <View style={styles.errorIconWrap}>
                            <Ionicons name="cloud-offline-outline" size={32} color={colors.textMuted} />
                        </View>
                        <Text style={styles.errorText}>{statusError}</Text>
                        <TouchableOpacity style={styles.retryBtn} onPress={() => void loadStatus()} activeOpacity={0.8}>
                            <Text style={styles.retryBtnText}>Try again</Text>
                        </TouchableOpacity>
                    </View>
                ) : (
                    <>
                        <Text style={styles.sectionKicker}>YOUR PLANS</Text>
                        <View style={styles.billingPill}>
                            <Ionicons name="sync-outline" size={14} color={colors.textMuted} />
                            <Text style={styles.billingPillText}>Billed weekly · renews automatically</Text>
                        </View>

                        {noStripeButPaid ? (
                            <View style={styles.infoBanner}>
                                <Ionicons name="information-circle-outline" size={22} color={colors.textSecondary} />
                                <Text style={styles.infoBannerText}>
                                    {Platform.OS === 'ios'
                                        ? 'Your subscription is managed through the App Store. Change or cancel your plan in Settings → Subscriptions.'
                                        : 'You have access, but there is no card subscription on file for this account. Plan changes and cancel are not available here.'}
                                </Text>
                                {Platform.OS === 'ios' ? (
                                    <TouchableOpacity
                                        style={styles.iosManageBtn}
                                        onPress={() => Linking.openURL('https://apps.apple.com/account/subscriptions')}
                                        activeOpacity={0.7}
                                    >
                                        <Text style={styles.iosManageBtnText}>Manage in Settings</Text>
                                        <Ionicons name="open-outline" size={14} color={colors.foreground} />
                                    </TouchableOpacity>
                                ) : null}
                            </View>
                        ) : null}

                        {billingDegraded ? (
                            <View style={styles.warnBanner}>
                                <Ionicons name="warning-outline" size={22} color={colors.warning} />
                                <View style={styles.warnBannerBody}>
                                    <Text style={styles.warnBannerTitle}>Billing details incomplete</Text>
                                    <Text style={styles.warnBannerText}>
                                        We could not load live data from the payment provider. Check your connection,
                                        then refresh. Upgrade, downgrade, and cancel stay disabled until billing loads.
                                    </Text>
                                    <TouchableOpacity
                                        style={styles.warnRefreshBtn}
                                        onPress={() => void loadStatus()}
                                        activeOpacity={0.85}
                                    >
                                        <Text style={styles.warnRefreshBtnText}>Refresh billing</Text>
                                    </TouchableOpacity>
                                </View>
                            </View>
                        ) : null}

                        {PLANS.map((plan) => {
                            const isPremiumPlan = plan.tier === 'premium';
                            const isCurrent = tier === plan.tier;
                            const busyThis = actionBusy === 'tier-premium';

                            return (
                                <View
                                    key={plan.tier}
                                    style={[
                                        styles.planCard,
                                        isPremiumPlan ? styles.planCardPremium : styles.planCardBasic,
                                        !isCurrent && styles.planCardNotCurrent,
                                    ]}
                                >
                                    <View style={styles.planHeader}>
                                        <View style={styles.planNameRow}>
                                            {isPremiumPlan ? (
                                                <Ionicons name="sparkles" size={22} color={colors.foreground} style={styles.planIcon} />
                                            ) : (
                                                <Ionicons name="layers-outline" size={22} color={colors.textSecondary} style={styles.planIcon} />
                                            )}
                                            <Text style={styles.planName}>{plan.name}</Text>
                                        </View>
                                        <View style={styles.planHeaderRight}>
                                            {isCurrent ? (
                                                <View style={styles.currentPill}>
                                                    <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                                                    <Text style={styles.currentPillText}>Current</Text>
                                                </View>
                                            ) : null}
                                            <View
                                                style={[
                                                    styles.planTag,
                                                    isPremiumPlan && styles.planTagPremium,
                                                ]}
                                            >
                                                <Text
                                                    style={[
                                                        styles.planTagText,
                                                        isPremiumPlan && styles.planTagTextPremium,
                                                    ]}
                                                >
                                                    {plan.tag}
                                                </Text>
                                            </View>
                                        </View>
                                    </View>
                                    <Text style={styles.planSub}>{plan.sub}</Text>
                                    <View style={styles.priceRow}>
                                        <Text style={styles.price}>{plan.price}</Text>
                                        <Text style={styles.priceLabel}>/wk</Text>
                                    </View>
                                    <View style={styles.featureList}>
                                        {plan.features.map((line) => (
                                            <View key={line} style={styles.featureItem}>
                                                <View
                                                    style={[
                                                        styles.featureIconWrap,
                                                        isPremiumPlan && styles.featureIconWrapPremium,
                                                    ]}
                                                >
                                                    <Ionicons
                                                        name="checkmark"
                                                        size={13}
                                                        color={isPremiumPlan ? colors.buttonText : colors.background}
                                                    />
                                                </View>
                                                <Text style={styles.featureText}>{line}</Text>
                                            </View>
                                        ))}
                                    </View>

                                    {isCurrent ? (
                                        <View style={styles.currentPlanFooter}>
                                            <Text style={styles.currentPlanFooterText}>{"You're subscribed to this plan"}</Text>
                                        </View>
                                    ) : stripeManageEnabled ? (
                                        <TouchableOpacity
                                            style={[styles.cardUpgradeBtn, busyThis && styles.btnDisabled]}
                                            onPress={confirmUpgrade}
                                            disabled={actionBusy !== null}
                                            activeOpacity={0.88}
                                        >
                                            {busyThis ? (
                                                <ActivityIndicator color={colors.buttonText} />
                                            ) : (
                                                <>
                                                    <Text style={styles.cardUpgradeBtnText}>Upgrade to Chad</Text>
                                                    <Ionicons name="arrow-forward" size={18} color={colors.buttonText} />
                                                </>
                                            )}
                                        </TouchableOpacity>
                                    ) : (
                                        <View style={styles.stripeActionPlaceholder}>
                                            <Text style={styles.stripeActionPlaceholderText}>
                                                {Platform.OS === 'ios'
                                                    ? 'Change your plan in iOS Settings → Subscriptions.'
                                                    : 'Upgrade is available when billing is connected to Stripe.'}
                                            </Text>
                                        </View>
                                    )}
                                    {isCurrent ? (
                                        <Text style={styles.legacyPriceNote}>
                                            Subscribed on a legacy Chadlite price? You keep that price with full Chad access.
                                        </Text>
                                    ) : null}
                                </View>
                            );
                        })}

                        {/* Schedule / renewal */}
                        {cancelAtPeriodEnd ? (
                            <View style={styles.statusBanner}>
                                <View style={styles.statusBannerAccent} />
                                <Ionicons name="calendar-outline" size={22} color={colors.warning} />
                                <View style={styles.statusBannerBody}>
                                    <Text style={styles.statusBannerTitle}>Cancellation scheduled</Text>
                                    <Text style={styles.statusBannerDesc}>
                                        {periodLabel
                                            ? `You keep full access until ${periodLabel}.`
                                            : 'You keep access until the end of this billing period.'}
                                    </Text>
                                </View>
                            </View>
                        ) : periodLabel ? (
                            <View style={styles.renewalCard}>
                                <View style={styles.renewalIconCircle}>
                                    <Ionicons name="calendar" size={18} color={colors.foreground} />
                                </View>
                                <View style={styles.renewalTextBlock}>
                                    <Text style={styles.renewalLabel}>Next billing date</Text>
                                    <Text style={styles.renewalValue}>{periodLabel}</Text>
                                </View>
                            </View>
                        ) : null}

                        {cancelAtPeriodEnd && stripeManageEnabled ? (
                            <TouchableOpacity
                                style={[styles.keepBtn, actionBusy === 'resume' && styles.btnDisabled]}
                                onPress={() => void runResume()}
                                disabled={actionBusy !== null}
                                activeOpacity={0.88}
                            >
                                {actionBusy === 'resume' ? (
                                    <ActivityIndicator color={colors.buttonText} />
                                ) : (
                                    <>
                                        <Ionicons name="heart-outline" size={20} color={colors.buttonText} />
                                        <Text style={styles.keepBtnText}>Keep my subscription</Text>
                                    </>
                                )}
                            </TouchableOpacity>
                        ) : null}

                        <Text style={styles.prorationHint}>
                            {Platform.OS === 'ios'
                                ? 'Manage your subscription in iOS Settings → Subscriptions.'
                                : stripeManageEnabled
                                  ? 'Plan changes use your saved card; Stripe applies prorated charges or credits.'
                                  : 'When billing is linked to Stripe, you can change plans and cancel here.'}
                        </Text>

                        {Platform.OS === 'ios' ? (
                            <TouchableOpacity
                                style={[styles.restoreBtn, appleRestoring && styles.btnDisabled]}
                                onPress={() => void handleRestore()}
                                disabled={appleRestoring}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityLabel="Restore previous purchases"
                            >
                                <Ionicons name="refresh-outline" size={18} color={colors.foreground} />
                                <Text style={styles.restoreBtnText}>
                                    {appleRestoring ? 'Restoring…' : 'Restore Purchases'}
                                </Text>
                            </TouchableOpacity>
                        ) : null}

                        {stripeManageEnabled ? (
                            <View style={styles.dangerBlock}>
                                <Text style={styles.sectionKicker}>CANCEL</Text>
                                <TouchableOpacity
                                    style={[styles.dangerBtn, actionBusy?.startsWith('cancel') && styles.btnDisabled]}
                                    onPress={openCancelMenu}
                                    disabled={actionBusy !== null}
                                    activeOpacity={0.85}
                                >
                                    <Ionicons name="close-circle-outline" size={20} color={colors.error} />
                                    <Text style={styles.dangerBtnText}>Cancel subscription</Text>
                                </TouchableOpacity>
                                <Text style={styles.dangerHint}>
                                    You can end at period end and keep access, or stop immediately.
                                </Text>
                            </View>
                        ) : null}
                    </>
                )}
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.borderLight,
        backgroundColor: colors.background,
    },
    backButton: { padding: 4, marginTop: 2 },
    headerTitles: { flex: 1, alignItems: 'center', marginHorizontal: spacing.sm },
    headerTitle: { fontFamily: fonts.serif, fontSize: 20, fontWeight: '400', letterSpacing: -0.3, color: colors.foreground },
    headerSubtitle: {
        fontSize: 12,
        color: colors.textMuted,
        marginTop: 4,
        textAlign: 'center',
        maxWidth: 260,
        lineHeight: 16,
    },
    scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
    centered: { paddingVertical: spacing.xxxl, alignItems: 'center', paddingHorizontal: spacing.md },
    loadingHint: { ...typography.caption, marginTop: spacing.md, color: colors.textMuted },
    errorIconWrap: {
        width: 64,
        height: 64,
        borderRadius: 32,
        backgroundColor: colors.surface,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: spacing.md,
    },
    errorText: { ...typography.bodySmall, color: colors.error, textAlign: 'center', marginBottom: spacing.md },
    retryBtn: {
        backgroundColor: colors.foreground,
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.sm + 2,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    retryBtnText: { color: colors.buttonText, fontWeight: '700', fontSize: 14 },
    sectionKicker: {
        ...typography.label,
        fontSize: 10,
        letterSpacing: 1.4,
        color: colors.textMuted,
        marginBottom: spacing.sm,
    },
    planCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        marginBottom: spacing.xl,
        borderWidth: 1,
        borderColor: colors.border,
    },
    planCardBasic: {},
    planCardPremium: {
        borderColor: colors.foreground,
        borderWidth: 2,
    },
    planCardNotCurrent: {
        opacity: 0.97,
    },
    planHeader: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        marginBottom: spacing.xs,
        gap: spacing.sm,
    },
    planHeaderRight: {
        flexDirection: 'row',
        alignItems: 'center',
        flexWrap: 'wrap',
        justifyContent: 'flex-end',
        gap: 6,
        maxWidth: '52%',
    },
    planNameRow: { flexDirection: 'row', alignItems: 'center', flex: 1, minWidth: 0 },
    currentPill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        backgroundColor: colors.surface,
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: borderRadius.sm,
        borderWidth: 1,
        borderColor: colors.success + '44',
    },
    currentPillText: { fontSize: 11, fontWeight: '800', color: colors.success },
    planIcon: { marginRight: spacing.sm },
    planName: {
        fontFamily: fonts.serif,
        fontSize: 24,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.4,
    },
    planTag: {
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.full,
        paddingHorizontal: 10,
        paddingVertical: 5,
    },
    planTagPremium: {
        backgroundColor: colors.foreground,
        borderColor: colors.foreground,
    },
    planTagText: { fontSize: 11, fontWeight: '700', color: colors.textSecondary },
    planTagTextPremium: { color: colors.buttonText },
    planSub: { fontSize: 14, color: colors.textSecondary, lineHeight: 20, marginBottom: spacing.sm },
    priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4, marginBottom: spacing.md },
    price: { fontSize: 30, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
    priceLabel: { fontSize: 14, fontWeight: '400', color: colors.textMuted },
    billingPill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        alignSelf: 'flex-start',
        backgroundColor: colors.surface,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        borderRadius: borderRadius.full,
        marginBottom: spacing.md,
    },
    billingPillText: { fontSize: 12, fontWeight: '600', color: colors.textMuted },
    infoBanner: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.md,
        backgroundColor: colors.surface,
        padding: spacing.md,
        borderRadius: borderRadius.xl,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    infoBannerText: { flex: 1, fontSize: 13, color: colors.textSecondary, lineHeight: 19 },
    iosManageBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        alignSelf: 'flex-start',
        marginTop: spacing.sm,
        paddingVertical: 8,
        paddingHorizontal: 14,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    iosManageBtnText: { fontSize: 13, fontWeight: '600', color: colors.foreground },
    warnBanner: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.md,
        backgroundColor: colors.surface,
        padding: spacing.md,
        borderRadius: borderRadius.lg,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: colors.warning + '55',
    },
    warnBannerBody: { flex: 1 },
    warnBannerTitle: { fontSize: 14, fontWeight: '700', color: colors.foreground, marginBottom: 4 },
    warnBannerText: { fontSize: 13, color: colors.textSecondary, lineHeight: 19, marginBottom: spacing.sm },
    warnRefreshBtn: {
        alignSelf: 'flex-start',
        backgroundColor: colors.foreground,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    warnRefreshBtnText: { color: colors.buttonText, fontWeight: '700', fontSize: 13 },
    stripeActionPlaceholder: {
        marginTop: spacing.md,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.lg,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
    },
    stripeActionPlaceholderText: { fontSize: 13, color: colors.textMuted, textAlign: 'center', lineHeight: 18 },
    featureList: { gap: spacing.sm },
    featureItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    featureIconWrap: {
        width: 20,
        height: 20,
        borderRadius: 10,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.foreground,
    },
    featureIconWrapPremium: {
        backgroundColor: colors.foreground,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    featureText: { flex: 1, fontSize: 14, color: colors.foreground, lineHeight: 20 },
    currentPlanFooter: {
        marginTop: spacing.md,
        paddingTop: spacing.md,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.borderLight,
        alignItems: 'center',
    },
    currentPlanFooterText: { fontSize: 13, fontWeight: '600', color: colors.textMuted },
    legacyPriceNote: { fontSize: 12, color: colors.textMuted, marginTop: 10, lineHeight: 17 },
    cardUpgradeBtn: {
        marginTop: spacing.md,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.md,
        backgroundColor: colors.foreground,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    cardUpgradeBtnText: { fontSize: 14, fontWeight: '600', color: colors.buttonText, letterSpacing: -0.2 },
    cardDowngradeBtn: {
        marginTop: spacing.md,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.md,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
    },
    cardDowngradeBtnText: { fontSize: 14, fontWeight: '700', color: colors.foreground },
    prorationHint: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        lineHeight: 17,
        marginBottom: spacing.lg,
        paddingHorizontal: spacing.sm,
    },
    restoreBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        alignSelf: 'center',
        paddingVertical: 12,
        paddingHorizontal: spacing.xl,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
        marginBottom: spacing.lg,
    },
    restoreBtnText: { fontSize: 14, fontWeight: '600', color: colors.foreground, letterSpacing: -0.1 },
    statusBanner: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.md,
        backgroundColor: colors.card,
        padding: spacing.md,
        borderRadius: borderRadius.lg,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
        overflow: 'hidden',
        position: 'relative',
    },
    statusBannerAccent: {
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: 4,
        backgroundColor: colors.warning,
        borderTopLeftRadius: borderRadius.xl,
        borderBottomLeftRadius: borderRadius.xl,
    },
    statusBannerBody: { flex: 1, paddingLeft: spacing.sm },
    statusBannerTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground, marginBottom: 4 },
    statusBannerDesc: { fontSize: 13, color: colors.textSecondary, lineHeight: 19 },
    renewalCard: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        backgroundColor: colors.card,
        padding: spacing.md,
        borderRadius: borderRadius.lg,
        marginBottom: spacing.lg,
        borderWidth: 1,
        borderColor: colors.border,
    },
    renewalIconCircle: {
        width: 44,
        height: 44,
        borderRadius: 22,
        backgroundColor: colors.surface,
        alignItems: 'center',
        justifyContent: 'center',
    },
    renewalLabel: { fontSize: 12, fontWeight: '600', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 },
    renewalValue: { fontSize: 16, fontWeight: '700', color: colors.foreground, marginTop: 2 },
    renewalTextBlock: { flex: 1 },
    keepBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.md,
        marginBottom: spacing.lg,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    keepBtnText: { ...typography.button, color: colors.buttonText, fontSize: 14 },
    dangerBlock: { marginTop: spacing.md },
    dangerBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        paddingVertical: 10,
        paddingHorizontal: spacing.sm + 6,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.error + '40',
        backgroundColor: colors.card,
    },
    dangerBtnText: { fontSize: 14, fontWeight: '700', color: colors.error },
    dangerHint: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: spacing.sm,
        lineHeight: 17,
    },
    btnDisabled: { opacity: 0.55 },
});
