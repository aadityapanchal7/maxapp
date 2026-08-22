/**
 * ReferralCodeScreen — the step right before the paywall. Enter a referral code
 * (caps-only) and Apply → "Approved". On a full free comp (e.g. CASH99, 1 week
 * of premium) the bottom button redeems server-side and routes PAST the payment
 * screen. No code → continue to checkout as normal. The client never
 * self-grants — a comp only routes forward after the server confirms entitlement.
 *
 * Funnel V4 (pay-BEFORE-account): the visitor here is normally still the
 * anonymous funnel account — that's expected, NOT a bounce condition. After a
 * comp redeems mid-funnel the navigator can't remount into the paid stack
 * (onboarding incomplete keeps treatAsFull false), so the comp path continues
 * the funnel explicitly to CreateAccount, exactly like PaymentScreen's
 * afterPurchase. Post-onboarding entries (courses / manage-subscription
 * upsells) still ride the remount + post-pay flag.
 *
 * Centered, "Craft"-aesthetic layout (cream canvas, serif display title) to match
 * Landing / the paywall.
 */
import React, { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, KeyboardAvoidingView, Platform } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { ReferralCodeField, ReferralCodeHandle } from '../../components/ReferralCodeField';
import { useAuth } from '../../context/AuthContext';
import { useFlag } from '../../constants/featureFlags';
import { markPostPayPending } from '../../lib/postPayNav';
import { fonts } from '../../theme/dark';

const INK = '#15130F';
const SUB = '#6B6B6B';
const BG = '#F4F2ED';

export default function ReferralCodeScreen() {
    const nav = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { user } = useAuth();
    const referralsEnabled = useFlag('referrals');
    const initialCode: string | undefined = route?.params?.referralCode;

    const fieldRef = useRef<ReferralCodeHandle>(null);
    const [compReady, setCompReady] = useState(false);

    // When the `referrals` flag is OFF, the code field renders nothing — this
    // mandatory funnel step would otherwise show a "Have a referral code?" prompt
    // with no input. Skip straight to the paywall so users aren't stranded.
    useEffect(() => {
        if (!referralsEnabled) nav.replace('Payment', route?.params);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [referralsEnabled]);

    // NOTE (funnel V4): the old account-first guest gate that bounced anonymous
    // users to CreateAccount is gone — under pay-before-account the funnel user
    // IS anonymous at this step, and the account is claimed AFTER payment/comp.

    // No code (or a discount-only code): continue to the paywall, passing any
    // params (e.g. a pre-filled referralCode) straight through.
    const goPayment = () => nav.navigate('Payment', route?.params);

    // Bottom button: a full comp redeems + routes PAST the paywall; otherwise
    // it's a normal "continue to checkout".
    const onContinue = async () => {
        if (compReady) {
            const comped = await fieldRef.current?.redeem();
            if (comped) return; // onComped already routed us into the app
            // A validated comp that failed to redeem (transient error) must NOT
            // silently fall through to the paywall — the field is showing the
            // error; let the user retry (or tap "I don't have a code" to skip).
            return;
        }
        goPayment();
    };

    if (!referralsEnabled) return <View style={styles.root} />;  // redirecting to Payment (referrals off)

    return (
        <View style={[styles.root, { paddingTop: insets.top + 6 }]}>
            <TouchableOpacity style={styles.back} onPress={() => nav.goBack()} hitSlop={12} accessibilityLabel="Back">
                <Ionicons name="chevron-back" size={26} color={INK} />
            </TouchableOpacity>

            <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
                <ScrollView
                    contentContainerStyle={styles.content}
                    keyboardShouldPersistTaps="handled"
                    showsVerticalScrollIndicator={false}
                >
                    <Text style={styles.title}>
                        Have a referral{'\n'}<Text style={styles.titleItalic}>code?</Text>
                    </Text>
                    <Text style={styles.sub}>Enter it to unlock access. No code? Continue to checkout.</Text>

                    {/* Caps-only input + validate. On a full comp the bottom button
                        redeems (server grants), refreshes auth and routes past the paywall. */}
                    <ReferralCodeField
                        ref={fieldRef}
                        initialCode={initialCode}
                        onValidated={(res) => setCompReady(res.valid && res.free)}
                        onComped={() => {
                            // Set the same one-shot post-pay flag the real IAP
                            // purchase path uses (so a stack remount, if one
                            // happens, also routes to the reveal).
                            markPostPayPending();
                            // ALWAYS route actively — never wait for a navigator
                            // remount. A remount only happens when treatAsFull
                            // FLIPS; a user who was already in the full stack
                            // (free tier, resumed paid-incomplete, upsell entry)
                            // gets no remount and used to sit stuck here until
                            // an app restart.
                            if (user?.onboarding?.completed !== true) {
                                // Mid-funnel: claim the account next, exactly
                                // like PaymentScreen.afterPurchase.
                                nav.navigate('CreateAccount', route?.params);
                                return;
                            }
                            // Onboarded: straight to the post-pay reveal (the
                            // screen is registered in BOTH stacks, so this works
                            // whether or not a remount follows; if one does, the
                            // post-pay flag re-routes to the same place).
                            const names: string[] = ((nav.getState?.() as any)?.routeNames) ?? [];
                            if (names.includes('FaceScanResults')) {
                                nav.navigate('FaceScanResults', { postPay: true });
                            } else if (names.includes('Main')) {
                                nav.navigate('Main');
                            } else if (nav.canGoBack()) {
                                nav.goBack();
                            }
                        }}
                    />

                    <TouchableOpacity style={styles.cta} onPress={onContinue} activeOpacity={0.85} accessibilityRole="button">
                        <Text style={styles.ctaText}>{compReady ? 'Unlock access' : 'Continue to checkout'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.skip} onPress={goPayment} hitSlop={8} accessibilityRole="button">
                        <Text style={styles.skipText}>I don’t have a code</Text>
                    </TouchableOpacity>
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG, paddingHorizontal: 24 },
    back: { width: 40, height: 40, alignItems: 'flex-start', justifyContent: 'center' },
    // flexGrow + center → vertically centered when there's room, scrolls when the keyboard is up.
    content: { flexGrow: 1, justifyContent: 'center', paddingBottom: 40 },
    title: { fontFamily: fonts.serif, fontSize: 33, color: INK, letterSpacing: -0.6, lineHeight: 37 },
    titleItalic: { fontFamily: fonts.serifItalic, fontStyle: 'italic' },
    sub: { fontFamily: fonts.sans, fontSize: 15.5, color: SUB, marginTop: 12, lineHeight: 22 },
    cta: {
        marginTop: 28, alignSelf: 'stretch', height: 58, borderRadius: 29, borderCurve: 'continuous',
        backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center',
        ...(Platform.OS === 'ios'
            ? { shadowColor: '#1A1714', shadowOpacity: 0.10, shadowRadius: 14, shadowOffset: { width: 0, height: 6 } }
            : { elevation: 4 }),
    },
    ctaText: { fontFamily: fonts.sansSemiBold, fontSize: 16.5, color: INK, letterSpacing: 0.2 },
    skip: { marginTop: 18, alignItems: 'center' },
    skipText: { fontFamily: fonts.sans, fontSize: 14, color: SUB, textDecorationLine: 'underline' },
});
