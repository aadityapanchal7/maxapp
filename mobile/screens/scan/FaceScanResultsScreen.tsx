import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    Platform,
    Animated,
    LayoutChangeEvent,
    Share,
    Alert,
    AppState,
    BackHandler,
} from 'react-native';
import * as MediaLibrary from 'expo-media-library';
import * as Sharing from 'expo-sharing';
import { captureRef } from 'react-native-view-shot';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { BlurView } from 'expo-blur';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { CachedImage } from '../../components/CachedImage';
import { userHasSignupPhone } from '../../utils/userPhone';
import { getMaxxDisplayLabel } from '../../utils/maxxDisplay';

function formatSuggestedModuleTitle(id: string): string {
    const t = getMaxxDisplayLabel({ id }).trim();
    if (!t) return id;
    return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Some DB drivers or legacy rows store analysis as a JSON string. */
function coerceAnalysisObject(analysis: unknown): any {
    if (analysis == null) return null;
    if (typeof analysis === 'string') {
        try {
            const p = JSON.parse(analysis);
            return p !== null && typeof p === 'object' ? p : null;
        } catch {
            return null;
        }
    }
    return typeof analysis === 'object' ? analysis : null;
}

/** Match backend `_infer_psl_tier_from_score` when tier was never persisted. */
function inferPslTierFromScore(score: number | null): string {
    if (score == null || Number.isNaN(score)) return '';
    const s = Math.max(0, Math.min(10, score));
    if (s < 3.0) return 'Subhuman';
    if (s < 4.25) return 'LTN';
    if (s < 5.5) return 'MTN';
    if (s < 6.75) return 'HTN';
    if (s < 8.0) return 'Chadlite';
    return 'Chad';
}

const _BONE_UMAX_IDS = new Set(['jawline', 'cheekbones', 'nose', 'eyes', 'symmetry']);

/** Mirrors backend when older rows lack profile_insights.suggested_modules. */
function suggestedModulesFromUmax(analysis: any): string[] {
    const rows = analysis?.umax_metrics;
    if (!Array.isArray(rows) || rows.length === 0) return ['fitmax', 'skinmax'];
    const parsed: { id: string; score: number }[] = [];
    for (const row of rows) {
        if (!row || typeof row !== 'object') continue;
        const id = String((row as { id?: string }).id || '');
        const sc = parseFloat(String((row as { score?: unknown }).score ?? '5'));
        if (!id || Number.isNaN(sc)) continue;
        parsed.push({ id, score: Math.max(0, Math.min(10, sc)) });
    }
    if (!parsed.length) return ['fitmax', 'skinmax'];
    const out: string[] = [];
    let bone = false;
    for (const { id, score } of parsed) {
        if (score > 5.9) continue;
        if (_BONE_UMAX_IDS.has(id)) {
            if (!bone) {
                out.push('bonemax');
                bone = true;
            }
        } else if (id === 'skin') {
            out.push('skinmax');
        }
    }
    if (!out.length) {
        const sorted = [...parsed].sort((x, y) => x.score - y.score);
        for (const { id } of sorted.slice(0, 3)) {
            if (_BONE_UMAX_IDS.has(id)) {
                if (!bone) {
                    out.push('bonemax');
                    bone = true;
                }
            } else if (id === 'skin') {
                out.push('skinmax');
            }
        }
    }
    if (!out.length) return ['fitmax', 'skinmax'];
    return [...new Set(out)].slice(0, 3);
}

function parseOverall(analysis: any): number | null {
    if (!analysis) return null;
    const pr = analysis.psl_rating;
    if (pr && pr.psl_score != null && pr.psl_score !== '') {
        const n = parseFloat(String(pr.psl_score));
        if (!Number.isNaN(n)) return n;
    }
    const o = analysis.overall_score ?? analysis.scan_summary?.overall_score ?? analysis.metrics?.overall_score;
    if (o !== undefined && o !== null) {
        const n = parseFloat(String(o));
        if (!Number.isNaN(n)) return n;
    }
    const m = analysis.umax_metrics;
    if (Array.isArray(m) && m.length > 0) {
        const sum = m.reduce((acc: number, x: any) => acc + (Number(x?.score) || 0), 0);
        const avg = sum / m.length;
        if (!Number.isNaN(avg)) return Math.round(avg * 10) / 10;
    }
    return null;
}

function parsePotential(analysis: any, fallback: number): number {
    const pr = analysis?.psl_rating;
    if (pr?.potential != null && pr.potential !== '') {
        const n = parseFloat(String(pr.potential));
        if (!Number.isNaN(n)) return Math.max(0, Math.min(10, n));
    }
    const p = analysis?.potential_score;
    if (p === undefined || p === null) return fallback;
    const n = parseFloat(String(p));
    if (Number.isNaN(n)) return fallback;
    return Math.max(0, Math.min(10, n));
}

function parseAppeal(analysis: any, fallback: number): number {
    const pr = analysis?.psl_rating;
    if (pr?.appeal != null && pr.appeal !== '') {
        const n = parseFloat(String(pr.appeal));
        if (!Number.isNaN(n)) return Math.max(0, Math.min(10, n));
    }
    return fallback;
}

function getScoreColor(score: number) {
    if (score >= 7) return colors.foreground;
    if (score >= 5) return colors.warning;
    return colors.error;
}

const RATING_DISPLAY_MIN = 2.5;

/** Model potential smoothed for display nudges (paid unlock only). */
function inflatePotentialForDisplay(raw: number): number {
    const headroom = Math.max(0, 10 - raw);
    const bumped = raw + 0.28 + headroom * 0.06;
    return Math.min(10, Math.round(bumped * 10) / 10);
}

/**
 * Anchor "potential" from current rating: lower score → lower ceiling (~8.2–8.4 at 4/10),
 * higher score → higher ceiling (~8.9–9.1 at 6/10, up to ~9.85 at 10/10). Piecewise linear.
 */
function anchorPotentialFromRating(ratingDisplay: number | null): number {
    const r = ratingDisplay ?? 5;
    const x = Math.max(RATING_DISPLAY_MIN, Math.min(10, r));
    const pts: readonly [number, number][] = [
        [2.5, 7.55],
        [4.0, 8.32],
        [6.0, 8.95],
        [8.0, 9.35],
        [10.0, 9.85],
    ];
    if (x <= pts[0][0]) return pts[0][1];
    for (let i = 0; i < pts.length - 1; i++) {
        const [x0, y0] = pts[i];
        const [x1, y1] = pts[i + 1];
        if (x <= x1) {
            const t = (x - x0) / (x1 - x0);
            return y0 + t * (y1 - y0);
        }
    }
    return pts[pts.length - 1][1];
}

/** Shown rating is never below 2.5. */
function clampDisplayRating(overall: number | null): number | null {
    if (overall == null || Number.isNaN(overall)) return null;
    return Math.round(Math.max(RATING_DISPLAY_MIN, Math.min(10, overall)) * 10) / 10;
}

/**
 * Paid/unlocked: potential follows current rating (not stuck at 8), with a small shift from model raw potential.
 * Preview: show raw analysis value only.
 */
function computeDisplayPotential(rawPotential: number, treatAsPaid: boolean, ratingDisplay: number | null): number {
    if (!treatAsPaid) {
        return Math.round(Math.max(0, Math.min(10, rawPotential)) * 10) / 10;
    }
    const anchor = anchorPotentialFromRating(ratingDisplay);
    const inflated = inflatePotentialForDisplay(rawPotential);
    const nudge = (inflated - 7) * 0.1;
    const v = anchor + nudge;
    return Math.round(Math.min(9.9, Math.max(6.4, v)) * 10) / 10;
}

type RouteParams = { postPay?: boolean };

/** Fixed width for PNG export (matches phone layout scale). */
const SHARE_CARD_WIDTH = 390;

async function captureRatingCardToPng(ref: React.RefObject<View | null>): Promise<string | null> {
    if (!ref.current) return null;
    await new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    try {
        const uri = await captureRef(ref.current, {
            format: 'png',
            quality: 1,
            result: 'tmpfile',
        });
        return typeof uri === 'string' ? uri : null;
    } catch (e) {
        console.error('captureRef failed', e);
        return null;
    }
}

/** Off-screen duplicate of the unlocked rating layout for Save / Share as image. */
function ResultsRatingShareCard({
    cardRef,
    frontUri,
    ratingDisplay,
    potentialDisplay,
    ratingColorScore,
    appealScore,
    pslTier,
    archetype,
    ascensionLabelText,
    ageScore,
    onShareImageEvent,
}: {
    cardRef: React.RefObject<View | null>;
    frontUri: string | null;
    ratingDisplay: number | null;
    potentialDisplay: number;
    ratingColorScore: number;
    appealScore: number;
    pslTier: string;
    archetype: string;
    ascensionLabelText: string;
    ageScore: number;
    onShareImageEvent: () => void;
}) {
    return (
        <View ref={cardRef} style={shareCardStyles.root} collapsable={false}>
            <Text style={shareCardStyles.kicker}>AI facial analysis</Text>
            {frontUri ? (
                <View style={shareCardStyles.photoRing} collapsable={false}>
                    <CachedImage
                        uri={frontUri}
                        style={shareCardStyles.photo}
                        onLoad={onShareImageEvent}
                        onError={onShareImageEvent}
                    />
                </View>
            ) : (
                <View style={[shareCardStyles.photoRing, shareCardStyles.photoPlaceholder]} collapsable={false} />
            )}
            <View style={shareCardStyles.scoreRow}>
                <View style={shareCardStyles.scoreOrb} collapsable={false}>
                    <Text style={shareCardStyles.scoreOrbLabel}>RATING</Text>
                    <View style={shareCardStyles.orbNums}>
                        <Text
                            style={[
                                shareCardStyles.scoreOrbNum,
                                ratingDisplay != null ? { color: getScoreColor(ratingColorScore) } : null,
                            ]}
                        >
                            {ratingDisplay != null ? ratingDisplay.toFixed(1) : '—'}
                        </Text>
                        <Text style={shareCardStyles.scoreOrbOut}>/10</Text>
                    </View>
                </View>
                <View style={shareCardStyles.scoreOrb} collapsable={false}>
                    <Text style={shareCardStyles.scoreOrbLabel}>POTENTIAL</Text>
                    <View style={shareCardStyles.orbNums}>
                        <Text style={[shareCardStyles.scoreOrbNum, { color: getScoreColor(potentialDisplay) }]}>
                            {potentialDisplay.toFixed(1)}
                        </Text>
                        <Text style={shareCardStyles.scoreOrbOut}>/10</Text>
                    </View>
                </View>
            </View>
            <View style={shareCardStyles.statGrid}>
                <View style={shareCardStyles.statCell} collapsable={false}>
                    <Text style={shareCardStyles.statLabel}>Tier</Text>
                    <Text style={shareCardStyles.statValue}>{pslTier || '—'}</Text>
                </View>
                <View style={shareCardStyles.statCell} collapsable={false}>
                    <Text style={shareCardStyles.statLabel}>Appeal</Text>
                    <Text style={[shareCardStyles.statValue, { color: getScoreColor(appealScore) }]}>
                        {appealScore.toFixed(1)}/10
                    </Text>
                </View>
                <View style={shareCardStyles.statCell} collapsable={false}>
                    <Text style={shareCardStyles.statLabel}>Archetype</Text>
                    <Text style={shareCardStyles.statValue}>{archetype || '—'}</Text>
                </View>
                <View style={shareCardStyles.statCell} collapsable={false}>
                    <Text style={shareCardStyles.statLabel}>Ascension time</Text>
                    <Text style={shareCardStyles.statValue}>{ascensionLabelText}</Text>
                </View>
                <View style={[shareCardStyles.statCell, shareCardStyles.statCellWide]} collapsable={false}>
                    <Text style={shareCardStyles.statLabel}>Facial age (look)</Text>
                    <Text style={shareCardStyles.statValue}>{ageScore > 0 ? `${ageScore}` : '—'}</Text>
                </View>
            </View>
            <Text style={shareCardStyles.brand}>MAX</Text>
        </View>
    );
}

const shareCardStyles = StyleSheet.create({
    root: {
        width: SHARE_CARD_WIDTH,
        backgroundColor: colors.background,
        paddingHorizontal: 20,
        paddingTop: 28,
        paddingBottom: 32,
        alignItems: 'center',
    },
    kicker: {
        fontSize: 11,
        fontWeight: '600',
        color: colors.textMuted,
        letterSpacing: 1.2,
        marginBottom: 16,
        textAlign: 'center',
    },
    photoRing: {
        width: 200,
        height: 200,
        borderRadius: 100,
        overflow: 'hidden',
        borderWidth: 3,
        borderColor: colors.border,
        marginBottom: 20,
        backgroundColor: colors.surface,
    },
    photoPlaceholder: { backgroundColor: colors.surface },
    photo: { width: '100%', height: '100%' },
    scoreRow: { flexDirection: 'row', justifyContent: 'center', gap: 16, marginBottom: 18, width: '100%' },
    scoreOrb: {
        width: 130,
        height: 130,
        borderRadius: 65,
        backgroundColor: colors.card,
        borderWidth: 2,
        borderColor: colors.borderLight,
        alignItems: 'center',
        justifyContent: 'center',
    },
    scoreOrbLabel: {
        fontSize: 9,
        fontWeight: '700',
        color: colors.textMuted,
        marginBottom: 4,
        letterSpacing: 0.6,
    },
    orbNums: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'center', gap: 2 },
    scoreOrbNum: { fontSize: 36, fontWeight: '800', color: colors.foreground },
    scoreOrbOut: { fontSize: 14, fontWeight: '600', color: colors.textMuted, paddingBottom: 4 },
    statGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
        width: '100%',
        justifyContent: 'space-between',
    },
    statCell: {
        width: '48%',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        padding: 12,
        borderWidth: 1,
        borderColor: colors.border,
    },
    statCellWide: { width: '100%' },
    statLabel: { fontSize: 10, fontWeight: '700', color: colors.textMuted, marginBottom: 4, letterSpacing: 0.6 },
    statValue: { fontSize: 15, fontWeight: '700', color: colors.foreground },
    brand: {
        fontFamily: fonts.serif,
        fontSize: 12,
        letterSpacing: 2,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: 16,
        opacity: 0.5,
    },
});

/** Blurs only inner value content; render label outside this wrapper */
function PaywallBlurShell({ children, minHeight }: { children: React.ReactNode; minHeight?: number }) {
    return (
        <View style={[styles.paywallBlurShell, minHeight ? { minHeight } : null]}>
            {children}
            <BlurView
                intensity={Platform.OS === 'ios' ? 56 : 72}
                tint="light"
                style={StyleSheet.absoluteFill}
                experimentalBlurMethod={Platform.OS === 'android' ? 'dimezisBlurView' : undefined}
            />
            <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.paywallFlatOverlay]} />
        </View>
    );
}

/** Full-screen progress UI — only while server is still analyzing the scan (not for routine GET /latest). */
function ScanProcessingView() {
    const insets = useSafeAreaInsets();
    const [trackWidth, setTrackWidth] = useState(0);
    const progressAnim = useRef(new Animated.Value(12)).current;
    const [pctLabel, setPctLabel] = useState(12);

    useEffect(() => {
        const sub = progressAnim.addListener(({ value }) => setPctLabel(Math.min(100, Math.max(0, Math.round(value)))));
        const loop = Animated.loop(
            Animated.sequence([
                Animated.timing(progressAnim, { toValue: 91, duration: 2400, useNativeDriver: false }),
                Animated.timing(progressAnim, { toValue: 14, duration: 600, useNativeDriver: false }),
            ]),
        );
        loop.start();
        return () => {
            progressAnim.removeListener(sub);
            loop.stop();
        };
    }, [progressAnim]);

    const onTrackLayout = (e: LayoutChangeEvent) => setTrackWidth(e.nativeEvent.layout.width);
    const fillWidth =
        trackWidth > 0
            ? progressAnim.interpolate({
                  inputRange: [0, 100],
                  outputRange: [0, trackWidth],
                  extrapolate: 'clamp',
              })
            : 0;

    return (
        <View style={[styles.root, styles.loadingRoot]}>
            <View style={[styles.loadingHeader, { paddingTop: Math.max(insets.top, 12) + 8 }]}>
                <View style={styles.progressTopRow}>
                    <Text style={styles.progressTitle}>Analyzing your scan</Text>
                    <Text style={styles.progressPct}>{pctLabel}%</Text>
                </View>
                <View style={styles.loadingTrackWrap}>
                    <View style={styles.track} onLayout={onTrackLayout}>
                        <Animated.View style={[styles.trackFill, { width: fillWidth }]} />
                    </View>
                </View>
                <Text style={styles.loadingSub}>Building your facial ratings…</Text>
                <Text style={styles.stayInAppNotice}>
                    Stay in the app until this finishes—leaving can delay or interrupt your results.
                </Text>
            </View>
            <ActivityIndicator size="large" color={colors.foreground} style={{ marginTop: spacing.xl }} />
        </View>
    );
}

export default function FaceScanResultsScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { isPaid, isScanUser, refreshUser, user } = useAuth() as { isPaid: boolean; isScanUser: boolean; refreshUser: () => Promise<unknown>; user: any };
    const postPayParam = !!(route.params as RouteParams)?.postPay;
    const scanIdParam = (route.params as any)?.scanId as string | undefined;
    const viewingHistory = !!scanIdParam;
    const postSubscriptionOnboarding = !!(user?.onboarding as { post_subscription_onboarding?: boolean } | undefined)
        ?.post_subscription_onboarding;

    const [scan, setScan] = useState<any>(null);
    /** First GET /latest in flight — use a small spinner, not the full analyzing UI. */
    const [hydrating, setHydrating] = useState(true);
    const [processing, setProcessing] = useState(false);
    /** Set true when we auto-advance past a missing scan (dev-skip flow) so we
     *  show a spinner instead of flashing the "Couldn't load your scan" error. */
    const [advancing, setAdvancing] = useState(false);
    const advancedRef = useRef(false);
    const shareCardRef = useRef<View>(null);
    const [shareImageReady, setShareImageReady] = useState(true);
    const [shareCaptureBusy, setShareCaptureBusy] = useState(false);

    const bootstrap = useCallback(async () => {
        setHydrating(true);
        try {
            const result = scanIdParam ? await api.getScanById(scanIdParam) : await api.getLatestScan();
            if (postPayParam || result?.is_unlocked) {
                try {
                    await refreshUser();
                } catch (e) {
                    console.error(e);
                }
            }
            setScan(result);
        } catch (e) {
            console.error(e);
            setScan(null);
        } finally {
            setHydrating(false);
        }
    }, [postPayParam, refreshUser, scanIdParam]);

    useEffect(() => {
        bootstrap();
    }, [bootstrap]);

    useEffect(() => {
        if (scan?.processing_status !== 'processing') return;
        setProcessing(true);
        const appStateRef = { current: AppState.currentState };
        let cancelled = false;
        let timer: ReturnType<typeof setTimeout> | null = null;
        // Backoff: 3s for first minute, 6s next two minutes, 12s thereafter. Caps
        // the polling data cost when a scan legitimately takes a while.
        const startedAt = Date.now();
        const nextDelay = () => {
            const elapsed = Date.now() - startedAt;
            if (elapsed < 60_000) return 3000;
            if (elapsed < 180_000) return 6000;
            return 12000;
        };
        const doPoll = async () => {
            try {
                const result = scanIdParam ? await api.getScanById(scanIdParam) : await api.getLatestScan();
                if (cancelled) return;
                setScan(result);
                if (result.processing_status !== 'processing') {
                    setProcessing(false);
                    return; // loop exits because status changed
                }
            } catch (e) {
                console.error(e);
            }
            if (!cancelled) timer = setTimeout(tick, nextDelay());
        };
        const tick = () => {
            if (appStateRef.current !== 'active') {
                timer = setTimeout(tick, nextDelay());
                return;
            }
            void doPoll();
        };
        timer = setTimeout(tick, nextDelay());
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
    }, [scan?.processing_status, scanIdParam]);

    const a = coerceAnalysisObject(scan?.analysis);
    const treatAsPaid = isPaid === true || isScanUser === true || scan?.is_unlocked === true;
    const locked = !treatAsPaid;
    /** After pay, user must pick programs — use server flag so CTA is correct even before Home re-pushes `postPay`. */
    // Only run the post-pay onboarding CTA when explicitly deep-linked from payment.
    const postPay = !!postPayParam && !locked && postSubscriptionOnboarding;
    /** After Stripe activate we set this false so user texts the Sendblue line before continuing.
     *  Also treat null/undefined as pending — legacy accounts activated before the backend fix
     *  have the field as null, meaning the step was never completed. Only `true` means done. */
    const sendbluePending =
        treatAsPaid &&
        (user?.onboarding as { sendblue_connect_completed?: boolean | null } | undefined)?.sendblue_connect_completed !== true;

    /** Jump to the next post-pay onboarding step without needing a scan.
     *  Used both by the auto-advance effect below and the manual Skip button
     *  on the fetch-error UI, so a paid user with no scan (e.g. DEV
     *  test-activate) is never trapped on "Couldn't load your scan". */
    const advancePostPay = useCallback(() => {
        if (sendbluePending) {
            const next = 'ModuleSelect';
            if (isPaid === true && !userHasSignupPhone(user)) {
                navigation.navigate('SmsCoachingIntro', { next });
            } else {
                navigation.navigate('SendblueConnect', { next });
            }
            return;
        }
        navigation.navigate('ModuleSelect');
    }, [sendbluePending, isPaid, user, navigation]);

    /** Auto-advance when we arrived from the paywall redirect but there is no
     *  scan on file. The normal flow requires scanning before paying, but
     *  dev/test-activate bypasses the scan, which would otherwise dead-end
     *  this screen (back is disabled in postPayOnboardingFlow). */
    useEffect(() => {
        if (hydrating || scan) return;
        if (!postPayParam) return;
        if (!(isPaid === true || isScanUser === true)) return;
        if (advancedRef.current) return;
        advancedRef.current = true;
        setAdvancing(true);
        advancePostPay();
    }, [hydrating, scan, postPayParam, isPaid, isScanUser, advancePostPay]);

    const overallScore = parseOverall(a);
    const base = overallScore ?? 5;
    const rawPotential = parsePotential(a, Math.min(10, Math.round((base + 0.6) * 10) / 10));
    const ratingDisplay = clampDisplayRating(overallScore);
    const potentialDisplay = computeDisplayPotential(rawPotential, treatAsPaid, ratingDisplay);
    const appealScore = parseAppeal(a, base);
    const isProcessing = processing || scan?.processing_status === 'processing';
    const frontUri = api.resolveAttachmentUrl(scan?.images?.front);


    const pr = a?.psl_rating && typeof a.psl_rating === 'object' ? a.psl_rating : {};
    const pi = a?.profile_insights && typeof a.profile_insights === 'object' ? a.profile_insights : {};
    const facialSummary = (user?.onboarding as { facial_scan_summary?: Record<string, unknown> } | undefined)
        ?.facial_scan_summary;
    const archetype =
        (typeof pr?.archetype === 'string' ? pr.archetype.trim() : '') ||
        (typeof pi?.archetype === 'string' ? pi.archetype.trim() : '') ||
        (typeof facialSummary?.archetype === 'string' ? facialSummary.archetype.trim() : '');
    let pslTier = typeof pr?.psl_tier === 'string' ? pr.psl_tier.trim() : '';
    if (!pslTier && typeof a?.psl_tier === 'string') pslTier = a.psl_tier.trim();
    if (!pslTier && typeof facialSummary?.psl_tier === 'string') pslTier = facialSummary.psl_tier.trim();
    if (!pslTier) {
        const t = inferPslTierFromScore(overallScore);
        if (t) pslTier = t;
    }
    const ascensionMonths =
        typeof pr?.ascension_time_months === 'number' && !Number.isNaN(pr.ascension_time_months)
            ? pr.ascension_time_months
            : parseInt(String(pr?.ascension_time_months || '0'), 10) || 0;
    const ageScore =
        typeof pr?.age_score === 'number' && !Number.isNaN(pr.age_score)
            ? pr.age_score
            : parseInt(String(pr?.age_score || '0'), 10) || 0;
    let suggestedMods: string[] = Array.isArray(pi?.suggested_modules) ? pi.suggested_modules.map(String) : [];
    if (!suggestedMods.length && Array.isArray(a?.suggested_modules)) {
        suggestedMods = a.suggested_modules.map(String);
    }
    if (!suggestedMods.length && Array.isArray(facialSummary?.suggested_modules)) {
        suggestedMods = (facialSummary!.suggested_modules as unknown[]).map(String);
    }
    if (!suggestedMods.length && a) {
        suggestedMods = suggestedModulesFromUmax(a);
    }
    suggestedMods = suggestedMods.slice(0, 3);

    const goPayment = () => navigation.navigate('Payment');

    const onPrimaryCta = async () => {
        if (isScanUser) {
            // Reset rather than push so the back-stack doesn't grow across repeated scans.
            navigation.reset({ index: 0, routes: [{ name: 'FaceScan' }] });
            return;
        }
        if (locked) {
            goPayment();
            return;
        }
        if (sendbluePending) {
            const next = postPay ? 'ModuleSelect' : 'Main';
            if (isPaid === true && !userHasSignupPhone(user)) {
                navigation.navigate('SmsCoachingIntro', { next });
            } else {
                navigation.navigate('SendblueConnect', { next });
            }
            return;
        }
        if (postPay) {
            navigation.navigate('ModuleSelect');
            return;
        }
        navigation.navigate('Main');
    };

    /** During post-pay onboarding, do not use back to bail to Home — user must complete Sendblue + notifications + programs. */
    const postPayOnboardingFlow = postPay && !viewingHistory;

    const headerBack = () => {
        if (postPayOnboardingFlow) {
            return;
        }
        if (isScanUser) {
            navigation.reset({ index: 0, routes: [{ name: 'FaceScan' }] });
            return;
        }
        if (navigation.canGoBack()) navigation.goBack();
        else navigation.navigate('Main');
    };

    useEffect(() => {
        if (!postPayOnboardingFlow || Platform.OS !== 'android') return;
        const sub = BackHandler.addEventListener('hardwareBackPress', () => true);
        return () => sub.remove();
    }, [postPayOnboardingFlow]);

    useLayoutEffect(() => {
        navigation.setOptions({ gestureEnabled: !postPayOnboardingFlow });
    }, [navigation, postPayOnboardingFlow]);

    const serverProcessing = scan?.processing_status === 'processing';

    /** Progress bar + copy only while backend is still running analysis — not after upload returns or on revisits. */
    if (serverProcessing) {
        return <ScanProcessingView />;
    }

    if ((hydrating && !scan) || (advancing && !scan)) {
        return (
            <View style={[styles.root, styles.fetchingRoot]}>
                <ActivityIndicator size="large" color={colors.foreground} />
            </View>
        );
    }

    if (!hydrating && !scan) {
        const canSkipForward = treatAsPaid;
        return (
            <View style={[styles.root, styles.fetchingRoot]}>
                <Text style={styles.fetchErrorText}>Couldn&apos;t load your scan.</Text>
                <TouchableOpacity style={styles.fetchRetryBtn} onPress={bootstrap} activeOpacity={0.85}>
                    <Text style={styles.fetchRetryText}>Try again</Text>
                </TouchableOpacity>
                {canSkipForward ? (
                    <TouchableOpacity
                        style={styles.fetchSkipBtn}
                        onPress={() => {
                            advancedRef.current = true;
                            setAdvancing(true);
                            if (postPayParam) advancePostPay();
                            else navigation.navigate('Main');
                        }}
                        activeOpacity={0.85}
                    >
                        <Text style={styles.fetchSkipText}>Skip for now</Text>
                    </TouchableOpacity>
                ) : null}
            </View>
        );
    }

    const ascensionLabelText = ascensionMonths > 0 ? `${ascensionMonths} months` : '—';

    const ratingColorScore = ratingDisplay ?? RATING_DISPLAY_MIN;

    const onSaveScanPhoto = async () => {
        if (Platform.OS === 'web') {
            Alert.alert('Save on web', 'Use your browser screenshot tool, or open Agartha on your phone to save your rating card to Photos.');
            return;
        }
        if (frontUri && !shareImageReady) {
            Alert.alert('Almost ready', 'Your scan photo is still loading — try again in a second.');
            return;
        }
        setShareCaptureBusy(true);
        try {
            const pngUri = await captureRatingCardToPng(shareCardRef);
            if (!pngUri) {
                Alert.alert('Save failed', 'Could not create the image. Try again.');
                return;
            }
            const perm = await MediaLibrary.requestPermissionsAsync();
            if (!perm.granted) {
                Alert.alert('Permission needed', 'Allow Photos access to save your rating card.');
                return;
            }
            await MediaLibrary.saveToLibraryAsync(pngUri);
            Alert.alert('Saved', 'Your rating card was saved to Photos.');
        } catch (e) {
            console.error(e);
            Alert.alert('Save failed', 'Could not save to Photos. Try again.');
        } finally {
            setShareCaptureBusy(false);
        }
    };

    const onShareRating = async () => {
        const tierLine = pslTier ? ` · Tier: ${pslTier}` : '';
        const r = ratingDisplay != null ? ratingDisplay.toFixed(1) : '—';
        const msg = `My facial rating on Agartha: ${r}/10 · Potential: ${potentialDisplay.toFixed(1)}/10${tierLine}`;

        if (Platform.OS === 'web') {
            try {
                const nav = typeof globalThis !== 'undefined' ? (globalThis as any).navigator : undefined;
                if (nav?.share) {
                    await nav.share({ title: 'My Agartha rating', text: msg });
                    return;
                }
                if (nav?.clipboard?.writeText) {
                    await nav.clipboard.writeText(msg);
                    Alert.alert('Copied', 'Rating text copied to clipboard.');
                    return;
                }
            } catch {
                /* fall through */
            }
            Alert.alert('My Agartha rating', msg);
            return;
        }

        if (frontUri && !shareImageReady) {
            Alert.alert('Almost ready', 'Your scan photo is still loading — try again in a second.');
            return;
        }

        setShareCaptureBusy(true);
        try {
            const pngUri = await captureRatingCardToPng(shareCardRef);
            if (!pngUri) {
                await Share.share({ message: msg, title: 'My Agartha rating' });
                return;
            }
            const canShareFiles = await Sharing.isAvailableAsync();
            if (canShareFiles) {
                await Sharing.shareAsync(pngUri, {
                    mimeType: 'image/png',
                    dialogTitle: 'Share your Agartha rating',
                });
            } else {
                await Share.share({
                    title: 'My Agartha rating',
                    message: msg,
                    url: pngUri,
                } as any);
            }
        } catch (e: any) {
            if (e?.message !== 'User did not share') console.error(e);
            try {
                await Share.share({ message: msg, title: 'My Agartha rating' });
            } catch (e2: any) {
                if (e2?.message !== 'User did not share') console.error(e2);
            }
        } finally {
            setShareCaptureBusy(false);
        }
    };

    return (
        <View style={styles.root}>
            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                {/* ── Back ── */}
                <View style={styles.header}>
                    {postPayOnboardingFlow ? (
                        <View style={styles.iconHit} />
                    ) : (
                        <TouchableOpacity onPress={headerBack} style={styles.iconHit} hitSlop={12}>
                            <Ionicons name="chevron-back" size={22} color={colors.foreground} />
                        </TouchableOpacity>
                    )}
                </View>

                <Text style={styles.sectionLabel}>AI FACIAL ANALYSIS</Text>

                {/* ── Photo ── */}
                <View style={styles.photoWrap}>
                    {frontUri ? (
                        <View style={styles.photoRing}>
                            <CachedImage uri={frontUri} style={styles.photoImg} />
                        </View>
                    ) : (
                        <View style={[styles.photoRing, styles.photoEmpty]} />
                    )}
                </View>

                {/* ── Score bubbles ── */}
                <View style={styles.bubblesRow}>
                    <View style={styles.bubble}>
                        <Text style={styles.bubbleLabel}>RATING</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 10 }} />
                        ) : locked ? (
                            <PaywallBlurShell minHeight={44}>
                                <Text style={[styles.bubbleNum, ratingDisplay != null && { color: getScoreColor(ratingColorScore) }]}>
                                    {ratingDisplay != null ? ratingDisplay.toFixed(1) : '—'}
                                </Text>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={[styles.bubbleNum, ratingDisplay != null && { color: getScoreColor(ratingColorScore) }]}>
                                {ratingDisplay != null ? ratingDisplay.toFixed(1) : '—'}
                            </Text>
                        )}
                        <Text style={styles.bubbleUnit}>/10</Text>
                    </View>

                    <View style={styles.bubble}>
                        <Text style={styles.bubbleLabel}>POTENTIAL</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 10 }} />
                        ) : locked ? (
                            <PaywallBlurShell minHeight={44}>
                                <Text style={[styles.bubbleNum, { color: getScoreColor(potentialDisplay) }]}>
                                    {potentialDisplay.toFixed(1)}
                                </Text>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={[styles.bubbleNum, { color: getScoreColor(potentialDisplay) }]}>
                                {potentialDisplay.toFixed(1)}
                            </Text>
                        )}
                        <Text style={styles.bubbleUnit}>/10</Text>
                    </View>
                </View>

                {/* ── Brand ── */}
                <Text style={styles.brandText}>max</Text>

                {/* ── Stats ── */}
                <View style={styles.statsBlock}>
                    {[
                        { label: 'Tier', value: pslTier || '—', color: colors.foreground },
                        { label: 'Appeal', value: appealScore > 0 ? `${appealScore.toFixed(1)}/10` : '—', color: getScoreColor(appealScore) },
                        { label: 'Archetype', value: archetype || '—', color: colors.foreground },
                        { label: 'Ascension', value: ascensionLabelText || '—', color: colors.foreground },
                        { label: 'Facial age', value: ageScore > 0 ? `${ageScore}` : '—', color: colors.foreground },
                    ].map((item, idx) => (
                        <View key={idx} style={[styles.statRow, idx === 0 && styles.statRowFirst]}>
                            <Text style={styles.statLabel}>{item.label}</Text>
                            {isProcessing ? (
                                <ActivityIndicator size="small" color={colors.textMuted} />
                            ) : locked ? (
                                <PaywallBlurShell minHeight={20}>
                                    <Text style={[styles.statValue, { color: item.color }]}>{item.value}</Text>
                                </PaywallBlurShell>
                            ) : (
                                <Text style={[styles.statValue, { color: item.color }]}>{item.value}</Text>
                            )}
                        </View>
                    ))}
                </View>

                {/* ── Recommended ── */}
                {!locked && suggestedMods.length > 0 ? (
                    <View style={styles.recsSection}>
                        <Text style={styles.recsHeading}>Recommended</Text>
                        <View style={styles.recsPills}>
                            {suggestedMods.map((m, i) => (
                                <View key={`${m}-${i}`} style={styles.recPill}>
                                    <Text style={styles.recPillText}>{formatSuggestedModuleTitle(m)}</Text>
                                </View>
                            ))}
                        </View>
                    </View>
                ) : null}

                {/* ── Share / Save ── */}
                {!locked && !isProcessing ? (
                    <View style={styles.shareRow}>
                        <TouchableOpacity
                            style={[styles.shareBtn, shareCaptureBusy && styles.shareBtnDisabled]}
                            onPress={onSaveScanPhoto}
                            activeOpacity={0.7}
                            disabled={shareCaptureBusy}
                        >
                            <Ionicons name="download-outline" size={14} color={colors.textMuted} />
                            <Text style={styles.shareBtnText}>Save</Text>
                        </TouchableOpacity>
                        <View style={styles.shareDot} />
                        <TouchableOpacity
                            style={[styles.shareBtn, shareCaptureBusy && styles.shareBtnDisabled]}
                            onPress={onShareRating}
                            activeOpacity={0.7}
                            disabled={shareCaptureBusy}
                        >
                            <Ionicons name="share-outline" size={14} color={colors.textMuted} />
                            <Text style={styles.shareBtnText}>Share</Text>
                        </TouchableOpacity>
                    </View>
                ) : null}

                {/* ── Paywall ── */}
                {locked && !isProcessing ? (
                    <View style={styles.paywallTeaser}>
                        <Text style={styles.paywallTitle}>See your full potential</Text>
                        <Text style={styles.paywallSub}>
                            Unlock exact scores, archetype, and a personalized plan.
                        </Text>
                    </View>
                ) : null}

                <Text style={styles.disclaimer}>For general wellness only — not medical advice.</Text>

                {/* ── CTA (after shareable content — scroll down to act) ── */}
                {!viewingHistory ? (
                    <>
                        <TouchableOpacity style={styles.cta} onPress={onPrimaryCta} activeOpacity={0.85}>
                            <Text style={styles.ctaText}>
                                {isScanUser
                                    ? 'Scan Again'
                                    : locked
                                        ? 'Unlock full results'
                                        : postPay && sendbluePending
                                          ? 'Continue'
                                          : postPay
                                            ? 'Choose your programs'
                                            : 'Continue'}
                            </Text>
                            <Ionicons
                                name={isScanUser ? 'camera-outline' : locked ? 'lock-open-outline' : 'arrow-forward'}
                                size={17}
                                color={colors.background}
                            />
                        </TouchableOpacity>

                        {!isScanUser && !locked && !postSubscriptionOnboarding ? (
                            <TouchableOpacity style={styles.skipBtn} onPress={() => navigation.navigate('Main')} activeOpacity={0.7}>
                                <Text style={styles.skipText}>Go to home</Text>
                            </TouchableOpacity>
                        ) : null}
                    </>
                ) : null}
            </ScrollView>

            {!locked && !isProcessing && Platform.OS !== 'web' ? (
                <View style={styles.shareCardOffscreen} pointerEvents="none" collapsable={false}>
                    <ResultsRatingShareCard
                        cardRef={shareCardRef}
                        frontUri={frontUri ?? null}
                        ratingDisplay={ratingDisplay}
                        potentialDisplay={potentialDisplay}
                        ratingColorScore={ratingColorScore}
                        appealScore={appealScore}
                        pslTier={pslTier}
                        archetype={archetype}
                        ascensionLabelText={ascensionLabelText}
                        ageScore={ageScore}
                        onShareImageEvent={() => setShareImageReady(true)}
                    />
                </View>
            ) : null}
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },

    /* ── Loading / fetching ── */
    loadingRoot: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.lg },
    fetchingRoot: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.xl },
    fetchErrorText: { ...typography.body, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.md },
    fetchRetryBtn: { backgroundColor: colors.foreground, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: borderRadius.full },
    fetchRetryText: { ...typography.button, color: colors.background },
    fetchSkipBtn: {
        marginTop: spacing.md,
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.sm + 2,
        borderRadius: borderRadius.full,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    fetchSkipText: { ...typography.button, color: colors.textSecondary },
    loadingHeader: { marginBottom: spacing.md, width: '100%', maxWidth: 420, alignItems: 'center' },
    loadingTrackWrap: { alignSelf: 'stretch', width: '100%', marginTop: spacing.sm },
    loadingSub: { fontSize: 14, color: colors.textSecondary, marginTop: spacing.sm, textAlign: 'center', alignSelf: 'stretch' },
    stayInAppNotice: { fontSize: 12, lineHeight: 17, color: colors.textMuted, marginTop: spacing.md, textAlign: 'center', alignSelf: 'stretch', paddingHorizontal: spacing.sm },
    progressTopRow: { flexDirection: 'row', justifyContent: 'center', alignItems: 'baseline', gap: spacing.md, marginBottom: 4 },
    progressTitle: { ...typography.h3, fontSize: 20, textAlign: 'center' },
    progressPct: { fontSize: 22, fontWeight: '800', color: colors.foreground, letterSpacing: -0.5 },
    track: { height: 10, borderRadius: borderRadius.full, backgroundColor: colors.borderLight, overflow: 'hidden' },
    trackFill: { height: '100%', borderRadius: borderRadius.full, backgroundColor: colors.foreground },

    /* ── Scroll / blur ── */
    scroll: { paddingHorizontal: 28, paddingTop: 48, paddingBottom: 40 },
    paywallBlurShell: { borderRadius: 8, overflow: 'hidden', backgroundColor: colors.surface, position: 'relative', alignSelf: 'stretch', width: '100%' },
    paywallFlatOverlay: { backgroundColor: 'rgba(245,245,243,0.55)' },

    /* ── Header ── */
    header: { alignSelf: 'flex-start' as const, marginBottom: 12 },
    iconHit: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },

    /* ── Section label ── */
    sectionLabel: {
        fontSize: 9,
        fontWeight: '600',
        color: colors.textMuted,
        letterSpacing: 2.5,
        textAlign: 'center',
        marginBottom: 24,
        opacity: 0.6,
    },

    /* ── Photo ── */
    photoWrap: { alignItems: 'center', marginBottom: 28 },
    photoRing: {
        width: 140,
        height: 140,
        borderRadius: 70,
        overflow: 'hidden',
        backgroundColor: colors.surface,
        borderWidth: 3,
        borderColor: 'rgba(0,0,0,0.04)',
    },
    photoEmpty: { borderWidth: 1, borderColor: colors.borderLight },
    photoImg: { width: '100%', height: '100%' },

    /* ── Score bubbles ── */
    bubblesRow: {
        flexDirection: 'row',
        justifyContent: 'center',
        gap: 20,
        marginBottom: 24,
    },
    bubble: {
        width: 136,
        height: 136,
        borderRadius: 68,
        backgroundColor: colors.background,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: 'rgba(0,0,0,0.06)',
    },
    bubbleLabel: {
        fontSize: 8,
        fontWeight: '600',
        color: colors.textMuted,
        letterSpacing: 2,
        marginBottom: 2,
        opacity: 0.7,
    },
    bubbleNum: {
        fontFamily: fonts.serif,
        fontSize: 42,
        fontWeight: '700',
        color: colors.foreground,
        letterSpacing: -2,
        lineHeight: 48,
        includeFontPadding: false,
    },
    bubbleUnit: {
        fontSize: 11,
        fontWeight: '400',
        color: colors.textMuted,
        marginTop: 2,
        opacity: 0.5,
    },

    /* ── Brand text ── */
    brandText: {
        fontFamily: fonts.serif,
        fontSize: 11,
        letterSpacing: 3,
        color: colors.textMuted,
        textAlign: 'center',
        textTransform: 'uppercase',
        opacity: 0.3,
        marginBottom: 32,
    },

    /* ── Stat rows ── */
    statsBlock: { marginBottom: 28 },
    statRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: 14,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: 'rgba(0,0,0,0.06)',
    },
    statRowFirst: { borderTopWidth: 0 },
    statLabel: {
        fontSize: 13,
        fontWeight: '400',
        color: colors.textMuted,
        letterSpacing: 0.2,
    },
    statValue: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: -0.2,
    },

    /* ── Recommended ── */
    recsSection: { marginBottom: 28 },
    recsHeading: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textMuted,
        letterSpacing: 1.5,
        textTransform: 'uppercase',
        marginBottom: 12,
        opacity: 0.6,
    },
    recsPills: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 8,
    },
    recPill: {
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: 'rgba(0,0,0,0.1)',
    },
    recPillText: {
        fontSize: 12,
        fontWeight: '500',
        color: colors.foreground,
        letterSpacing: 0.1,
    },

    /* ── Share ── */
    shareRow: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        gap: 16,
        marginBottom: 24,
    },
    shareBtn: {
        flexDirection: 'row', alignItems: 'center', gap: 5,
        paddingVertical: 6, paddingHorizontal: 0,
    },
    shareBtnText: { fontSize: 12, fontWeight: '500', color: colors.textMuted },
    shareBtnDisabled: { opacity: 0.3 },
    shareDot: {
        width: 3,
        height: 3,
        borderRadius: 1.5,
        backgroundColor: colors.textMuted,
        opacity: 0.25,
    },

    /* ── Paywall teaser ── */
    paywallTeaser: { alignItems: 'center', paddingVertical: 24, marginBottom: 4 },
    paywallTitle: { fontFamily: fonts.serif, fontSize: 18, fontWeight: '500', color: colors.foreground, letterSpacing: -0.3 },
    paywallSub: { fontSize: 13, lineHeight: 19, color: colors.textMuted, textAlign: 'center', marginTop: 8, maxWidth: 240 },

    /* ── CTA ── */
    cta: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
        backgroundColor: colors.foreground, paddingVertical: 16, borderRadius: borderRadius.full,
        marginTop: spacing.xs,
    },
    ctaText: { fontSize: 14, fontWeight: '600', color: colors.background, letterSpacing: 0.3 },
    skipBtn: { alignItems: 'center', paddingVertical: 14 },
    skipText: { fontSize: 12, color: colors.textMuted, fontWeight: '500' },

    /* ── Disclaimer ── */
    disclaimer: {
        fontSize: 9,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: 20,
        lineHeight: 13,
        marginBottom: spacing.xs,
        opacity: 0.3,
    },

    shareCardOffscreen: { position: 'absolute', width: SHARE_CARD_WIDTH, left: -4000, top: 0, opacity: 1 },
});
