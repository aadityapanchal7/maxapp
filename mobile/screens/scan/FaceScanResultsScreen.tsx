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
    const { isPaid, refreshUser, user } = useAuth() as any;
    const postPayParam = !!(route.params as RouteParams)?.postPay;
    const scanIdParam = (route.params as any)?.scanId as string | undefined;
    const viewingHistory = !!scanIdParam;
    const postSubscriptionOnboarding = !!(user?.onboarding as { post_subscription_onboarding?: boolean } | undefined)
        ?.post_subscription_onboarding;

    const [scan, setScan] = useState<any>(null);
    /** First GET /latest in flight — use a small spinner, not the full analyzing UI. */
    const [hydrating, setHydrating] = useState(true);
    const [processing, setProcessing] = useState(false);
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
    /** API sets is_unlocked from DB — fixes empty screen when JWT context lags after payment */
    const treatAsPaid = isPaid === true || scan?.is_unlocked === true;
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
        if (locked) {
            goPayment();
            return;
        }
        if (sendbluePending) {
            navigation.navigate('SendblueConnect', { next: postPay ? 'ModuleSelect' : 'Main' });
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

    if (hydrating && !scan) {
        return (
            <View style={[styles.root, styles.fetchingRoot]}>
                <ActivityIndicator size="large" color={colors.foreground} />
            </View>
        );
    }

    if (!hydrating && !scan) {
        return (
            <View style={[styles.root, styles.fetchingRoot]}>
                <Text style={styles.fetchErrorText}>Couldn&apos;t load your scan.</Text>
                <TouchableOpacity style={styles.fetchRetryBtn} onPress={bootstrap} activeOpacity={0.85}>
                    <Text style={styles.fetchRetryText}>Try again</Text>
                </TouchableOpacity>
            </View>
        );
    }

    const ascensionLabelText = ascensionMonths > 0 ? `${ascensionMonths} months` : '—';

    const ratingColorScore = ratingDisplay ?? RATING_DISPLAY_MIN;

    const onSaveScanPhoto = async () => {
        if (Platform.OS === 'web') {
            Alert.alert('Save on web', 'Use your browser screenshot tool, or open Max on your phone to save your rating card to Photos.');
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
        const msg = `My facial rating on Max: ${r}/10 · Potential: ${potentialDisplay.toFixed(1)}/10${tierLine}`;

        if (Platform.OS === 'web') {
            try {
                const nav = typeof globalThis !== 'undefined' ? (globalThis as any).navigator : undefined;
                if (nav?.share) {
                    await nav.share({ title: 'My Max rating', text: msg });
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
            Alert.alert('My Max rating', msg);
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
                await Share.share({ message: msg, title: 'My Max rating' });
                return;
            }
            const canShareFiles = await Sharing.isAvailableAsync();
            if (canShareFiles) {
                await Sharing.shareAsync(pngUri, {
                    mimeType: 'image/png',
                    dialogTitle: 'Share your Max rating',
                });
            } else {
                await Share.share({
                    title: 'My Max rating',
                    message: msg,
                    url: pngUri,
                } as any);
            }
        } catch (e: any) {
            if (e?.message !== 'User did not share') console.error(e);
            try {
                await Share.share({ message: msg, title: 'My Max rating' });
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
                {/* ── Header ── */}
                <View style={styles.header}>
                    {postPayOnboardingFlow ? (
                        <View style={styles.iconHit} />
                    ) : (
                        <TouchableOpacity onPress={headerBack} style={styles.iconHit} hitSlop={12}>
                            <Ionicons name="chevron-back" size={22} color={colors.foreground} />
                        </TouchableOpacity>
                    )}
                    <Text style={styles.headerTitle}>Your results</Text>
                    <View style={styles.iconHit} />
                </View>

                {/* ── Portrait photo ── */}
                {frontUri ? (
                    <View style={styles.heroPhoto}>
                        <CachedImage uri={frontUri} style={styles.heroImg} />
                    </View>
                ) : null}

                {/* ── Dual scores ── */}
                <View style={styles.scoresRow}>
                    <View style={styles.scoreCol}>
                        <Text style={styles.scoreColLabel}>Rating</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 10 }} />
                        ) : locked ? (
                            <PaywallBlurShell minHeight={48}>
                                <Text style={styles.scoreColNum}>
                                    {ratingDisplay != null ? ratingDisplay.toFixed(1) : '—'}
                                </Text>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={styles.scoreColNum}>
                                {ratingDisplay != null ? ratingDisplay.toFixed(1) : '—'}
                            </Text>
                        )}
                    </View>

                    <View style={styles.scoreColSep} />

                    <View style={styles.scoreCol}>
                        <Text style={styles.scoreColLabel}>Potential</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 10 }} />
                        ) : locked ? (
                            <PaywallBlurShell minHeight={48}>
                                <Text style={styles.scoreColNum}>
                                    {potentialDisplay.toFixed(1)}
                                </Text>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={styles.scoreColNum}>
                                {potentialDisplay.toFixed(1)}
                            </Text>
                        )}
                    </View>
                </View>

                {/* ── Tier badge ── */}
                {pslTier && !isProcessing ? (
                    <View style={styles.tierRow}>
                        {locked ? (
                            <PaywallBlurShell minHeight={26}>
                                <View style={styles.tierPill}><Text style={styles.tierPillText}>{pslTier}</Text></View>
                            </PaywallBlurShell>
                        ) : (
                            <View style={styles.tierPill}><Text style={styles.tierPillText}>{pslTier}</Text></View>
                        )}
                    </View>
                ) : null}

                {/* ── Breakdown rows ── */}
                <View style={styles.breakdownSection}>
                    <Text style={styles.breakdownHeading}>Breakdown</Text>
                    {[
                        { label: 'Appeal', value: appealScore.toFixed(1) + '/10', color: getScoreColor(appealScore) },
                        { label: 'Archetype', value: archetype || '—', color: colors.foreground },
                        { label: 'Ascension time', value: ascensionLabelText, color: colors.foreground },
                        { label: 'Facial age', value: ageScore > 0 ? `${ageScore}` : '—', color: colors.foreground },
                    ].map((item, idx) => (
                        <View key={idx} style={styles.breakdownRow}>
                            <Text style={styles.breakdownLabel}>{item.label}</Text>
                            {isProcessing ? (
                                <ActivityIndicator size="small" color={colors.textMuted} />
                            ) : locked ? (
                                <PaywallBlurShell minHeight={20}>
                                    <Text style={[styles.breakdownValue, { color: item.color }]}>{item.value}</Text>
                                </PaywallBlurShell>
                            ) : (
                                <Text style={[styles.breakdownValue, { color: item.color }]}>{item.value}</Text>
                            )}
                        </View>
                    ))}
                </View>

                {/* ── Suggested modules ── */}
                {!locked && suggestedMods.length > 0 ? (
                    <View style={styles.modsSection}>
                        <Text style={styles.breakdownHeading}>Recommended for you</Text>
                        <View style={styles.modsRow}>
                            {suggestedMods.map((m, i) => (
                                <View key={i} style={styles.modChip}>
                                    <Text style={styles.modChipText}>{m}</Text>
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
                            activeOpacity={0.8}
                            disabled={shareCaptureBusy}
                        >
                            <Ionicons name="download-outline" size={17} color={colors.textSecondary} />
                            <Text style={styles.shareBtnText}>Save</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={[styles.shareBtn, shareCaptureBusy && styles.shareBtnDisabled]}
                            onPress={onShareRating}
                            activeOpacity={0.8}
                            disabled={shareCaptureBusy}
                        >
                            <Ionicons name="share-outline" size={17} color={colors.textSecondary} />
                            <Text style={styles.shareBtnText}>Share</Text>
                        </TouchableOpacity>
                    </View>
                ) : null}

                {/* ── Paywall teaser ── */}
                {locked && !isProcessing ? (
                    <View style={styles.paywallTeaser}>
                        <Ionicons name="lock-closed-outline" size={18} color={colors.textMuted} style={{ marginBottom: 8 }} />
                        <Text style={styles.paywallTitle}>Unlock your full analysis</Text>
                        <Text style={styles.paywallSub}>
                            See exact scores, your archetype, potential ceiling, and a personalized improvement plan.
                        </Text>
                    </View>
                ) : null}

                {/* ── CTA ── */}
                {!viewingHistory ? (
                    <>
                        <TouchableOpacity style={styles.cta} onPress={onPrimaryCta} activeOpacity={0.85}>
                            <Text style={styles.ctaText}>
                                {locked
                                    ? 'Unlock full results'
                                    : postPay && sendbluePending
                                      ? 'Continue'
                                      : postPay
                                        ? 'Choose your programs'
                                        : 'Continue'}
                            </Text>
                            <Ionicons name={locked ? 'lock-open-outline' : 'arrow-forward'} size={17} color={colors.background} />
                        </TouchableOpacity>

                        {!locked && !postSubscriptionOnboarding ? (
                            <TouchableOpacity style={styles.skipBtn} onPress={() => navigation.navigate('Main')} activeOpacity={0.7}>
                                <Text style={styles.skipText}>Go to home</Text>
                            </TouchableOpacity>
                        ) : null}
                    </>
                ) : null}

                <Text style={styles.brandMark}>max</Text>
                <Text style={styles.disclaimer}>For general wellness only — not medical advice.</Text>
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
    scroll: { paddingHorizontal: 20, paddingTop: 48, paddingBottom: 56 },
    paywallBlurShell: { borderRadius: 8, overflow: 'hidden', backgroundColor: colors.surface, position: 'relative', alignSelf: 'stretch', width: '100%' },
    paywallFlatOverlay: { backgroundColor: 'rgba(245,245,243,0.55)' },

    /* ── Header ── */
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 },
    iconHit: { width: 36, height: 36, justifyContent: 'center' },
    headerTitle: { fontSize: 15, fontWeight: '600', color: colors.foreground, letterSpacing: 0.2 },

    /* ── Hero photo ── */
    heroPhoto: {
        alignSelf: 'center', width: 200, height: 260, borderRadius: 20,
        overflow: 'hidden', marginBottom: 24, backgroundColor: colors.surface,
    },
    heroImg: { width: '100%', height: '100%' },

    /* ── Dual scores ── */
    scoresRow: {
        flexDirection: 'row', alignItems: 'center',
        marginBottom: 14, paddingHorizontal: 4,
    },
    scoreCol: { flex: 1, alignItems: 'center' },
    scoreColLabel: {
        fontSize: 12, fontWeight: '500', color: colors.textMuted,
        letterSpacing: 0.4, marginBottom: 2,
    },
    scoreColNum: {
        fontFamily: fonts.serif, fontSize: 46, fontWeight: '700',
        color: colors.foreground, letterSpacing: -1.5, lineHeight: 52,
    },
    scoreColSep: {
        width: StyleSheet.hairlineWidth, height: 44,
        backgroundColor: colors.border, marginHorizontal: 4,
    },

    /* ── Tier ── */
    tierRow: { alignItems: 'center', marginBottom: 20 },
    tierPill: {
        paddingHorizontal: 16, paddingVertical: 5, borderRadius: borderRadius.full,
        borderWidth: 1, borderColor: colors.border,
    },
    tierPillText: {
        fontSize: 11, fontWeight: '600', color: colors.textSecondary,
        letterSpacing: 0.8, textTransform: 'uppercase',
    },

    /* ── Breakdown ── */
    breakdownSection: { marginBottom: 20 },
    breakdownHeading: {
        fontFamily: fonts.serif, fontSize: 16, fontWeight: '600',
        color: colors.foreground, letterSpacing: -0.2, marginBottom: 12,
    },
    breakdownRow: {
        flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
        paddingVertical: 12,
        borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
    },
    breakdownLabel: { fontSize: 14, fontWeight: '500', color: colors.textSecondary },
    breakdownValue: { fontFamily: fonts.serif, fontSize: 15, fontWeight: '600', color: colors.foreground },

    /* ── Modules ── */
    modsSection: { marginBottom: 20 },
    modsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    modChip: {
        paddingHorizontal: 14, paddingVertical: 7, borderRadius: borderRadius.full,
        borderWidth: 1, borderColor: colors.border,
    },
    modChipText: { fontSize: 12, fontWeight: '500', color: colors.foreground },

    /* ── Share ── */
    shareRow: { flexDirection: 'row', justifyContent: 'center', gap: 12, marginBottom: 16 },
    shareBtn: {
        flexDirection: 'row', alignItems: 'center', gap: 6,
        paddingVertical: 9, paddingHorizontal: 16,
        borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border,
    },
    shareBtnText: { fontSize: 13, fontWeight: '500', color: colors.textSecondary },
    shareBtnDisabled: { opacity: 0.4 },

    /* ── Paywall teaser ── */
    paywallTeaser: { alignItems: 'center', paddingVertical: 20, marginBottom: 4 },
    paywallTitle: { fontFamily: fonts.serif, fontSize: 18, fontWeight: '600', color: colors.foreground, letterSpacing: -0.2 },
    paywallSub: { fontSize: 13, lineHeight: 19, color: colors.textSecondary, textAlign: 'center', marginTop: 6, maxWidth: 280 },

    /* ── CTA ── */
    cta: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
        backgroundColor: colors.foreground, paddingVertical: 15, borderRadius: borderRadius.full,
    },
    ctaText: { fontSize: 15, fontWeight: '600', color: colors.background, letterSpacing: 0.2 },
    skipBtn: { alignItems: 'center', paddingVertical: 14 },
    skipText: { fontSize: 13, color: colors.textMuted, fontWeight: '500' },

    /* ── Disclaimer ── */
    brandMark: {
        fontFamily: fonts.serif,
        fontSize: 13,
        letterSpacing: 1.5,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: spacing.xl,
        opacity: 0.45,
        textTransform: 'uppercase',
    },
    disclaimer: { fontSize: 10, color: colors.textMuted, textAlign: 'center', marginTop: 6, lineHeight: 14 },

    shareCardOffscreen: { position: 'absolute', width: SHARE_CARD_WIDTH, left: -4000, top: 0, opacity: 1 },
});
