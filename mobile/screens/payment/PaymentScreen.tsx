/**
 * PaymentScreen — dark full-bleed paywall (Cosmos-style: near-black canvas,
 * a slow-moving photo background, a small animated mark, a bordered
 * checklist card, two side-by-side plan boxes, a white pill CTA).
 *
 * Layout: the same bust-dissolving-into-blue-smoke background (Higgsfield)
 * as before, now Ken-Burns animated (slow zoom + drift, Reanimated) so the
 * screen has motion the instant it opens — a dark gradient keeps text
 * legible over it. A small pulsing 6-dot ring sits above the headline.
 *
 * Single plan (funnel V4): Chad — 3-day free trial (Apple introductory
 * offer), then the SKU's period price. Both selector boxes run the same
 * StoreKit purchase (Apple applies the intro offer per eligibility); the
 * choice is presentation only. Hard paywall: no free tier entry point.
 */

import React, { useEffect, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Platform,
    ActivityIndicator,
} from 'react-native'
import Animated, {
    Easing,
    useAnimatedStyle,
    useSharedValue,
    withRepeat,
    withTiming,
    type SharedValue,
} from 'react-native-reanimated';
import { Alert } from '../../components/InAppAlert';
import { LinearGradient } from 'expo-linear-gradient';
const DUST = require('../../assets/paywall-dust.webp');
import { LiquidGlass } from '../../components/glass/LiquidGlass';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { track } from '../../lib/analytics';
import { useAuth } from '../../context/AuthContext';
import { useStripeSubscription } from '../../hooks/useStripeSubscription';
import { useAppleSubscription } from '../../hooks/useAppleSubscription';
import { APPLE_IAP_PREMIUM_SKU } from '../../constants/appleIap';
import { useFlag } from '../../constants/featureFlags';

/* ── Palette ── dark paywall (near-black, white ink, brand-blue accent) ── */
const WHITE   = '#FFFFFF';
const INK     = '#0B0B0D';                    // near-black base canvas
const HAIR    = 'rgba(255,255,255,0.14)';
const HAIR_SOFT = 'rgba(255,255,255,0.08)';
const MUTED   = 'rgba(255,255,255,0.58)';
const MUTED_SOFT = 'rgba(255,255,255,0.42)';

const IS_IOS = Platform.OS === 'ios';
const SHOW_DEV_BYPASS = __DEV__;

/* ── Feature rows per plan ──────────────────────────────────────────────── */
type Feature = { title: string; sub: string };

const CHAD_FEATURES: Feature[] = [
    { title: 'Max Chat Pro',        sub: 'Unlimited AI coaching conversations'          },
    { title: '3 Active Routines',   sub: 'Run up to 3 looksmaxxing programs at once'    },
    { title: 'Daily Face Scans',    sub: 'AI face analysis every single day'            },
    { title: 'Full Course Library', sub: 'Every creator course and piece of content'    },
    { title: 'Priority Support',    sub: 'Faster responses and dedicated help'          },
];
const CHAD_FEATURES_NO_SCAN: Feature[] = [
    { title: 'Max Chat Pro',        sub: 'Unlimited AI coaching conversations'          },
    { title: '3 Active Routines',   sub: 'Run up to 3 looksmaxxing programs at once'    },
    { title: 'Full Course Library', sub: 'Every creator course and piece of content'    },
    { title: 'Priority Support',    sub: 'Faster responses and dedicated help'          },
];
// Chad Lite is retired (funnel V4): one plan, one price, 3-day free trial.
// Existing Lite subscribers are grandfathered INTO Chad server-side.

/* ── Component ─────────────────────────────────────────────────────────── */
export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const insets     = useSafeAreaInsets();
    const { user, refreshUser, isAnonymous, isFreeTier } = useAuth();

    // Funnel V4: the paywall comes BEFORE account creation — anonymous users
    // purchase (Apple IAP is Apple-ID-scoped; the entitlement attaches to this
    // authed anon account) and claim the account on the next screen.
    const onboardingCompleted = user?.onboarding?.completed === true;

    useEffect(() => {
        track('paywall_view');
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const faceScanEnabled = useFlag('faceScan');
    const chadFeatures = faceScanEnabled ? CHAD_FEATURES : CHAD_FEATURES_NO_SCAN;

    const stripe = useStripeSubscription();
    const apple  = useAppleSubscription();
    const useAppleSim = !IS_IOS && __DEV__ && Platform.OS === 'web';
    const sub = IS_IOS || useAppleSim ? apple : stripe;

    const appleRestoring = 'restoring' in apple ? !!apple.restoring : false;
    const busy = sub.loading !== null || appleRestoring;

    const appleProducts: any[] = IS_IOS ? ((apple as any).products ?? []) : [];
    const priceFor = (sku: string, fallback: string): string => {
        const p = appleProducts.find((x) => (x?.productId ?? x?.id) === sku);
        return (p?.displayPrice || p?.localizedPrice || fallback) as string;
    };
    const premiumPrice = priceFor(APPLE_IAP_PREMIUM_SKU, '$5.99');

    // Free trial is the default; the user can opt to subscribe immediately.
    // Both run the SAME StoreKit purchase — Apple applies the 3-day intro
    // offer to eligible accounts either way — so this is a presentation
    // choice, not two different SKUs.
    const [payNow, setPayNow] = useState(false);

    // Slow Ken Burns drift on the background image (scale + a touch of
    // horizontal pan), so the screen has motion the instant it opens — the
    // SAME art as before, just no longer static.
    const bgScale = useSharedValue(1);
    const bgX = useSharedValue(0);
    useEffect(() => {
        bgScale.value = withRepeat(
            withTiming(1.07, { duration: 9000, easing: Easing.inOut(Easing.sin) }),
            -1, true,
        );
        bgX.value = withRepeat(
            withTiming(9, { duration: 12000, easing: Easing.inOut(Easing.sin) }),
            -1, true,
        );
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    const bgAnimatedStyle = useAnimatedStyle(() => ({
        transform: [{ scale: bgScale.value }, { translateX: bgX.value }],
    }));

    // Drives the small pulsing dot-ring mark above the headline.
    const dotT = useSharedValue(0);
    useEffect(() => {
        dotT.value = withRepeat(withTiming(1, { duration: 1800, easing: Easing.linear }), -1, false);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Where a successful purchase goes. Mid-funnel (onboarding incomplete) the
    // next step is claiming the account ("Save your results"); a completed user
    // hitting this as an in-app gate rides the paid-stack remount instead.
    const afterPurchase = () => {
        if (!onboardingCompleted) {
            navigation.navigate('CreateAccount');
        } else if (navigation.canGoBack()) {
            navigation.goBack();
        }
    };

    const [devBusy, setDevBusy] = useState<'premium' | null>(null);
    const devBypass = async () => {
        if (devBusy) return;
        setDevBusy('premium');
        try {
            await api.testActivateSubscription('premium');
            await refreshUser();
            afterPurchase();
        } catch (e: any) {
            Alert.alert('Dev bypass failed', String(e?.message || e || 'Could not activate.'));
        } finally {
            setDevBusy(null);
        }
    };

    const handleRestore = async () => {
        if (!IS_IOS || busy) return;
        try {
            await apple.restorePurchases();
            await refreshUser();
        } catch (error: any) {
            Alert.alert('Restore failed', String(error?.message || 'Could not restore.'));
        }
    };

    const handleSubscribe = async () => {
        // In any dev build (__DEV__) the primary CTA activates the plan directly.
        // Production builds run the real Apple IAP purchase — the 3-day free
        // trial is Apple's introductory offer on the Chad SKU, so "subscribe
        // free now, auto-converts to paid" needs no second opt-in from the user.
        track('purchase_started', { plan: 'premium' });
        if (SHOW_DEV_BYPASS) {
            await devBypass();
            return;
        }
        try {
            // subscribePremium resolves TRUE only for a verified entitlement.
            // A cancelled or failed purchase resolves FALSE and must leave the
            // user right here on the paywall — never forward into account
            // creation. (The hooks' own error paths surface the alert.)
            const purchased = await sub.subscribePremium();
            if (!purchased) {
                track('purchase_not_completed', { plan: 'premium' });
                return;
            }
            track('purchase_success', { plan: 'premium' });
            afterPurchase();
        } catch (e: any) {
            track('purchase_failed', { plan: 'premium', error: String(e?.message ?? 'unknown') });
            throw e;
        }
    };

    const ctaBusy = busy || devBusy !== null;
    const ctaLabel = ctaBusy
        ? 'Processing…'
        : payNow ? 'Subscribe now' : 'Start my 3-day free trial';

    // The free tier is RETIRED as an entry point (hard paywall: trial or
    // subscribe). chooseFreeTier stays in AuthContext only so accounts that
    // already chose it keep working; the close chip below still lets them
    // dismiss a gate-pushed paywall.

    return (
        <View style={s.root}>
            {/* ── Full-bleed animated background ── the same bust/smoke art as
                before, now Ken-Burns drifting (scale + pan) so the screen reads
                as alive the instant it opens. A dark gradient (near-black,
                heaviest at top and bottom) keeps text legible while letting
                the photo read through the middle — the Cosmos look. ──────── */}
            <Animated.Image source={DUST} style={[StyleSheet.absoluteFill, bgAnimatedStyle]} resizeMode="cover" />
            <LinearGradient
                pointerEvents="none"
                colors={['rgba(11,11,13,0.86)', 'rgba(11,11,13,0.30)', 'rgba(11,11,13,0.40)', 'rgba(11,11,13,0.94)']}
                locations={[0, 0.32, 0.60, 1]}
                style={StyleSheet.absoluteFill}
            />

            {/* ── Top bar — X close (left) / Restore (right), Cosmos-style ── */}
            <View style={[s.topBar, { top: Math.max(insets.top + 8, 52) }]}>
                {SHOW_DEV_BYPASS ? (
                    <TouchableOpacity style={s.topChip} onPress={afterPurchase} activeOpacity={0.7} hitSlop={12}>
                        <Text style={s.topChipText}>Skip payment</Text>
                    </TouchableOpacity>
                ) : isFreeTier && navigation.canGoBack() ? (
                    <TouchableOpacity
                        style={s.close}
                        onPress={() => navigation.goBack()}
                        activeOpacity={0.7}
                        hitSlop={12}
                        accessibilityRole="button"
                        accessibilityLabel="Close"
                    >
                        <Ionicons name="close" size={18} color={WHITE} />
                    </TouchableOpacity>
                ) : <View />}

                {/* Apple requires a working Restore control (Guideline 3.1.1). */}
                {IS_IOS && (
                    <TouchableOpacity onPress={handleRestore} disabled={busy} hitSlop={10} activeOpacity={0.7}>
                        <Text style={s.topRestoreText}>{appleRestoring ? 'Restoring…' : 'Restore'}</Text>
                    </TouchableOpacity>
                )}
            </View>

            {/* ── Content column ───────────────────────────────────── */}
            <View style={[s.content, { paddingTop: Math.max(insets.top + 56, 100), paddingBottom: Math.max(insets.bottom + 20, 36) }]}>

                <PulseDotRing t={dotT} />

                {/* Title — sits just below the mark, no dead space */}
                <Text style={s.title}>Unlock your <Text style={s.titleI}>potential</Text></Text>
                <View style={s.proPill}>
                    <Text style={s.proPillText}>PREMIUM</Text>
                </View>

                {/* Feature checklist — flat bordered card over the photo bg,
                    uniform checkmarks (Cosmos convention) instead of per-feature
                    icons. LiquidGlass at low intensity gives it a touch of depth
                    without the full frosted-glass look. */}
                <LiquidGlass dark radius={22} intensity={IS_IOS ? 24 : 10} spec={0.7} style={s.featureCard} contentStyle={s.featureCardContent}>
                    {chadFeatures.map((f, i) => (
                        <View key={f.title} style={[s.featureRow, i > 0 && s.featureRowDivider]}>
                            <View style={s.featureCheck}>
                                <Ionicons name="checkmark" size={13} color={WHITE} />
                            </View>
                            <View style={s.featureText}>
                                <Text style={s.featureTitle}>{f.title}</Text>
                                <Text style={s.featureSub}>{f.sub}</Text>
                            </View>
                        </View>
                    ))}
                </LiquidGlass>

                {/* Plan choice — two side-by-side boxes (Cosmos's Monthly/Annual
                    shape), free trial default / subscribe now. The selected box
                    carries the price + period (Apple requires it visible by the
                    CTA); both boxes run the same purchase. */}
                <View style={s.planRow}>
                    <PlanBox
                        selected={!payNow}
                        onPress={() => setPayNow(false)}
                        title="3-day trial"
                        price="Free"
                        sub={`then ${premiumPrice}/wk`}
                    />
                    <PlanBox
                        selected={payNow}
                        onPress={() => setPayNow(true)}
                        title="Subscribe now"
                        price={`${premiumPrice}/wk`}
                        sub="start today"
                    />
                </View>

                {/* CTA — solid white pill (Cosmos's inverted-on-dark button). */}
                <View style={[s.ctaWrap, ctaBusy && s.ctaDisabled]}>
                    <TouchableOpacity
                        style={s.cta}
                        onPress={handleSubscribe}
                        disabled={ctaBusy}
                        activeOpacity={0.85}
                    >
                        {ctaBusy
                            ? <ActivityIndicator color={INK} />
                            : <Text style={s.ctaText}>{ctaLabel}</Text>
                        }
                    </TouchableOpacity>
                </View>

                {/* The one line a hesitant thumb needs to hear, right under the CTA. */}
                <Text style={s.noPaymentNote}>
                    {payNow ? 'Cancel anytime in Settings' : 'No payment due today · cancel anytime'}
                </Text>

                {/* Legal footer */}
                <View style={s.legalRow}>
                    <TouchableOpacity onPress={() => navigation.navigate('LegalDocument', { document: 'terms' })} hitSlop={8} activeOpacity={0.7}>
                        <Text style={s.legalLink}>Terms of Service</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => navigation.navigate('LegalDocument', { document: 'privacy' })} hitSlop={8} activeOpacity={0.7}>
                        <Text style={s.legalLink}>Privacy Policy</Text>
                    </TouchableOpacity>
                </View>

            </View>
        </View>
    );
}

/* ── Pulsing dot ring (Cosmos-style animated mark) ───────────────────────── */
function PulseDotRing({ t }: { t: SharedValue<number> }) {
    return (
        <View style={s.dotRing}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
                <PulseDot key={i} t={t} index={i} />
            ))}
        </View>
    );
}
function PulseDot({ t, index }: { t: SharedValue<number>; index: number }) {
    const angle = (index / 6) * Math.PI * 2;
    const radius = 13;
    const dx = Math.cos(angle) * radius;
    const dy = Math.sin(angle) * radius;
    const style = useAnimatedStyle(() => {
        const phase = t.value * Math.PI * 2 + index * (Math.PI / 3);
        const opacity = 0.28 + 0.72 * ((Math.sin(phase) + 1) / 2);
        return { opacity, transform: [{ translateX: dx }, { translateY: dy }] };
    });
    return <Animated.View style={[s.dot, style]} />;
}

/* ── Plan box (free trial / subscribe now) ───────────────────────────────── */
function PlanBox({ selected, onPress, title, price, sub }: {
    selected: boolean; onPress: () => void; title: string; price: string; sub: string;
}) {
    return (
        <TouchableOpacity
            style={[s.planBox, selected && s.planBoxSel]}
            onPress={onPress}
            activeOpacity={0.85}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            accessibilityLabel={`${title}, ${price} ${sub}`}
        >
            {selected ? (
                <View style={s.planCheck}>
                    <Ionicons name="checkmark" size={12} color={INK} />
                </View>
            ) : null}
            <Text style={s.planBoxLabel}>{title}</Text>
            <Text style={s.planBoxPrice}>{price}</Text>
            <Text style={s.planBoxSub}>{sub}</Text>
        </TouchableOpacity>
    );
}

/* ── Styles ──────────────────────────────────────────────────────────── */
const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: INK },

    topBar: {
        position: 'absolute',
        left: 20,
        right: 20,
        zIndex: 10,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    topChip: {
        backgroundColor: 'rgba(255,255,255,0.12)',
        borderRadius: 999,
        paddingHorizontal: 14,
        paddingVertical: 6,
    },
    topChipText: {
        fontFamily: 'Matter-Medium',
        fontSize: 14,
        color: WHITE,
        letterSpacing: 0.2,
    },
    topRestoreText: {
        fontFamily: 'Matter-Medium',
        fontSize: 13.5,
        color: MUTED,
        letterSpacing: 0.1,
    },

    /* free-tier gate close chip */
    close: {
        backgroundColor: 'rgba(255,255,255,0.12)',
        borderRadius: 999,
        width: 32,
        height: 32,
        alignItems: 'center',
        justifyContent: 'center',
    },

    /* pulsing dot-ring mark */
    dotRing: {
        width: 30, height: 30,
        alignSelf: 'center',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 14,
    },
    dot: {
        position: 'absolute',
        width: 5, height: 5, borderRadius: 2.5,
        backgroundColor: WHITE,
    },

    /* "no payment due" reassurance under the CTA */
    noPaymentNote: {
        alignSelf: 'center',
        marginTop: 10,
        fontFamily: 'Matter-Medium',
        fontSize: 13,
        color: MUTED,
        letterSpacing: 0.1,
    },

    /* plan choice — two side-by-side boxes, Cosmos style */
    planRow: { flexDirection: 'row', gap: 10 },
    planBox: {
        flex: 1,
        backgroundColor: 'rgba(255,255,255,0.05)',
        borderRadius: 16,
        borderCurve: 'continuous',
        borderWidth: 1,
        borderColor: HAIR_SOFT,
        paddingVertical: 14,
        paddingHorizontal: 14,
    },
    planBoxSel: {
        backgroundColor: 'rgba(255,255,255,0.09)',
        borderColor: 'rgba(255,255,255,0.55)',
    },
    planCheck: {
        position: 'absolute',
        top: 10, right: 10,
        width: 20, height: 20, borderRadius: 10,
        backgroundColor: WHITE,
        alignItems: 'center', justifyContent: 'center',
    },
    planBoxLabel: { fontFamily: 'Matter-Medium', fontSize: 12.5, color: MUTED, letterSpacing: 0.1 },
    planBoxPrice: { fontFamily: 'Matter-SemiBold', fontSize: 19, color: WHITE, letterSpacing: -0.3, marginTop: 5 },
    planBoxSub: { fontFamily: 'Matter-Regular', fontSize: 11.5, color: MUTED_SOFT, marginTop: 2 },

    content: {
        flex: 1,
        paddingHorizontal: 20,
        gap: 8,
    },

    title: {
        fontFamily: 'Fraunces',
        fontSize: 32,
        color: WHITE,
        letterSpacing: -0.8,
        lineHeight: 36,
        textAlign: 'center',
        marginTop: 2,
    },
    titleI: {
        fontFamily: 'Fraunces-Italic',
        fontStyle: 'italic',
    },
    proPill: {
        alignSelf: 'center',
        marginTop: 10,
        marginBottom: 22,
        borderWidth: 1,
        borderColor: HAIR,
        borderRadius: 999,
        paddingHorizontal: 14,
        paddingVertical: 5,
    },
    proPillText: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 11,
        color: WHITE,
        letterSpacing: 1.4,
    },

    /* feature checklist card */
    featureCard: {
        flex: 1,
    },
    featureCardContent: {
        flex: 1,
        paddingHorizontal: 18,
        paddingVertical: 6,
    },
    featureRow: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 13,
    },
    featureRowDivider: {
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: HAIR_SOFT,
    },
    featureCheck: {
        width: 24,
        height: 24,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: HAIR,
        alignItems: 'center',
        justifyContent: 'center',
    },
    featureText: { flex: 1 },
    featureTitle: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 14.5,
        color: WHITE,
        letterSpacing: -0.1,
    },
    featureSub: {
        fontFamily: 'Matter-Regular',
        fontSize: 12,
        color: MUTED,
        marginTop: 2,
        lineHeight: 16,
    },

    /* CTA — solid white pill pops on the dark canvas */
    ctaWrap: {
        borderRadius: 999,
        borderCurve: 'continuous',
        marginTop: 4,
        ...(IS_IOS
            ? { shadowColor: '#000', shadowOpacity: 0.30, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } }
            : { elevation: 6 }),
    },
    cta: {
        borderRadius: 999,
        borderCurve: 'continuous',
        height: 56,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: WHITE,
    },
    ctaDisabled: { opacity: 0.5 },
    ctaText: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 16,
        color: INK,
        letterSpacing: 0.1,
    },

    /* legal */
    legalRow: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 14,
    },
    legalLink: {
        fontFamily: 'Matter-Regular',
        fontSize: 11,
        color: MUTED_SOFT,
        textDecorationLine: 'underline',
    },
});
