import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Alert,
    ScrollView,
    Platform,
} from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { SHOW_DEV_SKIP_CONTROLS } from '../../constants/devSkips';

/** Stripe Payment Links — override with EXPO_PUBLIC_STRIPE_BASIC_LINK / EXPO_PUBLIC_STRIPE_PREMIUM_LINK. Legacy: EXPO_PUBLIC_STRIPE_PAYMENT_LINK maps to Premium only. */
// Chadlite (basic) — $3.99/mo
const STRIPE_BASIC_FALLBACK = 'https://buy.stripe.com/14A4gz5fFdrae7XaHWbII06';
// Chad (premium) — $5.99/mo
const STRIPE_PREMIUM_FALLBACK = 'https://buy.stripe.com/6oU6oH23t1Is8ND17mbII05';

const STRIPE_BASIC_URL = (process.env.EXPO_PUBLIC_STRIPE_BASIC_LINK?.trim() || STRIPE_BASIC_FALLBACK).trim();
const STRIPE_PREMIUM_URL = (
    process.env.EXPO_PUBLIC_STRIPE_PREMIUM_LINK?.trim() ||
    process.env.EXPO_PUBLIC_STRIPE_PAYMENT_LINK?.trim() ||
    STRIPE_PREMIUM_FALLBACK
).trim();

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 20;

const BASIC_FEATURES = [
    'Up to 2 maxxes active',
    'Community forums',
    '1 face scan total (not daily)',
    'Basic course library',
];

const PREMIUM_FEATURES = [
    'Up to 3 maxxes active',
    'Exclusive forums with influencers (alpha tips)',
    '1:1 lives / calls with influencers',
    'Daily face scans',
    'Full course library',
];

function buildCheckoutUrl(base: string, userId: string | undefined): string {
    if (!userId) return base;
    try {
        const u = new URL(base);
        u.searchParams.set('client_reference_id', userId);
        return u.toString();
    } catch {
        const sep = base.includes('?') ? '&' : '?';
        return `${base}${sep}client_reference_id=${encodeURIComponent(userId)}`;
    }
}

export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const { user, refreshUser } = useAuth();
    const [checkoutLoading, setCheckoutLoading] = useState<'basic' | 'premium' | null>(null);
    const [devLoading, setDevLoading] = useState(false);
    const pollingRef = useRef(false);
    const finishedRef = useRef(false);

    const stripeUrlsConfigured = useMemo(() => STRIPE_BASIC_URL.length > 0 && STRIPE_PREMIUM_URL.length > 0, []);
    const basicCheckoutUrl = useMemo(() => buildCheckoutUrl(STRIPE_BASIC_URL, user?.id), [user?.id]);
    const premiumCheckoutUrl = useMemo(() => buildCheckoutUrl(STRIPE_PREMIUM_URL, user?.id), [user?.id]);

    const pollUntilPaid = useCallback(async (): Promise<boolean> => {
        if (pollingRef.current) return false;
        pollingRef.current = true;
        try {
            for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
                try {
                    const u = await refreshUser();
                    if (u?.is_paid && u?.subscription_tier) return true;
                } catch {
                    /* retry */
                }
                await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
            }
            return false;
        } finally {
            pollingRef.current = false;
        }
    }, [refreshUser]);

    /**
     * After browser closes: refresh once; if still unpaid, poll (webhook delay).
     * If paid, RootNavigator remounts (auth-paid) → Main — skip Thank You.
     */
    const finishAfterPayment = useCallback(async () => {
        if (finishedRef.current) return;
        finishedRef.current = true;
        setCheckoutLoading(null);
        try {
            let u = await refreshUser();
            if (!u?.is_paid) {
                const ok = await pollUntilPaid();
                if (ok) {
                    await refreshUser();
                    return;
                }
            } else {
                return;
            }
        } catch {
            /* fall through */
        }
        navigation.navigate('PaymentThankYou');
    }, [navigation, refreshUser, pollUntilPaid]);

    useEffect(() => {
        const handleUrl = (event: { url: string }) => {
            const u = event.url || '';
            if (u.includes('PaymentThankYou')) {
                finishAfterPayment();
            }
        };
        const sub = Linking.addEventListener('url', handleUrl);
        Linking.getInitialURL().then((url) => {
            if (url?.includes('PaymentThankYou')) handleUrl({ url });
        });
        return () => sub.remove();
    }, [finishAfterPayment]);

    const openStripeCheckout = async (checkoutUrl: string, tier: 'basic' | 'premium') => {
        if (user && !user.first_scan_completed) {
            Alert.alert('Face scan first', 'Complete your AI face scan to see your preview score, then you can subscribe.', [
                { text: 'Start scan', onPress: () => navigation.navigate('FaceScan') },
                { text: 'Cancel', style: 'cancel' },
            ]);
            return;
        }
        if (!checkoutUrl) {
            Alert.alert(
                'Stripe link not set',
                'Add EXPO_PUBLIC_STRIPE_BASIC_LINK and EXPO_PUBLIC_STRIPE_PREMIUM_LINK in mobile/.env (restart Expo), or use the defaults in PaymentScreen.tsx.',
            );
            return;
        }

        try {
            setCheckoutLoading(tier);
            WebBrowser.maybeCompleteAuthSession();
            finishedRef.current = false;

            if (Platform.OS === 'web') {
                await WebBrowser.openBrowserAsync(checkoutUrl);
            } else {
                // SFSafariViewController / Custom Tabs — reliable for Stripe; in-app WebView often blank on iOS.
                await WebBrowser.openBrowserAsync(checkoutUrl, {
                    presentationStyle:
                        Platform.OS === 'ios' ? WebBrowser.WebBrowserPresentationStyle.PAGE_SHEET : undefined,
                    enableBarCollapsing: false,
                });
            }
            await finishAfterPayment();
        } catch (e) {
            Alert.alert('Error', 'Could not open checkout. Try again.');
        } finally {
            setCheckoutLoading(null);
        }
    };

    const handleDevSkip = (tier: 'basic' | 'premium' = 'premium') => {
        const doActivate = async () => {
            try {
                setDevLoading(true);
                await api.testActivateSubscription(tier);
                const u = await refreshUser();
                if (!u?.is_paid) {
                    navigation.navigate('PaymentThankYou');
                }
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
                        Secure checkout opens in your browser. Prices and renewal are shown before you pay. When you’re
                        done, you’ll return to the app.
                    </Text>
                </View>

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
                    <Text style={styles.planSub}>Essential maxxes, forums, and one included face scan (not daily).</Text>
                    <View style={styles.priceRow}>
                        <Text style={styles.price}>$3.99</Text>
                        <Text style={styles.priceLabel}>/mo</Text>
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
                        style={[
                            styles.button,
                            styles.buttonSecondary,
                            (!stripeUrlsConfigured || checkoutLoading !== null || devLoading) && styles.buttonMuted,
                        ]}
                        activeOpacity={0.85}
                        onPress={() => openStripeCheckout(basicCheckoutUrl, 'basic')}
                        disabled={checkoutLoading !== null || devLoading}
                        accessibilityRole="button"
                        accessibilityLabel="Continue with Basic plan"
                    >
                        <Text style={[styles.buttonText, styles.buttonTextOnSurface]}>
                            {checkoutLoading === 'basic' ? 'Opening checkout…' : 'Continue with Basic'}
                        </Text>
                    </TouchableOpacity>
                </View>

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
                        <Text style={styles.priceLabel}>/mo</Text>
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
                        style={[
                            styles.button,
                            (!stripeUrlsConfigured || checkoutLoading !== null || devLoading) && styles.buttonMuted,
                        ]}
                        activeOpacity={0.85}
                        onPress={() => openStripeCheckout(premiumCheckoutUrl, 'premium')}
                        disabled={checkoutLoading !== null || devLoading}
                        accessibilityRole="button"
                        accessibilityLabel="Continue with Premium plan"
                    >
                        <Text style={styles.buttonText}>
                            {checkoutLoading === 'premium' ? 'Opening checkout…' : 'Continue with Premium'}
                        </Text>
                    </TouchableOpacity>
                </View>

                {stripeUrlsConfigured ? null : (
                    <Text style={styles.linkHint}>Stripe Payment Links aren’t configured.</Text>
                )}

                {SHOW_DEV_SKIP_CONTROLS ? (
                    <View style={styles.devRow}>
                        <TouchableOpacity
                            style={styles.devButton}
                            activeOpacity={0.85}
                            onPress={() => handleDevSkip('basic')}
                            disabled={devLoading || checkoutLoading !== null}
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
                            disabled={devLoading || checkoutLoading !== null}
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
    metaRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
    metaPill: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
        paddingVertical: 8,
        paddingHorizontal: 8,
    },
    metaText: { fontSize: 11, color: colors.textSecondary, fontWeight: '600' },
    linkHint: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: spacing.md,
        lineHeight: 18,
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
