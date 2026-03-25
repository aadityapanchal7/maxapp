import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    Image,
    Platform,
    Animated,
    LayoutChangeEvent,
    Share,
    Alert,
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
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

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
            <Text style={shareCardStyles.kicker}>AI FACIAL ANALYSIS</Text>
            {frontUri ? (
                <View style={shareCardStyles.photoRing} collapsable={false}>
                    <Image
                        source={{ uri: frontUri }}
                        style={shareCardStyles.photo}
                        resizeMode="cover"
                        onLoadEnd={onShareImageEvent}
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
        ...shadows.lg,
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
        ...shadows.md,
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
});

/** Blurs only inner value content; render label outside this wrapper */
function PaywallBlurShell({ children, minHeight }: { children: React.ReactNode; minHeight?: number }) {
    return (
        <View style={[styles.paywallBlurShell, minHeight ? { minHeight } : null]}>
            {children}
            <BlurView intensity={Platform.OS === 'ios' ? 30 : 42} tint="light" style={StyleSheet.absoluteFill} />
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
                <View style={styles.track} onLayout={onTrackLayout}>
                    <Animated.View style={[styles.trackFill, { width: fillWidth }]} />
                </View>
                <Text style={styles.loadingSub}>Building your facial ratings…</Text>
            </View>
            <ActivityIndicator size="large" color={colors.foreground} style={{ marginTop: spacing.xl }} />
        </View>
    );
}

function clipProblem(s: string, maxLen: number) {
    const t = (s || '').trim();
    if (t.length <= maxLen) return t;
    return `${t.slice(0, maxLen - 1)}…`;
}

export default function FaceScanResultsScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { isPaid, refreshUser, user } = useAuth() as any;
    const postPayParam = !!(route.params as RouteParams)?.postPay;
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
            if (postPayParam) {
                try {
                    await refreshUser();
                } catch (e) {
                    console.error(e);
                }
            }
            const result = await api.getLatestScan();
            if (result?.is_unlocked) {
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
    }, [postPayParam, refreshUser]);

    useEffect(() => {
        bootstrap();
    }, [bootstrap]);

    useEffect(() => {
        if (scan?.processing_status === 'processing') {
            setProcessing(true);
            const interval = setInterval(async () => {
                try {
                    const result = await api.getLatestScan();
                    setScan(result);
                    if (result.processing_status !== 'processing') {
                        setProcessing(false);
                        clearInterval(interval);
                    }
                } catch (e) {
                    console.error(e);
                }
            }, 3000);
            return () => clearInterval(interval);
        }
    }, [scan?.processing_status]);

    const a = scan?.analysis;
    /** API sets is_unlocked from DB — fixes empty screen when JWT context lags after payment */
    const treatAsPaid = isPaid === true || scan?.is_unlocked === true;
    const locked = !treatAsPaid;
    /** After pay, user must pick programs — use server flag so CTA is correct even before Home re-pushes `postPay`. */
    const chooseProgramsFlow = !locked && postSubscriptionOnboarding;
    const postPay = postPayParam || chooseProgramsFlow;
    /** After Stripe activate we set this false so user texts the Sendblue line before continuing. */
    const sendbluePending =
        treatAsPaid &&
        (user?.onboarding as { sendblue_connect_completed?: boolean } | undefined)?.sendblue_connect_completed === false;

    const overallScore = parseOverall(a);
    const base = overallScore ?? 5;
    const rawPotential = parsePotential(a, Math.min(10, Math.round((base + 0.6) * 10) / 10));
    const ratingDisplay = clampDisplayRating(overallScore);
    const potentialDisplay = computeDisplayPotential(rawPotential, treatAsPaid, ratingDisplay);
    const appealScore = parseAppeal(a, base);
    const isProcessing = processing || scan?.processing_status === 'processing';
    const frontUri = api.resolveAttachmentUrl(scan?.images?.front);

    const pr = a?.psl_rating && typeof a.psl_rating === 'object' ? a.psl_rating : {};
    const pi = a?.profile_insights;
    const archetype =
        (typeof pr?.archetype === 'string' ? pr.archetype.trim() : '') ||
        (typeof pi?.archetype === 'string' ? pi.archetype.trim() : '');
    const pslTier = typeof pr?.psl_tier === 'string' ? pr.psl_tier.trim() : '';
    const ascensionMonths =
        typeof pr?.ascension_time_months === 'number' && !Number.isNaN(pr.ascension_time_months)
            ? pr.ascension_time_months
            : parseInt(String(pr?.ascension_time_months || '0'), 10) || 0;
    const ageScore =
        typeof pr?.age_score === 'number' && !Number.isNaN(pr.age_score)
            ? pr.age_score
            : parseInt(String(pr?.age_score || '0'), 10) || 0;
    const weakestLink = typeof pr?.weakest_link === 'string' ? pr.weakest_link.trim() : '';
    const problemsRaw: string[] = Array.isArray(pi?.problems) ? pi.problems : [];
    const focusProblems: string[] = [];
    if (weakestLink) focusProblems.push(weakestLink);
    for (const p of problemsRaw) {
        if (!p || typeof p !== 'string') continue;
        const t = p.trim();
        if (!t) continue;
        if (focusProblems.some((x) => x.toLowerCase().includes(t.slice(0, 24).toLowerCase()))) continue;
        focusProblems.push(t);
        if (focusProblems.length >= 5) break;
    }
    const suggestedMods: string[] = Array.isArray(pi?.suggested_modules) ? pi.suggested_modules : [];

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

    const headerBack = () => {
        if (postPay) {
            navigation.navigate('Main');
            return;
        }
        if (navigation.canGoBack()) navigation.goBack();
        else navigation.navigate('FeaturesIntro');
    };

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
                <View style={styles.header}>
                    <TouchableOpacity onPress={headerBack} style={styles.iconHit} hitSlop={12}>
                        <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Your results</Text>
                    <View style={styles.iconHit} />
                </View>

                <Text style={styles.kicker}>AI facial analysis</Text>

                {frontUri ? (
                    <View style={styles.photoCard}>
                        <Image source={{ uri: frontUri }} style={styles.frontPhoto} resizeMode="cover" />
                    </View>
                ) : null}

                <View style={styles.scoreRow}>
                    <View style={styles.scoreOrb}>
                        <Text style={styles.scoreOrbLabel}>Rating</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 12 }} />
                        ) : locked ? (
                            <PaywallBlurShell minHeight={72}>
                                <View style={styles.orbBlurInner}>
                                    <Text
                                        style={[
                                            styles.scoreOrbNum,
                                            ratingDisplay != null ? { color: getScoreColor(ratingColorScore) } : null,
                                        ]}
                                    >
                                        {ratingDisplay != null ? ratingDisplay.toFixed(1) : '—'}
                                    </Text>
                                    <Text style={styles.scoreOrbOut}>/10</Text>
                                </View>
                            </PaywallBlurShell>
                        ) : (
                            <>
                                <Text style={[styles.scoreOrbNum, ratingDisplay != null ? { color: getScoreColor(ratingColorScore) } : null]}>
                                    {ratingDisplay != null ? ratingDisplay.toFixed(1) : '—'}
                                </Text>
                                <Text style={styles.scoreOrbOut}>/10</Text>
                            </>
                        )}
                    </View>
                    <View style={styles.scoreOrb}>
                        <Text style={styles.scoreOrbLabel}>Potential</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 12 }} />
                        ) : locked ? (
                            <PaywallBlurShell minHeight={72}>
                                <View style={styles.orbBlurInner}>
                                    <Text style={[styles.scoreOrbNum, { color: getScoreColor(potentialDisplay) }]}>
                                        {potentialDisplay.toFixed(1)}
                                    </Text>
                                    <Text style={styles.scoreOrbOut}>/10</Text>
                                </View>
                            </PaywallBlurShell>
                        ) : (
                            <>
                                <Text style={[styles.scoreOrbNum, { color: getScoreColor(potentialDisplay) }]}>
                                    {potentialDisplay.toFixed(1)}
                                </Text>
                                <Text style={styles.scoreOrbOut}>/10</Text>
                            </>
                        )}
                    </View>
                </View>

                <View style={styles.statGrid}>
                    <View style={styles.statCell}>
                        <Text style={styles.statLabel}>Tier</Text>
                        {locked ? (
                            <PaywallBlurShell minHeight={40}>
                                <View style={styles.statBlurInner}>
                                    <Text style={styles.statValue}>{pslTier || '—'}</Text>
                                </View>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={styles.statValue}>{pslTier || '—'}</Text>
                        )}
                    </View>
                    <View style={styles.statCell}>
                        <Text style={styles.statLabel}>Appeal</Text>
                        {locked ? (
                            <PaywallBlurShell minHeight={40}>
                                <View style={styles.statBlurInner}>
                                    <Text style={[styles.statValue, { color: getScoreColor(appealScore) }]}>
                                        {appealScore.toFixed(1)}/10
                                    </Text>
                                </View>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={[styles.statValue, { color: getScoreColor(appealScore) }]}>{appealScore.toFixed(1)}/10</Text>
                        )}
                    </View>
                    <View style={styles.statCell}>
                        <Text style={styles.statLabel}>Archetype</Text>
                        {locked ? (
                            <PaywallBlurShell minHeight={40}>
                                <View style={styles.statBlurInner}>
                                    <Text style={styles.statValue}>{archetype || '—'}</Text>
                                </View>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={styles.statValue}>{archetype || '—'}</Text>
                        )}
                    </View>
                    <View style={styles.statCell}>
                        <Text style={styles.statLabel}>Ascension time</Text>
                        {locked ? (
                            <PaywallBlurShell minHeight={40}>
                                <View style={styles.statBlurInner}>
                                    <Text style={styles.statValue}>{ascensionLabelText}</Text>
                                </View>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={styles.statValue}>{ascensionLabelText}</Text>
                        )}
                    </View>
                    <View style={[styles.statCell, styles.statCellWide]}>
                        <Text style={styles.statLabel}>Facial age (look)</Text>
                        {locked ? (
                            <PaywallBlurShell minHeight={40}>
                                <View style={styles.statBlurInner}>
                                    <Text style={styles.statValue}>{ageScore > 0 ? `${ageScore}` : '—'}</Text>
                                </View>
                            </PaywallBlurShell>
                        ) : (
                            <Text style={styles.statValue}>{ageScore > 0 ? `${ageScore}` : '—'}</Text>
                        )}
                    </View>
                </View>

                <Text style={styles.sectionKicker}>Focus</Text>
                {locked ? (
                    <View style={styles.insightCard}>
                        <PaywallBlurShell minHeight={Math.max(120, 24 + focusProblems.length * 26)}>
                            <View style={styles.focusBlurInner}>
                                {focusProblems.length > 0 ? (
                                    focusProblems.map((p, i) => (
                                        <Text key={i} style={styles.bullet}>
                                            • {clipProblem(p, 96)}
                                        </Text>
                                    ))
                                ) : (
                                    <Text style={styles.bodyText}>No major focus flags.</Text>
                                )}
                            </View>
                        </PaywallBlurShell>
                    </View>
                ) : (
                    <View style={styles.insightCard}>
                        {focusProblems.length > 0 ? (
                            focusProblems.map((p, i) => (
                                <Text key={i} style={styles.bullet}>
                                    • {clipProblem(p, 96)}
                                </Text>
                            ))
                        ) : (
                            <Text style={styles.bodyText}>No major focus flags.</Text>
                        )}
                    </View>
                )}

                {!locked ? (
                    <>
                        <Text style={styles.sectionKicker}>Suggested modules</Text>
                        <View style={styles.insightCard}>
                            {suggestedMods.length > 0 ? (
                                <View style={styles.moduleChips}>
                                    {suggestedMods.map((m, i) => (
                                        <View key={i} style={styles.moduleChip}>
                                            <Text style={styles.moduleChipText}>{m}</Text>
                                        </View>
                                    ))}
                                </View>
                            ) : (
                                <Text style={styles.bodyText}>Based on your scan and goals.</Text>
                            )}
                        </View>
                    </>
                ) : null}

                {!locked && !isProcessing ? (
                    <View style={styles.shareRow}>
                        <TouchableOpacity
                            style={[styles.shareBtn, shareCaptureBusy && styles.shareBtnDisabled]}
                            onPress={onSaveScanPhoto}
                            activeOpacity={0.85}
                            disabled={shareCaptureBusy}
                        >
                            <Ionicons name="download-outline" size={20} color={colors.foreground} />
                            <Text style={styles.shareBtnText}>Save to photos</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={[styles.shareBtn, shareCaptureBusy && styles.shareBtnDisabled]}
                            onPress={onShareRating}
                            activeOpacity={0.85}
                            disabled={shareCaptureBusy}
                        >
                            <Ionicons name="share-social-outline" size={20} color={colors.foreground} />
                            <Text style={styles.shareBtnText}>Share my rating</Text>
                        </TouchableOpacity>
                    </View>
                ) : null}

                <TouchableOpacity style={styles.cta} onPress={onPrimaryCta} activeOpacity={0.88}>
                    <Text style={styles.ctaText}>
                        {locked ? 'Unlock plan' : postPay ? 'Choose your programs' : 'Continue'}
                    </Text>
                    <Ionicons name={locked ? 'lock-open-outline' : 'arrow-forward'} size={20} color={colors.background} />
                </TouchableOpacity>

                {!locked && !postPay ? (
                    <TouchableOpacity style={styles.secondaryCta} onPress={() => navigation.navigate('Main')} activeOpacity={0.7}>
                        <Text style={styles.secondaryCtaText}>Skip to home</Text>
                    </TouchableOpacity>
                ) : null}

                {locked ? <Text style={styles.priceHint}>Full analysis with membership · $9.99/mo</Text> : null}
            </ScrollView>

            {!locked && !isProcessing && Platform.OS !== 'web' ? (
                <View style={styles.shareCardOffscreen} pointerEvents="none" collapsable={false}>
                    <ResultsRatingShareCard
                        cardRef={shareCardRef}
                        frontUri={frontUri}
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
    loadingRoot: { alignItems: 'stretch', paddingHorizontal: spacing.lg },
    fetchingRoot: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.xl },
    fetchErrorText: { ...typography.body, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.md },
    fetchRetryBtn: {
        backgroundColor: colors.foreground,
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.md,
        borderRadius: borderRadius.full,
    },
    fetchRetryText: { ...typography.button, color: colors.background },
    loadingHeader: { marginBottom: spacing.md },
    loadingSub: { fontSize: 14, color: colors.textSecondary, marginTop: spacing.sm },
    progressTopRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: 10,
    },
    progressTitle: { ...typography.h3, fontSize: 20 },
    progressPct: { fontSize: 22, fontWeight: '800', color: colors.foreground, letterSpacing: -0.5 },
    track: {
        height: 10,
        borderRadius: borderRadius.full,
        backgroundColor: colors.borderLight,
        overflow: 'hidden',
    },
    trackFill: {
        height: '100%',
        borderRadius: borderRadius.full,
        backgroundColor: colors.foreground,
    },
    scroll: { paddingHorizontal: spacing.lg, paddingTop: 56, paddingBottom: 48 },
    paywallBlurShell: {
        borderRadius: borderRadius.lg,
        overflow: 'hidden',
        backgroundColor: colors.borderLight,
        position: 'relative',
        alignSelf: 'stretch',
        width: '100%',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.md,
    },
    iconHit: { width: 40, height: 40, justifyContent: 'center' },
    headerTitle: { ...typography.h2 },
    kicker: { ...typography.label, color: colors.textMuted, textAlign: 'center', marginBottom: spacing.md },
    photoCard: {
        alignSelf: 'center',
        width: 200,
        height: 200,
        borderRadius: 100,
        overflow: 'hidden',
        borderWidth: 3,
        borderColor: colors.border,
        marginBottom: spacing.xl,
        ...shadows.lg,
    },
    photoCardPaywall: {
        alignSelf: 'center',
        width: 132,
        height: 132,
        borderRadius: 66,
        overflow: 'hidden',
        borderWidth: 2,
        borderColor: colors.border,
        marginBottom: spacing.md,
        ...shadows.md,
    },
    frontPhoto: { width: '100%', height: '100%' },
    frontPhotoPaywall: { width: '100%', height: '100%' },
    scoreRow: { flexDirection: 'row', justifyContent: 'center', gap: spacing.lg, marginBottom: spacing.lg },
    scoreOrb: {
        width: 130,
        height: 130,
        borderRadius: 65,
        backgroundColor: colors.card,
        borderWidth: 2,
        borderColor: colors.borderLight,
        alignItems: 'center',
        justifyContent: 'center',
        ...shadows.md,
    },
    scoreOrbLabel: { ...typography.label, fontSize: 9, marginBottom: 4, textAlign: 'center', paddingHorizontal: 4 },
    scoreOrbNum: { fontSize: 36, fontWeight: '800' },
    scoreOrbOut: { fontSize: 14, fontWeight: '600', color: colors.textMuted },
    orbBlurInner: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        justifyContent: 'center',
        paddingVertical: 8,
        gap: 2,
        minHeight: 56,
    },
    statBlurInner: {
        justifyContent: 'center',
        minHeight: 22,
        paddingVertical: 2,
    },
    focusBlurInner: {
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.xs,
    },
    statGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: spacing.sm,
        marginBottom: spacing.lg,
        justifyContent: 'space-between',
    },
    statCell: {
        width: '47%',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        padding: spacing.sm,
        borderWidth: 1,
        borderColor: colors.border,
    },
    statCellWide: { width: '100%' },
    statLabel: { fontSize: 10, fontWeight: '700', color: colors.textMuted, marginBottom: 4, letterSpacing: 0.6 },
    statValue: { fontSize: 15, fontWeight: '700', color: colors.foreground },
    sectionKicker: {
        ...typography.label,
        color: colors.textMuted,
        marginBottom: spacing.md,
        letterSpacing: 1,
    },
    sectionKickerTight: {
        ...typography.label,
        fontSize: 10,
        color: colors.textMuted,
        marginBottom: spacing.sm,
        marginTop: spacing.xs,
        letterSpacing: 1,
    },
    insightCard: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.xl,
        padding: spacing.md,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    bodyText: { fontSize: 14, color: colors.textSecondary, lineHeight: 21 },
    bullet: { fontSize: 14, color: colors.textSecondary, marginBottom: 6, lineHeight: 20 },
    moduleChips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    moduleChip: {
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: borderRadius.full,
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
    },
    moduleChipText: { fontSize: 12, fontWeight: '600', color: colors.foreground },
    cta: {
        marginTop: spacing.lg,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: 16,
        borderRadius: borderRadius.full,
        ...shadows.md,
    },
    ctaText: { ...typography.button, color: colors.background, fontSize: 16 },
    secondaryCta: { alignItems: 'center', paddingVertical: spacing.md },
    secondaryCtaText: { fontSize: 14, color: colors.textMuted, fontWeight: '600' },
    priceHint: { textAlign: 'center', fontSize: 12, color: colors.textMuted, marginTop: spacing.sm },
    shareRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg },
    shareBtn: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        paddingVertical: 14,
        paddingHorizontal: spacing.sm,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        ...shadows.sm,
    },
    shareBtnText: { fontSize: 13, fontWeight: '600', color: colors.foreground, flexShrink: 1 },
    shareBtnDisabled: { opacity: 0.55 },
    shareCardOffscreen: {
        position: 'absolute',
        width: SHARE_CARD_WIDTH,
        left: -4000,
        top: 0,
        opacity: 1,
    },
});
