import React, { useState, useMemo, useEffect, useCallback } from 'react';
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
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

/** Optional: paste your Stripe Payment Link here if you’re not using .env yet. */
const STRIPE_LINK_FALLBACK = '';

const STRIPE_CHECKOUT_URL = (
    process.env.EXPO_PUBLIC_STRIPE_PAYMENT_LINK?.trim() || STRIPE_LINK_FALLBACK
).trim();

/**
 * Must match Stripe Payment Link (or Checkout) “redirect after payment” URL exactly.
 * Override if Stripe only allows https — use a page that redirects to this app URL.
 */
function getPaymentReturnUrl(): string {
    const override = process.env.EXPO_PUBLIC_STRIPE_RETURN_URL?.trim();
    if (override) return override;
    return Linking.createURL('PaymentThankYou');
}

const PRICE = '9.99';

const FULL_ACCESS_FEATURES = [
    'Full course library & every Maxx track',
    'AI schedules + SMS reminders that keep you on track',
    'Face scans & progress tracking',
    'Fitmax workouts, routines, and check-ins',
    'Community, forums, and live events',
    'Max coach in the app and over SMS',
];

export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const { refreshUser } = useAuth();
    const [checkoutLoading, setCheckoutLoading] = useState(false);
    const [devLoading, setDevLoading] = useState(false);

    const stripeUrlConfigured = useMemo(() => STRIPE_CHECKOUT_URL.length > 0, []);
    const paymentReturnUrl = useMemo(() => getPaymentReturnUrl(), []);

    const finishAfterPayment = useCallback(async () => {
        try {
            await refreshUser();
        } catch {
            /* still land on thank-you */
        }
        navigation.navigate('PaymentThankYou');
    }, [navigation, refreshUser]);

    /** Deep link / universal link → thank-you (backup if auth session doesn’t fire). */
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

    const openStripeCheckout = async () => {
        if (!STRIPE_CHECKOUT_URL) {
            Alert.alert(
                'Stripe link not set yet',
                'Add EXPO_PUBLIC_STRIPE_PAYMENT_LINK in mobile/.env (restart Expo), or paste the URL in STRIPE_LINK_FALLBACK in PaymentScreen.tsx.',
            );
            return;
        }

        try {
            setCheckoutLoading(true);
            WebBrowser.maybeCompleteAuthSession();

            if (Platform.OS === 'web') {
                await WebBrowser.openBrowserAsync(STRIPE_CHECKOUT_URL);
                return;
            }

            const result = await WebBrowser.openAuthSessionAsync(STRIPE_CHECKOUT_URL, paymentReturnUrl);
            WebBrowser.maybeCompleteAuthSession();

            if (result.type === 'success') {
                await finishAfterPayment();
            }
        } catch (e) {
            Alert.alert('Error', 'Could not open checkout. Try again.');
        } finally {
            setCheckoutLoading(false);
        }
    };

    const handleDevSkip = async () => {
        try {
            setDevLoading(true);
            await api.testActivateSubscription();
            await refreshUser();
            navigation.navigate('PaymentThankYou');
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

    return (
        <View style={styles.container}>
            <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
                <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>

                <View style={styles.header}>
                    <Text style={styles.title}>Choose your plan</Text>
                    <Text style={styles.subtitle}>
                        One membership — full access to everything in Max for ${PRICE}/month.
                    </Text>
                </View>

                <View style={styles.planCard}>
                    <View style={styles.planHeader}>
                        <Text style={styles.planName}>Full access</Text>
                        <View style={styles.priceRow}>
                            <Text style={styles.price}>${PRICE}</Text>
                            <Text style={styles.priceLabel}>/month</Text>
                        </View>
                    </View>

                    <View style={styles.featureList}>
                        {FULL_ACCESS_FEATURES.map((feature, idx) => (
                            <View key={idx} style={styles.featureItem}>
                                <Ionicons name="checkmark" size={16} color={colors.foreground} />
                                <Text style={styles.featureText}>{feature}</Text>
                            </View>
                        ))}
                    </View>

                    <TouchableOpacity
                        style={[styles.button, (!stripeUrlConfigured || checkoutLoading || devLoading) && styles.buttonMuted]}
                        activeOpacity={0.85}
                        onPress={openStripeCheckout}
                        disabled={checkoutLoading || devLoading}
                    >
                        <Text style={styles.buttonText}>
                            {checkoutLoading ? 'Opening checkout…' : 'Continue to checkout'}
                        </Text>
                    </TouchableOpacity>

                    {stripeUrlConfigured ? (
                        <View style={styles.redirectBlock}>
                            <Text style={styles.redirectHint}>
                                After payment, Stripe should send you back into the app. In your Payment Link (or
                                Checkout) settings, set the success redirect URL to exactly:
                            </Text>
                            <Text style={styles.redirectUrl} selectable>
                                {paymentReturnUrl}
                            </Text>
                            {!process.env.EXPO_PUBLIC_STRIPE_RETURN_URL?.trim() ? (
                                <Text style={[styles.redirectHint, styles.redirectHintSpaced]}>
                                    Optional: use EXPO_PUBLIC_STRIPE_RETURN_URL if you redirect via an https page that
                                    then opens the app.
                                </Text>
                            ) : null}
                        </View>
                    ) : (
                        <Text style={styles.linkHint}>
                            Add your Stripe link in .env as EXPO_PUBLIC_STRIPE_PAYMENT_LINK, then restart Expo.
                        </Text>
                    )}
                </View>

                <Text style={styles.disclaimer}>
                    You can change or cancel your plan any time from your account settings.
                </Text>

                <TouchableOpacity
                    style={styles.devButton}
                    activeOpacity={0.85}
                    onPress={handleDevSkip}
                    disabled={devLoading || checkoutLoading}
                >
                    <Text style={styles.devButtonText}>
                        {devLoading ? 'Activating…' : 'DEV: Skip payment & unlock'}
                    </Text>
                </TouchableOpacity>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg, paddingTop: 64, paddingBottom: 40 },
    backButton: { position: 'absolute', top: 54, left: spacing.lg, zIndex: 10, padding: spacing.sm },
    header: { alignItems: 'flex-start', marginBottom: spacing.xl, marginTop: spacing.xl },
    title: {
        fontSize: 28,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: -0.5,
        marginBottom: spacing.xs,
    },
    subtitle: { fontSize: 13, color: colors.textSecondary, lineHeight: 19 },
    planCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        marginBottom: spacing.lg,
        ...shadows.md,
    },
    planHeader: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        marginBottom: spacing.md,
    },
    planName: {
        fontSize: 18,
        fontWeight: '600',
        color: colors.foreground,
        textTransform: 'uppercase',
    },
    priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
    price: { fontSize: 28, fontWeight: '700', color: colors.foreground },
    priceLabel: { fontSize: 14, fontWeight: '400', color: colors.textMuted },
    featureList: { marginBottom: spacing.lg, gap: spacing.sm },
    featureItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    featureText: { flex: 1, fontSize: 14, color: colors.foreground },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.md,
        alignItems: 'center',
        ...shadows.md,
    },
    buttonMuted: { opacity: 0.5 },
    buttonText: { ...typography.button },
    linkHint: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: spacing.md,
        lineHeight: 18,
    },
    redirectBlock: { marginTop: spacing.md },
    redirectHint: {
        fontSize: 11,
        color: colors.textMuted,
        lineHeight: 16,
    },
    redirectHintSpaced: { marginTop: spacing.sm },
    redirectUrl: {
        fontSize: 11,
        color: colors.textSecondary,
        fontWeight: '600',
        marginTop: spacing.xs,
        lineHeight: 15,
    },
    disclaimer: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: spacing.md,
    },
    devButton: {
        marginTop: spacing.lg,
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
