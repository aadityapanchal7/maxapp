import React, { useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Alert,
    ScrollView,
    Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useStripeSubscription } from '../../hooks/useStripeSubscription';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { SHOW_DEV_SKIP_CONTROLS } from '../../constants/devSkips';

const BASIC_FEATURES = [
    'Up to 2 maxxes active',
    'Community forums',
    '1 face scan with Basic (signup) — no additional scans',
    'Basic course library',
];

const PREMIUM_FEATURES = [
    'Up to 3 maxxes active',
    'Exclusive forums with influencers (alpha tips)',
    '1:1 lives / calls with influencers',
    'Daily face scans',
    'Full course library',
];

export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const { user, refreshUser } = useAuth();
    const { loading: stripeLoading, subscribeBasic, subscribePremium } = useStripeSubscription();
    const [devLoading, setDevLoading] = useState(false);

    const busy = stripeLoading !== null || devLoading;

    const handleSubscribe = async (tier: 'basic' | 'premium') => {
        if (user && !user.first_scan_completed) {
            Alert.alert(
                'Face scan first',
                'Complete your AI face scan to see your preview score, then you can subscribe.',
                [
                    { text: 'Start scan', onPress: () => navigation.navigate('FaceScan') },
                    { text: 'Cancel', style: 'cancel' },
                ],
            );
            return;
        }

        await (tier === 'basic' ? subscribeBasic() : subscribePremium());
        // Hook refreshes on success and polls until paid or gives up. When is_paid is true,
        // RootNavigator remounts to Main. Never push PaymentThankYou on failure/cancel/pending —
        // that wrongly showed "almost there" without a confirmed subscription.
    };

    const handleDevSkip = (tier: 'basic' | 'premium' = 'premium') => {
        const doActivate = async () => {
            try {
                setDevLoading(true);
                await api.testActivateSubscription(tier);
                await refreshUser();
                // Paid → RootNavigator sends user to Main; unpaid → stay on payment.
            } catch (error: any) {
                const msg =
                    error?.response?.data?.detail ||
                    error?.message ||
                    (error?.response?.status === 401 ? 'Please log in first.' : 'Failed to activate dev subscription.');
                Alert.alert('Error', String(msg));
            } finally {
                setDevLoading(false);
            }
        };
        void doActivate();
    };

    return (
        <View style={styles.container}>
            <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
                <TouchableOpacity
                    style={styles.backButton}
                    onPress={() => navigation.goBack()}
                    activeOpacity={0.7}
                    accessibilityRole="button"
                    accessibilityLabel="Back"
                >
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>

                <View style={styles.header}>
                    <Text style={styles.kicker}>SUBSCRIBE</Text>
                    <Text style={styles.title}>Choose Basic or Premium</Text>
                    <Text style={styles.subtitle}>
                        {Platform.OS === 'web'
                            ? 'In-app checkout is available on iOS and Android.'
                            : 'Pay with card — your payment method is saved securely by Stripe.'}
                    </Text>
                </View>

                {/* ── Chadlite (basic) ── */}
                <View style={[styles.planCard, styles.planCardBasic]}>
                    <LinearGradient
                        colors={['rgba(255,255,255,0.1)', 'rgba(255,255,255,0.02)']}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={styles.planCardSheen}
                        pointerEvents="none"
                    />
                    <View style={styles.planHeader}>
                        <Text style={styles.planName}>Chadlite</Text>
                        <View style={styles.planTag}>
                            <Text style={styles.planTagText}>Core access</Text>
                        </View>
                    </View>
                    <Text style={styles.planSub}>
                        Essential maxxes and forums. One face scan when you sign up — Basic does not add extra scans;
                        upgrade for daily scans.
                    </Text>
                    <View style={styles.priceRow}>
                        <Text style={styles.price}>$3.99</Text>
                        <Text style={styles.priceLabel}>/wk</Text>
                    </View>
                    <View style={styles.featureList}>
                        {BASIC_FEATURES.map((feature, idx) => (
                            <View key={idx} style={styles.featureItem}>
                                <View style={styles.featureIconWrap}>
                                    <Ionicons name="checkmark" size={13} color={colors.background} />
                                </View>
                                <Text style={styles.featureText}>{feature}</Text>
                            </View>
                        ))}
                    </View>
                    <TouchableOpacity
                        style={[styles.button, styles.buttonSecondary, busy && styles.buttonMuted]}
                        activeOpacity={0.85}
                        onPress={() => handleSubscribe('basic')}
                        disabled={busy}
                        accessibilityRole="button"
                        accessibilityLabel="Continue with Basic plan"
                    >
                        <Text style={[styles.buttonText, styles.buttonTextOnSurface]}>
                            {stripeLoading === 'basic' ? 'Processing…' : 'Continue with Basic'}
                        </Text>
                    </TouchableOpacity>
                </View>

                {/* ── Chad (premium) ── */}
                <View style={[styles.planCard, styles.planCardPremium]}>
                    <LinearGradient
                        colors={['rgba(255,255,255,0.16)', 'rgba(255,255,255,0.04)']}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={styles.planCardSheen}
                        pointerEvents="none"
                    />
                    <View style={styles.planHeader}>
                        <Text style={styles.planName}>Chad</Text>
                        <View style={[styles.planTag, styles.planTagAccent]}>
                            <Text style={styles.planTagTextAccent}>Full stack</Text>
                        </View>
                    </View>
                    <Text style={styles.planSub}>Influencer access, daily scans, and the full library.</Text>
                    <View style={styles.priceRow}>
                        <Text style={styles.price}>$5.99</Text>
                        <Text style={styles.priceLabel}>/wk</Text>
                    </View>
                    <View style={styles.featureList}>
                        {PREMIUM_FEATURES.map((feature, idx) => (
                            <View key={idx} style={styles.featureItem}>
                                <View style={styles.featureIconWrap}>
                                    <Ionicons name="checkmark" size={13} color={colors.background} />
                                </View>
                                <Text style={styles.featureText}>{feature}</Text>
                            </View>
                        ))}
                    </View>
                    <TouchableOpacity
                        style={[styles.button, busy && styles.buttonMuted]}
                        activeOpacity={0.85}
                        onPress={() => handleSubscribe('premium')}
                        disabled={busy}
                        accessibilityRole="button"
                        accessibilityLabel="Continue with Premium plan"
                    >
                        <Text style={styles.buttonText}>
                            {stripeLoading === 'premium' ? 'Processing…' : 'Continue with Premium'}
                        </Text>
                    </TouchableOpacity>
                </View>

                <Text style={styles.disclaimer}>
                    Manage billing from Stripe emails or customer portal. Subscriptions renew weekly until cancelled.
                </Text>

                {SHOW_DEV_SKIP_CONTROLS ? (
                    <View style={styles.devRow}>
                        <TouchableOpacity
                            style={styles.devButton}
                            activeOpacity={0.85}
                            onPress={() => handleDevSkip('basic')}
                            disabled={busy}
                            accessibilityRole="button"
                            accessibilityLabel="Developer skip basic"
                        >
                            <Text style={styles.devButtonText}>
                                {devLoading ? 'Activating…' : 'DEV: Basic'}
                            </Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={styles.devButton}
                            activeOpacity={0.85}
                            onPress={() => handleDevSkip('premium')}
                            disabled={busy}
                            accessibilityRole="button"
                            accessibilityLabel="Developer skip premium"
                        >
                            <Text style={styles.devButtonText}>
                                {devLoading ? 'Activating…' : 'DEV: Premium'}
                            </Text>
                        </TouchableOpacity>
                    </View>
                ) : null}
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg, paddingTop: 64, paddingBottom: 40 },
    backButton: { position: 'absolute', top: 54, left: spacing.lg, zIndex: 10, padding: spacing.sm },
    header: { alignItems: 'flex-start', marginBottom: spacing.xl, marginTop: spacing.xl },
    kicker: {
        ...typography.label,
        color: colors.textMuted,
        letterSpacing: 1.2,
        marginBottom: spacing.xs,
    },
    title: {
        fontSize: 28,
        fontWeight: '700',
        color: colors.foreground,
        letterSpacing: -0.5,
        marginBottom: spacing.xs,
    },
    subtitle: { fontSize: 14, color: colors.textSecondary, lineHeight: 21, maxWidth: 340 },
    planCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        marginBottom: spacing.lg,
        ...shadows.md,
        borderWidth: 1,
        borderColor: colors.border,
        overflow: 'hidden',
        position: 'relative',
    },
    planCardBasic: {},
    planCardPremium: {
        borderColor: colors.foreground,
        borderWidth: 2,
    },
    planCardSheen: { ...StyleSheet.absoluteFillObject },
    planHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.sm,
        gap: spacing.sm,
    },
    planTag: {
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.full,
        paddingHorizontal: 10,
        paddingVertical: 5,
    },
    planTagAccent: {
        backgroundColor: colors.foreground,
        borderColor: colors.foreground,
    },
    planTagText: { fontSize: 11, fontWeight: '700', color: colors.textSecondary },
    planTagTextAccent: { fontSize: 11, fontWeight: '700', color: colors.background },
    planName: {
        fontSize: 22,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: -0.3,
    },
    planSub: { fontSize: 13, color: colors.textMuted, marginTop: 4, marginBottom: spacing.md },
    priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
    price: { fontSize: 34, fontWeight: '700', color: colors.foreground },
    priceLabel: { fontSize: 14, fontWeight: '400', color: colors.textMuted },
    featureList: { marginBottom: spacing.lg, gap: spacing.sm },
    featureItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    featureIconWrap: {
        width: 18,
        height: 18,
        borderRadius: 9,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.foreground,
    },
    featureText: { flex: 1, fontSize: 14, color: colors.foreground },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.md,
        alignItems: 'center',
        ...shadows.md,
    },
    buttonSecondary: {
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
    },
    buttonTextOnSurface: {
        color: colors.foreground,
    },
    buttonMuted: { opacity: 0.5 },
    buttonText: { ...typography.button },
    disclaimer: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: spacing.md,
    },
    devRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg },
    devButton: {
        flex: 1,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.sm,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
    },
    devButtonText: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.textSecondary,
    },
});
