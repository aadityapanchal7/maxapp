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
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useStripeSubscription } from '../../hooks/useStripeSubscription';
import { colors, spacing, borderRadius, fonts } from '../../theme/dark';
import { SHOW_DEV_SKIP_CONTROLS } from '../../constants/devSkips';

const BASIC_PERKS = [
    '2 active programs',
    'Community forums',
    '1 face scan',
    'Basic course library',
];

const PREMIUM_PERKS = [
    '3 active programs',
    'Influencer forums & 1:1 lives',
    'Daily face scans',
    'Full course library',
];

export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
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
    };

    const handleDevSkip = (tier: 'basic' | 'premium' = 'premium') => {
        const doActivate = async () => {
            try {
                setDevLoading(true);
                await api.testActivateSubscription(tier);
                await refreshUser();
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
        <View style={s.container}>
            <View style={[s.topBar, { paddingTop: Math.max(insets.top, 12) }]}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={s.backBtn}
                    activeOpacity={0.7}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                    accessibilityRole="button"
                    accessibilityLabel="Back"
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>
            </View>

            <ScrollView
                contentContainerStyle={s.scroll}
                showsVerticalScrollIndicator={false}
            >
                <Text style={s.headline}>Your plan</Text>
                <Text style={s.subline}>
                    {Platform.OS === 'web'
                        ? 'Checkout is available on iOS and Android.'
                        : 'Secure payment via Stripe. Cancel anytime.'}
                </Text>

                {/* ── Premium (recommended) ── */}
                <View style={s.cardPremium}>
                    <View style={s.recommendedBadge}>
                        <Text style={s.recommendedText}>RECOMMENDED</Text>
                    </View>
                    <Text style={[s.cardName, { color: colors.background }]}>Chad</Text>
                    <View style={s.priceRow}>
                        <Text style={[s.priceValue, { color: colors.background }]}>$5.99</Text>
                        <Text style={[s.pricePer, { color: 'rgba(245,245,243,0.55)' }]}>/week</Text>
                    </View>
                    <View style={s.perksList}>
                        {PREMIUM_PERKS.map((p, i) => (
                            <View key={i} style={s.perkRow}>
                                <Ionicons name="checkmark" size={15} color={colors.background} />
                                <Text style={[s.perkText, { color: 'rgba(245,245,243,0.85)' }]}>{p}</Text>
                            </View>
                        ))}
                    </View>
                    <TouchableOpacity
                        style={[s.ctaPrimary, busy && s.ctaDisabled]}
                        onPress={() => handleSubscribe('premium')}
                        disabled={busy}
                        activeOpacity={0.8}
                        accessibilityRole="button"
                        accessibilityLabel="Continue with Premium plan"
                    >
                        <Text style={s.ctaPrimaryText}>
                            {stripeLoading === 'premium' ? 'Processing…' : 'Get Chad'}
                        </Text>
                    </TouchableOpacity>
                </View>

                {/* ── Basic ── */}
                <View style={s.cardBasic}>
                    <Text style={s.cardName}>Chadlite</Text>
                    <View style={s.priceRow}>
                        <Text style={s.priceValue}>$3.99</Text>
                        <Text style={s.pricePer}>/week</Text>
                    </View>
                    <View style={s.perksList}>
                        {BASIC_PERKS.map((p, i) => (
                            <View key={i} style={s.perkRow}>
                                <Ionicons name="checkmark" size={15} color={colors.textMuted} />
                                <Text style={[s.perkText, { color: colors.textSecondary }]}>{p}</Text>
                            </View>
                        ))}
                    </View>
                    <TouchableOpacity
                        style={[s.ctaSecondary, busy && s.ctaDisabled]}
                        onPress={() => handleSubscribe('basic')}
                        disabled={busy}
                        activeOpacity={0.8}
                        accessibilityRole="button"
                        accessibilityLabel="Continue with Basic plan"
                    >
                        <Text style={s.ctaSecondaryText}>
                            {stripeLoading === 'basic' ? 'Processing…' : 'Get Chadlite'}
                        </Text>
                    </TouchableOpacity>
                </View>

                <Text style={s.disclaimer}>
                    Subscriptions renew weekly until cancelled.{'\n'}
                    Manage billing via Stripe customer portal.
                </Text>

                {SHOW_DEV_SKIP_CONTROLS ? (
                    <View style={s.devRow}>
                        <TouchableOpacity style={s.devBtn} onPress={() => handleDevSkip('basic')} disabled={busy}>
                            <Text style={s.devBtnText}>{devLoading ? 'Activating…' : 'DEV: Basic'}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={s.devBtn} onPress={() => handleDevSkip('premium')} disabled={busy}>
                            <Text style={s.devBtnText}>{devLoading ? 'Activating…' : 'DEV: Premium'}</Text>
                        </TouchableOpacity>
                    </View>
                ) : null}
            </ScrollView>
        </View>
    );
}

const s = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    topBar: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.sm,
    },
    backBtn: {
        width: 40,
        height: 40,
        justifyContent: 'center',
    },
    scroll: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.xxxl,
    },

    headline: {
        fontFamily: fonts.serif,
        fontSize: 32,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.5,
        marginTop: spacing.md,
    },
    subline: {
        fontSize: 14,
        color: colors.textSecondary,
        lineHeight: 20,
        marginTop: spacing.sm,
        marginBottom: spacing.xl + spacing.md,
    },

    // ── Premium card ────────────────────────────────────────────────
    cardPremium: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.lg,
        padding: spacing.xl,
        marginBottom: spacing.lg,
    },
    recommendedBadge: {
        alignSelf: 'flex-start',
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: 'rgba(245,245,243,0.25)',
        paddingVertical: 3,
        paddingHorizontal: 10,
        marginBottom: spacing.lg,
    },
    recommendedText: {
        fontSize: 10,
        fontWeight: '700',
        color: colors.background,
        letterSpacing: 1.2,
    },

    // ── Basic card ──────────────────────────────────────────────────
    cardBasic: {
        borderRadius: borderRadius.lg,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        padding: spacing.xl,
        marginBottom: spacing.xl,
    },

    cardName: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        letterSpacing: -0.3,
    },
    priceRow: {
        flexDirection: 'row',
        alignItems: 'baseline',
        gap: 4,
        marginTop: spacing.sm,
    },
    priceValue: {
        fontSize: 36,
        fontWeight: '700',
        letterSpacing: -1,
    },
    pricePer: {
        fontSize: 14,
        fontWeight: '400',
    },
    perksList: {
        marginTop: spacing.lg,
        marginBottom: spacing.xl,
        gap: 10,
    },
    perkRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    perkText: {
        fontSize: 14,
        fontWeight: '400',
        flex: 1,
    },

    // ── CTAs ────────────────────────────────────────────────────────
    ctaPrimary: {
        backgroundColor: colors.background,
        borderRadius: borderRadius.full,
        paddingVertical: 14,
        alignItems: 'center',
    },
    ctaPrimaryText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: 0.1,
    },
    ctaSecondary: {
        borderRadius: borderRadius.full,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        paddingVertical: 14,
        alignItems: 'center',
    },
    ctaSecondaryText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: 0.1,
    },
    ctaDisabled: { opacity: 0.45 },

    disclaimer: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        lineHeight: 18,
    },

    devRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg },
    devBtn: {
        flex: 1,
        borderRadius: borderRadius.md,
        paddingVertical: 10,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
    },
    devBtnText: { fontSize: 13, fontWeight: '600', color: colors.textSecondary },
});
