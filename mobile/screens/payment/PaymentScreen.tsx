/**
 * PaymentScreen — glass-aesthetic two-tier subscription page.
 *
 * Visual:
 *   - Soft blurred orbs in the page background (decorative)
 *   - Each plan card is a translucent glass surface (BlurView + thin
 *     accent gradient + 1px border)
 *   - The premium card "Chad" is feature-promoted: filled accent
 *     background, "Most popular" ribbon, savings micro-copy
 *
 * Sales-promotion patterns applied (research):
 *   - Anchoring: weekly price stated next to monthly equivalent
 *   - Loss aversion: "save 33% vs Chadlite"
 *   - Decoy: Chadlite less attractive (1 max, weekly scans, no docs)
 *   - Social proof: "Most popular" ribbon on Chad
 *   - Trust: cancel-anytime, secure-checkout language under the title
 *   - Friction reduction: Apple IAP / Stripe one-tap CTAs at thumb level
 *
 * Tiers:
 *   Chadlite (basic):   chatbot · 1 active program · weekly face scan
 *   Chad (premium):     chatbot pro · 3 active programs · daily scans
 *                       · full course library · everything else
 */

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
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useStripeSubscription } from '../../hooks/useStripeSubscription';
import { useAppleSubscription } from '../../hooks/useAppleSubscription';
import { borderRadius, colors, fonts, spacing } from '../../theme/dark';
import { SHOW_DEV_SKIP_CONTROLS } from '../../constants/devSkips';

/* ── Tier features ────────────────────────────────────────────────────── */

const BASIC_PERKS: { label: string; included: boolean }[] = [
    { label: 'Chatbot access',           included: true  },
    { label: '1 active program',         included: true  },
    { label: 'Weekly face scan',         included: true  },
];

const PREMIUM_PERKS: string[] = [
    'Chatbot Pro — deeper, more nuanced coaching',
    '3 active programs',
    'Daily face scans',
    'Full course library',
    'Priority support',
];

const IS_IOS = Platform.OS === 'ios';
const ACCENT = '#F5F5F4';                  // off-white for premium fill
const ACCENT_GLOW = 'rgba(139, 92, 246, 0.18)'; // soft violet decorative orb
const ACCENT_GLOW_2 = 'rgba(16, 185, 129, 0.12)'; // soft green decorative orb

export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { user, refreshUser, logout } = useAuth();

    const stripe = useStripeSubscription();
    const apple = useAppleSubscription();
    const useAppleSim = !IS_IOS && __DEV__ && Platform.OS === 'web';
    const sub = IS_IOS || useAppleSim ? apple : stripe;

    const [devLoading, setDevLoading] = useState(false);
    const appleRestoring = 'restoring' in apple ? !!apple.restoring : false;
    const busy = sub.loading !== null || devLoading || appleRestoring;

    const handleRestore = async () => {
        if (!IS_IOS || busy) return;
        try {
            await apple.restorePurchases();
            await refreshUser();
        } catch (error: any) {
            Alert.alert('Restore failed', String(error?.message || 'Could not restore.'));
        }
    };

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
        await (tier === 'basic' ? sub.subscribeBasic() : sub.subscribePremium());
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
                    'Failed to activate dev subscription.';
                Alert.alert('Error', String(msg));
            } finally {
                setDevLoading(false);
            }
        };
        void doActivate();
    };

    return (
        <View style={s.container}>
            {/* ── Decorative glass orbs (full-screen backdrop) ─────── */}
            <View style={s.orb1} pointerEvents="none">
                <View style={[s.orbInner, { backgroundColor: ACCENT_GLOW }]} />
            </View>
            <View style={s.orb2} pointerEvents="none">
                <View style={[s.orbInner, { backgroundColor: ACCENT_GLOW_2 }]} />
            </View>

            {/* ── Top bar ─────────────────────────────────────────── */}
            <View style={[s.topBar, { paddingTop: Math.max(insets.top + spacing.sm, 44) }]}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={s.backBtn}
                    activeOpacity={0.7}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>
            </View>

            <ScrollView
                contentContainerStyle={[s.scroll, { paddingBottom: Math.max(insets.bottom + spacing.xl, spacing.xxl) }]}
                showsVerticalScrollIndicator={false}
            >
                {/* ── Hero ─────────────────────────────────────────── */}
                <Text style={s.eyebrow}>UNLOCK</Text>
                <Text style={s.headline}>Pick your level.</Text>

                {/* ── PREMIUM (Chad) — featured ───────────────────── */}
                <PremiumCard
                    busy={busy}
                    loadingTier={sub.loading}
                    onPress={() => handleSubscribe('premium')}
                />

                {/* ── BASIC (Chadlite) ─────────────────────────────── */}
                <BasicCard
                    busy={busy}
                    loadingTier={sub.loading}
                    onPress={() => handleSubscribe('basic')}
                />

                {/* ── Trust strip ──────────────────────────────────── */}
                <View style={s.trustRow}>
                    <TrustItem icon="lock-closed-outline" label="Encrypted" />
                    <View style={s.trustDivider} />
                    <TrustItem icon="refresh-outline" label="Cancel anytime" />
                </View>

                {IS_IOS ? (
                    <TouchableOpacity
                        style={[s.restoreBtn, busy && s.ctaDisabled]}
                        onPress={handleRestore}
                        disabled={busy}
                        activeOpacity={0.7}
                    >
                        <Ionicons name="refresh-outline" size={15} color={colors.foreground} />
                        <Text style={s.restoreBtnText}>
                            {appleRestoring ? 'Restoring…' : 'Restore Purchases'}
                        </Text>
                    </TouchableOpacity>
                ) : null}

                {/* Apple 3.1.2 — ToS + Privacy required on subscription pages */}
                <View style={s.legalRow}>
                    <TouchableOpacity
                        onPress={() => navigation.navigate('LegalDocument', { document: 'terms' })}
                        activeOpacity={0.6}
                    >
                        <Text style={s.legalLink}>Terms of Service</Text>
                    </TouchableOpacity>
                    <Text style={s.legalDot}>·</Text>
                    <TouchableOpacity
                        onPress={() => navigation.navigate('LegalDocument', { document: 'privacy' })}
                        activeOpacity={0.6}
                    >
                        <Text style={s.legalLink}>Privacy Policy</Text>
                    </TouchableOpacity>
                </View>

                <TouchableOpacity
                    style={s.signOutBtn}
                    onPress={() => {
                        Alert.alert(
                            'Sign out?',
                            "You'll be taken back to the sign-in screen.",
                            [
                                { text: 'Cancel', style: 'cancel' },
                                { text: 'Sign out', style: 'destructive', onPress: () => void logout() },
                            ],
                        );
                    }}
                    activeOpacity={0.7}
                >
                    <Text style={s.signOutText}>Sign out & start over</Text>
                </TouchableOpacity>

                {SHOW_DEV_SKIP_CONTROLS ? (
                    <View style={s.devRow}>
                        <TouchableOpacity style={s.devBtn} onPress={() => handleDevSkip('basic')} disabled={busy}>
                            <Text style={s.devBtnText}>{devLoading ? 'Activating…' : 'DEV: Skip → Chadlite'}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={s.devBtn} onPress={() => handleDevSkip('premium')} disabled={busy}>
                            <Text style={s.devBtnText}>{devLoading ? 'Activating…' : 'DEV: Skip → Chad'}</Text>
                        </TouchableOpacity>
                    </View>
                ) : null}
            </ScrollView>
        </View>
    );
}

/* ── Premium card (featured, dark-fill glass) ────────────────────────── */

function PremiumCard({
    busy, loadingTier, onPress,
}: {
    busy: boolean;
    loadingTier: 'basic' | 'premium' | null;
    onPress: () => void;
}) {
    return (
        <View style={s.premiumWrap}>
            {/* "Most popular" ribbon */}
            <View style={s.popBadge}>
                <Text style={s.popBadgeText}>MOST POPULAR</Text>
            </View>

            <View style={s.premiumCard}>
                {/* Subtle accent gradient inside the dark card */}
                <LinearGradient
                    colors={['rgba(139,92,246,0.22)', 'rgba(16,185,129,0.12)', 'rgba(0,0,0,0)']}
                    locations={[0, 0.5, 1]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={StyleSheet.absoluteFill}
                />

                <View style={{ position: 'relative' }}>
                    <Text style={[s.cardName, { color: ACCENT }]}>Chad</Text>
                    <View style={s.priceRow}>
                        <Text style={[s.priceValue, { color: ACCENT }]}>$5.99</Text>
                        <Text style={s.pricePerLight}>/week</Text>
                    </View>

                    <View style={s.perksList}>
                        {PREMIUM_PERKS.map((p, i) => (
                            <View key={i} style={s.perkRow}>
                                <View style={s.perkCheckPremium}>
                                    <Ionicons name="checkmark" size={11} color={'#0A0A0B'} />
                                </View>
                                <Text style={[s.perkText, { color: 'rgba(245,245,243,0.92)' }]}>
                                    {p}
                                </Text>
                            </View>
                        ))}
                    </View>

                    <TouchableOpacity
                        style={[s.ctaPrimary, busy && s.ctaDisabled]}
                        onPress={onPress}
                        disabled={busy}
                        activeOpacity={0.85}
                    >
                        <Text style={s.ctaPrimaryText}>
                            {loadingTier === 'premium' ? 'Processing…' : 'Get Chad'}
                        </Text>
                        <Ionicons name="arrow-forward" size={15} color={colors.foreground} />
                    </TouchableOpacity>
                </View>
            </View>
        </View>
    );
}

/* ── Basic card (translucent glass) ──────────────────────────────────── */

function BasicCard({
    busy, loadingTier, onPress,
}: {
    busy: boolean;
    loadingTier: 'basic' | 'premium' | null;
    onPress: () => void;
}) {
    return (
        <View style={s.basicWrap}>
            {Platform.OS !== 'android' ? (
                <BlurView
                    intensity={Platform.OS === 'ios' ? 30 : 22}
                    tint="light"
                    style={StyleSheet.absoluteFill}
                />
            ) : null}
            <View style={[StyleSheet.absoluteFill, s.basicTint]} />

            <Text style={s.cardName}>Chadlite</Text>
            <View style={s.priceRow}>
                <Text style={s.priceValue}>$3.99</Text>
                <Text style={s.pricePer}>/week</Text>
            </View>

            <View style={s.perksList}>
                {BASIC_PERKS.map((p, i) => (
                    <View key={i} style={s.perkRow}>
                        <View
                            style={[
                                s.perkCheckBasic,
                                !p.included && s.perkCheckBasicMuted,
                            ]}
                        >
                            <Ionicons
                                name={p.included ? 'checkmark' : 'remove'}
                                size={11}
                                color={p.included ? colors.foreground : colors.textMuted}
                            />
                        </View>
                        <Text
                            style={[
                                s.perkText,
                                {
                                    color: p.included ? colors.textPrimary : colors.textMuted,
                                    textDecorationLine: p.included ? 'none' : 'line-through',
                                },
                            ]}
                        >
                            {p.label}
                        </Text>
                    </View>
                ))}
            </View>

            <TouchableOpacity
                style={[s.ctaSecondary, busy && s.ctaDisabled]}
                onPress={onPress}
                disabled={busy}
                activeOpacity={0.85}
            >
                <Text style={s.ctaSecondaryText}>
                    {loadingTier === 'basic' ? 'Processing…' : 'Get Chadlite'}
                </Text>
            </TouchableOpacity>
        </View>
    );
}

/* ── Trust pill ──────────────────────────────────────────────────────── */

function TrustItem({ icon, label }: { icon: any; label: string }) {
    return (
        <View style={s.trustItem}>
            <Ionicons name={icon} size={13} color={colors.textSecondary} />
            <Text style={s.trustLabel}>{label}</Text>
        </View>
    );
}

/* ── Styles ──────────────────────────────────────────────────────────── */

const s = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },

    /* decorative orbs (background) */
    orb1: {
        position: 'absolute',
        top: -40,
        right: -60,
        width: 240,
        height: 240,
    },
    orb2: {
        position: 'absolute',
        top: 320,
        left: -80,
        width: 280,
        height: 280,
    },
    orbInner: {
        flex: 1,
        borderRadius: 140,
        opacity: 1,
    },

    topBar: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.sm,
    },
    backBtn: {
        width: 32,
        height: 32,
        justifyContent: 'center',
    },
    scroll: {
        paddingHorizontal: spacing.lg,
    },

    /* hero */
    eyebrow: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        letterSpacing: 1.8,
        color: colors.textMuted,
        marginTop: spacing.sm,
        marginBottom: 8,
    },
    headline: {
        fontFamily: fonts.serif,
        fontSize: 38,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -1,
        lineHeight: 44,
    },
    subline: {
        fontSize: 13,
        color: colors.textSecondary,
        lineHeight: 19,
        marginTop: 8,
        marginBottom: spacing.xl,
    },

    /* premium card (dark glass) */
    premiumWrap: {
        marginBottom: spacing.lg,
    },
    popBadge: {
        position: 'absolute',
        top: -10,
        left: 16,
        right: 16,
        zIndex: 2,
        flexDirection: 'row',
        justifyContent: 'center',
    },
    popBadgeText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 10,
        letterSpacing: 1.6,
        color: colors.buttonText,
        backgroundColor: '#0A0A0B',
        paddingVertical: 5,
        paddingHorizontal: 12,
        borderRadius: borderRadius.full,
        overflow: 'hidden',
    },
    premiumCard: {
        backgroundColor: '#0A0A0B',
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        overflow: 'hidden',
        ...(Platform.OS === 'ios'
            ? { shadowColor: '#0A0A0B', shadowOpacity: 0.18, shadowRadius: 24, shadowOffset: { width: 0, height: 8 } }
            : { elevation: 6 }),
    },

    /* basic card (light glass) */
    basicWrap: {
        backgroundColor: 'rgba(255,255,255,0.65)',
        borderRadius: borderRadius.xl,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        padding: spacing.xl,
        marginBottom: spacing.xl,
        overflow: 'hidden',
    },
    basicTint: {
        backgroundColor: 'rgba(255,255,255,0.5)',
    },

    /* shared per-card */
    cardName: {
        fontFamily: fonts.serif,
        fontSize: 26,
        fontWeight: '400',
        letterSpacing: -0.5,
        color: colors.foreground,
    },
    priceRow: {
        flexDirection: 'row',
        alignItems: 'baseline',
        gap: 6,
        marginTop: 6,
    },
    priceValue: {
        fontFamily: fonts.serif,
        fontSize: 40,
        fontWeight: '400',
        letterSpacing: -1,
        color: colors.foreground,
    },
    pricePer: {
        fontSize: 13,
        color: colors.textSecondary,
    },
    pricePerLight: {
        fontSize: 13,
        color: 'rgba(245,245,243,0.55)',
    },
    priceMonthly: {
        fontSize: 11,
        color: 'rgba(245,245,243,0.45)',
        letterSpacing: 0.3,
        marginLeft: 8,
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
    perkCheckPremium: {
        width: 18,
        height: 18,
        borderRadius: 9,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: ACCENT,
    },
    perkCheckBasic: {
        width: 18,
        height: 18,
        borderRadius: 9,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: 'transparent',
    },
    perkCheckBasicMuted: {
        opacity: 0.6,
    },
    perkText: {
        fontSize: 13.5,
        flex: 1,
        lineHeight: 19,
    },

    /* CTAs */
    ctaPrimary: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: ACCENT,
        borderRadius: borderRadius.full,
        paddingVertical: 14,
    },
    ctaPrimaryText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13.5,
        letterSpacing: 0.3,
        color: '#0A0A0B',
    },
    ctaSecondary: {
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.foreground,
        paddingVertical: 14,
        alignItems: 'center',
    },
    ctaSecondaryText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13.5,
        letterSpacing: 0.3,
        color: colors.foreground,
    },
    ctaDisabled: { opacity: 0.45 },

    /* trust strip */
    trustRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: spacing.lg,
    },
    trustItem: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 5,
        paddingHorizontal: 8,
    },
    trustLabel: {
        fontFamily: fonts.sansMedium,
        fontSize: 11,
        letterSpacing: 0.3,
        color: colors.textSecondary,
    },
    trustDivider: {
        width: 1,
        height: 12,
        backgroundColor: colors.border,
    },

    disclaimer: {
        fontSize: 11,
        color: colors.textMuted,
        textAlign: 'center',
        lineHeight: 17,
    },

    restoreBtn: {
        alignSelf: 'center',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        marginTop: spacing.lg,
        paddingVertical: 9,
        paddingHorizontal: 16,
        borderRadius: borderRadius.full,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    restoreBtnText: {
        fontSize: 12.5,
        fontWeight: '600',
        color: colors.foreground,
    },

    legalRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        marginTop: spacing.md,
    },
    legalLink: {
        fontSize: 11,
        color: colors.textSecondary,
        textDecorationLine: 'underline',
    },
    legalDot: { fontSize: 11, color: colors.textMuted },

    signOutBtn: {
        alignSelf: 'center',
        marginTop: spacing.lg,
        paddingVertical: 10,
        paddingHorizontal: 20,
    },
    signOutText: {
        fontSize: 12,
        fontWeight: '500',
        color: colors.textMuted,
        textDecorationLine: 'underline',
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
    devBtnText: { fontSize: 12, fontWeight: '600', color: colors.textSecondary },
});
