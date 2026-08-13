/**
 * CreateAccountScreen — "Save your results". Sits between the locked scan results
 * and the referral/paywall screens (account-after-scan, Approach A). It CLAIMS the
 * anonymous account minted at "Get started" — sets a real email + password + name —
 * then routes to ReferralCode. A returning user who lands here gets a clear "email
 * already registered" error (they sign in from Landing instead).
 *
 * Visual: mirrors the paywall (Unlock your potential) — a dark, full-bleed canvas
 * with the SAME landing-hero avatar drifting behind a near-black gradient, a small
 * "ALMOST THERE" pill under a serif headline, glass input fields, and a white pill
 * CTA. The background image itself is unchanged; only the treatment went dark.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
    View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
    KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native';
import Animated, {
    Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming,
} from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { GoogleSignInButton } from '../../components/auth/GoogleSignInButton';
import { AppleSignInButton } from '../../components/auth/AppleSignInButton';
import { useAuth } from '../../context/AuthContext';
import { track } from '../../lib/analytics';
import { navigationRef } from '../../lib/navigationRef';

/* ── Dark cinematic palette — mirrors the paywall ─────────────────────────── */
const WHITE = '#FFFFFF';
const INK = '#0B0B0D';                       // near-black canvas
const HAIR = 'rgba(255,255,255,0.14)';
const HAIR_SOFT = 'rgba(255,255,255,0.08)';
const MUTED = 'rgba(255,255,255,0.58)';
const MUTED_SOFT = 'rgba(255,255,255,0.42)';
const FIELD = 'rgba(255,255,255,0.06)';
const ERR = '#FF6B5E';                        // legible red on dark
const IS_IOS = Platform.OS === 'ios';

// Same hero backdrop as the Landing screen (UNCHANGED) — now sitting behind a
// dark gradient so the claim step reads as part of the same cinematic funnel.
const HERO = require('../../assets/landing-hero.webp');

// The claim endpoint needs a unique username; the user doesn't pick one here, so
// derive a sane one from the email + a random suffix.
function deriveUsername(email: string): string {
    const base = (email.split('@')[0] || 'user').toLowerCase().replace(/[^a-z0-9_]/g, '').slice(0, 20) || 'user';
    const suffix = Math.floor(1000 + Math.random() * 9000);
    return `${base}_${suffix}`.slice(0, 30);
}

// FastAPI errors: `detail` is a string for our own HTTPExceptions but an ARRAY
// of {msg,...} for 422 validation errors — unpack both so the user sees the
// actual problem ("value is not a valid email address") instead of a generic one.
function claimErrorMessage(e: any): string {
    const detail = e?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg;
    return 'Could not save your account. Please try again.';
}

const ANON_EMAIL_SUFFIX = '@anon.trymax.app';

export default function CreateAccountScreen() {
    const nav = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { user, claimAccount, logout, refreshUser } = useAuth();
    // The anon account this screen is claiming — captured at mount so a Google
    // sign-in can tell a CLAIM (same id) from a switch to an existing account.
    const anonIdRef = useRef(user?.id);

    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // Chain the keyboard's Next/Go across the three fields.
    const emailRef = useRef<TextInput>(null);
    const passwordRef = useRef<TextInput>(null);

    const canSubmit = name.trim().length > 0 && /\S+@\S+\.\S+/.test(email.trim()) && password.length >= 8 && !busy;

    // Slow Ken-Burns drift on the hero (scale + a touch of pan), matching the
    // paywall so the screen reads as alive the instant it opens.
    const bgScale = useSharedValue(1);
    const bgX = useSharedValue(0);
    useEffect(() => {
        bgScale.value = withRepeat(withTiming(1.07, { duration: 9000, easing: Easing.inOut(Easing.sin) }), -1, true);
        bgX.value = withRepeat(withTiming(9, { duration: 12000, easing: Easing.inOut(Easing.sin) }), -1, true);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    const bgAnimatedStyle = useAnimatedStyle(() => ({
        transform: [{ scale: bgScale.value }, { translateX: bgX.value }],
    }));

    // Continue to the schedule questions. This screen lives in TWO stacks: the
    // funnel stack (which has 'Onboarding') and the main-app stack (reached when
    // an already-full user opens it from "unlock scan results" — that stack has
    // NO 'Onboarding' route). Navigating to a route the current navigator doesn't
    // know throws the "action REPLACE/NAVIGATE was not handled" error, so guard on
    // the registered route names and fall back to Main outside the funnel.
    //
    // RESET (not navigate/push) into the schedule phase: a plain navigate LEAVES
    // the pre-schedule funnel (Payment, CreateAccount) sitting in the back-stack,
    // so when the schedule phase finishes ("Build my day") and the navigator
    // remounts, that stale CreateAccount is what shows instead of Home. Resetting
    // to a single Onboarding(schedule) route clears the funnel history entirely.
    const continueToSchedule = (_mode: 'navigate' | 'replace' = 'navigate') => {
        const routeNames: string[] = ((nav.getState?.() as any)?.routeNames) ?? [];
        if (routeNames.includes('Onboarding')) {
            nav.reset({ index: 0, routes: [{ name: 'Onboarding', params: { phase: 'schedule' } }] });
        } else {
            nav.navigate('Main');
        }
    };

    // Funnel V4 resume-guard: this screen sits AFTER the paywall, and the account
    // may already be claimed on arrival — either a relaunch mid-funnel, OR (the
    // bug this fixes) when onboarding COMPLETES and the navigator remounts onto
    // the main stack carrying a stale CreateAccount route, which would show the
    // account form a SECOND time after the schedule questions. Captured on the
    // FIRST render so we can skip the form entirely (no flash) and redirect. A
    // fresh anon claiming ON this screen is initialClaimed=false, so the legit
    // first pass is untouched (its own goForward drives the hand-off).
    const initialClaimed = useRef<boolean | null>(null);
    if (initialClaimed.current === null) {
        initialClaimed.current = !!user && !String(user.email || '').endsWith(ANON_EMAIL_SUFFIX);
    }
    useEffect(() => {
        if (initialClaimed.current) continueToSchedule('replace');
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // After a successful claim (password OR Google), continue the funnel to the
    // schedule questions (funnel V4: paywall → account → schedule → Main).
    // Unlike the guest Login/Signup screens — which live in the unauthenticated
    // stack, so signing in there flips isAuthenticated and the navigator
    // remounts automatically — the anon user is ALREADY authenticated here, so
    // claiming changes no stack and we must navigate explicitly.
    const goForward = (method: 'email' | 'google' = 'email') => {
        track('onboarding_step', { step: 'account_created', method });
        continueToSchedule('navigate');
    };

    // A Google sign-in either CLAIMED the anon account (same user id — the normal
    // save-your-results path) or matched an EXISTING account and switched the
    // session to it. The two must route differently: a claim continues the funnel;
    // an existing account resumes wherever THAT account left off.
    const onGoogleSuccess = (u?: { id: string; is_paid?: boolean; onboarding?: { completed?: boolean } }) => {
        if (!u || u.id === anonIdRef.current) { goForward('google'); return; }
        track('onboarding_step', { step: 'signed_in_existing', method: 'google' });
        // Paid AND onboarded: treatAsFull flips, the navigator remounts onto
        // Main — any manual navigate here would race the remount. Do nothing.
        // Paid but onboarding INCOMPLETE (a V4 buyer who quit before finishing
        // the schedule questions, now signing back in): treatAsFull stays
        // false, so NO remount happens — a bare return would leave them parked
        // on this form with nothing occurring. Resume their onboarding instead,
        // clearing the anon funnel history like the unpaid branch below.
        if (u.is_paid) {
            if (u.onboarding?.completed !== true) {
                nav.reset({ index: 0, routes: [{ name: 'Onboarding' }] });
            }
            return;
        }
        // Unpaid but onboarded (legacy account): straight to the paywall.
        if (u.onboarding?.completed === true) { nav.navigate('Payment'); return; }
        // Unpaid, onboarding NOT done: run onboarding — clear the anon funnel
        // history so back-swipes can't resurface another account's scan results.
        nav.reset({ index: 0, routes: [{ name: 'Onboarding' }] });
    };

    const onSubmit = async () => {
        if (!canSubmit) return;
        setBusy(true); setError(null);
        try {
            // The username is auto-derived (user never sees it) — retry a couple of
            // times on a collision instead of surfacing "Username already taken"
            // for a name they never chose.
            for (let attempt = 0; ; attempt++) {
                try {
                    await claimAccount(email.trim(), password, name.trim(), '', deriveUsername(email.trim()));
                    break;
                } catch (e: any) {
                    if (e?.response?.data?.detail === 'Username already taken' && attempt < 2) continue;
                    throw e;
                }
            }
            goForward('email');
        } catch (e: any) {
            const message = claimErrorMessage(e);
            // "Already set up" can mean a PREVIOUS attempt succeeded but its
            // response was lost (timeout) — the account is claimed, we just never
            // heard back. If this session now owns a claimed account with the
            // entered email, that's exactly what happened: continue instead of
            // stranding the user on an error they can't act on.
            if (/already set up/i.test(message)) {
                try {
                    const u = await refreshUser();
                    if (u?.email && !u.email.endsWith(ANON_EMAIL_SUFFIX) && u.email.toLowerCase() === email.trim().toLowerCase()) {
                        goForward('email');
                        return;
                    }
                } catch { /* fall through to the error message */ }
            }
            setError(message);
        } finally {
            setBusy(false);
        }
    };

    // Returning user who tapped "Get started" by mistake: drop the throwaway anon
    // session and send them to sign in instead.
    const onSignInInstead = async () => {
        try { await logout(); } catch { /* fall through to Login regardless */ }
        // logout swaps to the unauthenticated stack; jump to Login once it's mounted.
        setTimeout(() => { if (navigationRef.isReady()) navigationRef.navigate('Login' as never); }, 350);
    };

    // Arrived already-claimed (post-onboarding remount / relaunch): never render
    // the account form — the effect above is redirecting us onward.
    if (initialClaimed.current) return null;

    return (
        <View style={styles.root}>
            {/* Landing-hero avatar (UNCHANGED), now Ken-Burns drifting behind a
                dark gradient — the same living-background treatment as the paywall. */}
            <Animated.Image source={HERO} style={[StyleSheet.absoluteFill, bgAnimatedStyle]} resizeMode="cover" />
            <LinearGradient
                pointerEvents="none"
                colors={['rgba(11,11,13,0.90)', 'rgba(11,11,13,0.42)', 'rgba(11,11,13,0.52)', 'rgba(11,11,13,0.96)']}
                locations={[0, 0.34, 0.62, 1]}
                style={StyleSheet.absoluteFill}
            />

            {/* Top bar — back chevron in a translucent chip (paywall style). */}
            <View style={[styles.topBar, { top: Math.max(insets.top + 8, 52) }]}>
                <TouchableOpacity style={styles.backChip} onPress={() => nav.goBack()} hitSlop={12} accessibilityLabel="Back" accessibilityRole="button">
                    <Ionicons name="chevron-back" size={20} color={WHITE} />
                </TouchableOpacity>
            </View>

            <KeyboardAvoidingView style={{ flex: 1 }} behavior={IS_IOS ? 'padding' : undefined}>
                <ScrollView
                    contentContainerStyle={[styles.content, { paddingTop: Math.max(insets.top + 76, 118), paddingBottom: Math.max(insets.bottom + 28, 44) }]}
                    keyboardShouldPersistTaps="handled"
                    showsVerticalScrollIndicator={false}
                >
                    {/* Headline + pill + sub — centered, mirroring the paywall. */}
                    <Text style={styles.title}>Save your <Text style={styles.titleItalic}>results</Text></Text>
                    <View style={styles.pill}>
                        <Text style={styles.pillText}>ALMOST THERE</Text>
                    </View>
                    <Text style={styles.sub}>Create your account to keep your scan and your plan.</Text>

                    <View style={styles.form}>
                        <TextInput
                            style={styles.input} value={name} onChangeText={setName}
                            placeholder="Your name" placeholderTextColor={MUTED_SOFT}
                            autoCapitalize="words" accessibilityLabel="Name"
                            textContentType="name" autoComplete="name"
                            returnKeyType="next" onSubmitEditing={() => emailRef.current?.focus()} blurOnSubmit={false}
                        />
                        <TextInput
                            ref={emailRef}
                            style={styles.input} value={email} onChangeText={setEmail}
                            placeholder="Email" placeholderTextColor={MUTED_SOFT}
                            autoCapitalize="none" autoCorrect={false} keyboardType="email-address"
                            accessibilityLabel="Email"
                            textContentType="emailAddress" autoComplete="email"
                            returnKeyType="next" onSubmitEditing={() => passwordRef.current?.focus()} blurOnSubmit={false}
                        />
                        <TextInput
                            ref={passwordRef}
                            style={styles.input} value={password} onChangeText={setPassword}
                            placeholder="Password (8+ characters)" placeholderTextColor={MUTED_SOFT}
                            secureTextEntry accessibilityLabel="Password"
                            textContentType="newPassword" autoComplete="new-password"
                            returnKeyType="go" onSubmitEditing={onSubmit}
                        />
                    </View>

                    {error ? <Text style={styles.err}>{error}</Text> : null}

                    {/* CTA — solid white pill (paywall's inverted-on-dark button). */}
                    <View style={[styles.ctaWrap, !canSubmit && styles.ctaDisabled]}>
                        <TouchableOpacity
                            style={styles.cta}
                            onPress={onSubmit} disabled={!canSubmit} activeOpacity={0.85} accessibilityRole="button"
                        >
                            {busy ? <ActivityIndicator color={INK} /> : <Text style={styles.ctaText}>Save & continue</Text>}
                        </TouchableOpacity>
                    </View>

                    <View style={styles.orRow}>
                        <View style={styles.orLine} />
                        <Text style={styles.orText}>OR</Text>
                        <View style={styles.orLine} />
                    </View>

                    <GoogleSignInButton label="Continue with Google" variant="glass" onAuthSuccess={onGoogleSuccess} />
                    <AppleSignInButton
                        label="Continue with Apple"
                        style={styles.apple}
                        textStyle={styles.appleText}
                        iconColor={WHITE}
                        onAuthSuccess={onGoogleSuccess}
                    />

                    <TouchableOpacity style={styles.signin} onPress={onSignInInstead} hitSlop={8} accessibilityRole="button">
                        <Text style={styles.signinText}>Already have an account? <Text style={styles.signinStrong}>Sign in</Text></Text>
                    </TouchableOpacity>

                    {/* Simulator-only: skip the account claim and continue the
                        funnel (the anon account stays anon). Never ships — __DEV__. */}
                    {__DEV__ ? (
                        <TouchableOpacity
                            style={styles.devSkip}
                            onPress={() => goForward('email')}
                            hitSlop={8}
                            accessibilityRole="button"
                            accessibilityLabel="Skip (dev)"
                        >
                            <Text style={styles.devSkipText}>DEV · Skip account →</Text>
                        </TouchableOpacity>
                    ) : null}
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: INK },

    topBar: {
        position: 'absolute',
        left: 20,
        right: 20,
        zIndex: 10,
        flexDirection: 'row',
        alignItems: 'center',
    },
    backChip: {
        backgroundColor: 'rgba(255,255,255,0.12)',
        borderRadius: 999,
        width: 34,
        height: 34,
        alignItems: 'center',
        justifyContent: 'center',
    },

    content: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: 24 },

    title: {
        fontFamily: 'Fraunces',
        fontSize: 34,
        color: WHITE,
        letterSpacing: -0.8,
        lineHeight: 38,
        textAlign: 'center',
    },
    titleItalic: { fontFamily: 'Fraunces-Italic', fontStyle: 'italic' },
    pill: {
        alignSelf: 'center',
        marginTop: 12,
        borderWidth: 1,
        borderColor: HAIR,
        borderRadius: 999,
        paddingHorizontal: 14,
        paddingVertical: 5,
    },
    pillText: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 11,
        color: WHITE,
        letterSpacing: 1.4,
    },
    sub: {
        fontFamily: 'Matter-Regular',
        fontSize: 15,
        color: MUTED,
        marginTop: 16,
        marginBottom: 26,
        lineHeight: 21,
        textAlign: 'center',
        paddingHorizontal: 8,
    },

    form: { gap: 10 },
    input: {
        height: 54,
        borderRadius: 14,
        borderCurve: 'continuous',
        paddingHorizontal: 16,
        backgroundColor: FIELD,
        borderWidth: 1,
        borderColor: HAIR_SOFT,
        color: WHITE,
        fontFamily: 'Matter-Regular',
        fontSize: 16,
    },
    err: {
        fontFamily: 'Matter-Regular',
        fontSize: 13.5,
        color: ERR,
        marginTop: 12,
        paddingHorizontal: 2,
        textAlign: 'center',
    },

    ctaWrap: {
        borderRadius: 999,
        borderCurve: 'continuous',
        marginTop: 22,
        ...(IS_IOS
            ? { shadowColor: '#000', shadowOpacity: 0.30, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } }
            : { elevation: 6 }),
    },
    cta: {
        height: 56,
        borderRadius: 999,
        borderCurve: 'continuous',
        backgroundColor: WHITE,
        alignItems: 'center',
        justifyContent: 'center',
    },
    ctaDisabled: { opacity: 0.45 },
    ctaText: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: INK, letterSpacing: 0.1 },

    orRow: { flexDirection: 'row', alignItems: 'center', marginTop: 22, marginBottom: 14, gap: 12 },
    orLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: HAIR },
    orText: { fontFamily: 'Matter-Regular', fontSize: 11, color: MUTED_SOFT, letterSpacing: 1.2 },

    apple: {
        marginTop: 10,
        height: 54,
        // Match GoogleSignInButton's glass variant so the two auth buttons are identical.
        borderRadius: 999,
        borderCurve: 'continuous',
        backgroundColor: 'rgba(255,255,255,0.14)',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.45)',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
    },
    appleText: { fontFamily: 'Matter-SemiBold', fontSize: 15, letterSpacing: 0.3, color: WHITE },

    signin: { marginTop: 20, alignItems: 'center' },
    signinText: { fontFamily: 'Matter-Regular', fontSize: 14, color: MUTED },
    signinStrong: { fontFamily: 'Matter-SemiBold', color: WHITE, textDecorationLine: 'underline' },

    devSkip: {
        marginTop: 14,
        alignSelf: 'center',
        paddingHorizontal: 14,
        paddingVertical: 7,
        borderRadius: 999,
        backgroundColor: 'rgba(255,255,255,0.10)',
    },
    devSkipText: { fontFamily: 'Matter-SemiBold', fontSize: 12, color: MUTED, letterSpacing: 0.4 },
});
