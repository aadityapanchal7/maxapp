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
} from 'react-native';
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

type RouteParams = { postPay?: boolean };

const LOCK_PLACEHOLDER_LINES = ['████████████████', '█████████████', '███████████████'];

function LockedBlurBlock({ compact }: { compact?: boolean }) {
    return (
        <View style={[styles.lockedBlockInner, compact && styles.lockedBlockInnerCompact]}>
            {LOCK_PLACEHOLDER_LINES.map((line, i) => (
                <Text key={i} style={styles.placeholderLine} numberOfLines={1}>
                    {line}
                </Text>
            ))}
            <BlurView intensity={Platform.OS === 'ios' ? 28 : 44} tint="light" style={StyleSheet.absoluteFill}>
                <View style={styles.lockOverlay}>
                    <Ionicons name="lock-closed" size={compact ? 16 : 20} color={colors.foreground} />
                </View>
            </BlurView>
        </View>
    );
}

/** Blurs only inner value content; render label outside this wrapper */
function PaywallBlurShell({ children, minHeight }: { children: React.ReactNode; minHeight?: number }) {
    return (
        <View style={[styles.paywallBlurShell, minHeight ? { minHeight } : null]}>
            {children}
            <BlurView intensity={Platform.OS === 'ios' ? 30 : 42} tint="light" style={StyleSheet.absoluteFill} />
        </View>
    );
}

function InsightRow({
    label,
    locked,
    children,
    compact,
}: {
    label: string;
    locked: boolean;
    children?: React.ReactNode;
    compact?: boolean;
}) {
    return (
        <View style={[styles.insightCard, compact && styles.insightCardCompact]}>
            <Text style={[styles.insightLabel, compact && styles.insightLabelCompact]}>{label}</Text>
            {locked ? <LockedBlurBlock compact={compact} /> : <View style={styles.insightBody}>{children}</View>}
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

const PSL_FEATURE_ROWS: { key: string; label: string }[] = [
    { key: 'eyes', label: 'Eyes' },
    { key: 'jaw', label: 'Jaw' },
    { key: 'cheekbones', label: 'Cheekbones' },
    { key: 'chin', label: 'Chin' },
    { key: 'nose', label: 'Nose' },
    { key: 'lips', label: 'Lips' },
    { key: 'brow_ridge', label: 'Brow ridge' },
    { key: 'skin', label: 'Skin' },
    { key: 'hairline', label: 'Hairline' },
    { key: 'symmetry', label: 'Symmetry' },
];

function clipProblem(s: string, maxLen: number) {
    const t = (s || '').trim();
    if (t.length <= maxLen) return t;
    return `${t.slice(0, maxLen - 1)}…`;
}

export default function FaceScanResultsScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { isPaid, refreshUser } = useAuth() as any;
    const postPay = !!(route.params as RouteParams)?.postPay;

    const [scan, setScan] = useState<any>(null);
    /** First GET /latest in flight — use a small spinner, not the full analyzing UI. */
    const [hydrating, setHydrating] = useState(true);
    const [processing, setProcessing] = useState(false);

    const bootstrap = useCallback(async () => {
        setHydrating(true);
        try {
            if (postPay) {
                try {
                    await refreshUser();
                } catch (e) {
                    console.error(e);
                }
            }
            const result = await api.getLatestScan();
            setScan(result);
        } catch (e) {
            console.error(e);
            setScan(null);
        } finally {
            setHydrating(false);
        }
    }, [postPay, refreshUser]);

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
    const paywallMode = locked && !postPay;

    const overallScore = parseOverall(a);
    const base = overallScore ?? 5;
    const potentialScore = parsePotential(a, Math.min(10, Math.round((base + 0.6) * 10) / 10));
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
    const auraTags: string[] = Array.isArray(pr?.aura_tags)
        ? pr.aura_tags.filter((t: unknown) => typeof t === 'string' && t.trim()).map((t: string) => t.trim())
        : [];
    const featureScores = pr?.feature_scores && typeof pr.feature_scores === 'object' ? pr.feature_scores : {};
    const proportions = pr?.proportions && typeof pr.proportions === 'object' ? pr.proportions : {};
    const sideProfile = pr?.side_profile && typeof pr.side_profile === 'object' ? pr.side_profile : {};
    const mogPct = typeof pr?.mog_percentile === 'number' ? pr.mog_percentile : parseInt(String(pr?.mog_percentile || ''), 10);
    const mascIdx = typeof pr?.masculinity_index === 'number' ? pr.masculinity_index : parseFloat(String(pr?.masculinity_index || ''));
    const glowUp = typeof pr?.glow_up_potential === 'number' ? pr.glow_up_potential : parseInt(String(pr?.glow_up_potential || ''), 10);

    const goPayment = () => navigation.navigate('Payment');

    const onPrimaryCta = async () => {
        if (locked) {
            goPayment();
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

    if (paywallMode) {
        const ratingDisplay = overallScore != null ? overallScore.toFixed(1) : '—';
        const ratingColor = overallScore != null ? getScoreColor(overallScore) : colors.foreground;
        const potColor = getScoreColor(potentialScore);

        return (
            <View style={styles.root}>
                <ScrollView
                    contentContainerStyle={styles.paywallScroll}
                    showsVerticalScrollIndicator={false}
                    keyboardShouldPersistTaps="handled"
                >
                    <View style={styles.headerTight}>
                        <TouchableOpacity onPress={headerBack} style={styles.iconHit} hitSlop={12}>
                            <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                        </TouchableOpacity>
                        <Text style={styles.headerTitleTight}>Your results</Text>
                        <View style={styles.iconHit} />
                    </View>

                    <Text style={styles.kickerTight}>AI facial analysis</Text>

                    {frontUri ? (
                        <View style={styles.photoCardPaywall}>
                            <Image source={{ uri: frontUri }} style={styles.frontPhotoPaywall} resizeMode="cover" />
                        </View>
                    ) : null}

                    <View style={styles.paywallCard}>
                        <View style={styles.paywallBlurSectionInner}>
                            <View style={styles.paywallScoresRow}>
                                <View style={styles.paywallScoreCol}>
                                    <Text style={styles.paywallLabelSharp}>PSL score</Text>
                                    <PaywallBlurShell minHeight={56}>
                                        <View style={styles.paywallValueInner}>
                                            {isProcessing ? (
                                                <ActivityIndicator color={colors.foreground} />
                                            ) : (
                                                <>
                                                    <Text style={[styles.paywallScoreNum, { color: ratingColor }]}>{ratingDisplay}</Text>
                                                    <Text style={styles.paywallScoreOut}>/10</Text>
                                                </>
                                            )}
                                        </View>
                                    </PaywallBlurShell>
                                </View>
                                <View style={styles.paywallScoreCol}>
                                    <Text style={styles.paywallLabelSharp}>Potential (PSL ceiling)</Text>
                                    <PaywallBlurShell minHeight={56}>
                                        <View style={styles.paywallValueInner}>
                                            {isProcessing ? (
                                                <ActivityIndicator color={colors.foreground} />
                                            ) : (
                                                <>
                                                    <Text style={[styles.paywallScoreNum, { color: potColor }]}>
                                                        {potentialScore.toFixed(1)}
                                                    </Text>
                                                    <Text style={styles.paywallScoreOut}>/10</Text>
                                                </>
                                            )}
                                        </View>
                                    </PaywallBlurShell>
                                </View>
                            </View>

                            <Text style={[styles.paywallLabelSharp, { marginTop: spacing.sm }]}>PSL ranking</Text>
                            <PaywallBlurShell minHeight={44}>
                                <View style={styles.paywallBlurbInner}>
                                    <Text style={styles.paywallBlurbHiddenText} numberOfLines={1}>
                                        {pslTier || '████████'}
                                    </Text>
                                </View>
                            </PaywallBlurShell>

                            <Text style={[styles.paywallLabelSharp, { marginTop: spacing.sm }]}>Appeal</Text>
                            <PaywallBlurShell minHeight={44}>
                                <View style={styles.paywallValueInner}>
                                    {isProcessing ? (
                                        <ActivityIndicator color={colors.foreground} />
                                    ) : (
                                        <>
                                            <Text style={[styles.paywallScoreNum, { fontSize: 22 }, { color: getScoreColor(appealScore) }]}>
                                                {appealScore.toFixed(1)}
                                            </Text>
                                            <Text style={styles.paywallScoreOut}>/10</Text>
                                        </>
                                    )}
                                </View>
                            </PaywallBlurShell>

                            <Text style={[styles.paywallLabelSharp, { marginTop: spacing.sm }]}>Archetype</Text>
                            <PaywallBlurShell minHeight={44}>
                                <View style={styles.paywallBlurbInner}>
                                    <Text style={styles.paywallBlurbHiddenText} numberOfLines={2}>
                                        {archetype || '████████████'}
                                    </Text>
                                </View>
                            </PaywallBlurShell>

                            <Text style={[styles.paywallLabelSharp, { marginTop: spacing.sm }]}>Approx. ascension time</Text>
                            <PaywallBlurShell minHeight={40}>
                                <View style={styles.paywallBlurbInner}>
                                    <Text style={styles.paywallBlurbHiddenText}>
                                        {!isProcessing && ascensionMonths > 0
                                            ? `~${ascensionMonths} mo`
                                            : '~██ months'}
                                    </Text>
                                </View>
                            </PaywallBlurShell>

                            <Text style={[styles.paywallLabelSharp, { marginTop: spacing.sm }]}>Facial age (look)</Text>
                            <PaywallBlurShell minHeight={40}>
                                <View style={styles.paywallBlurbInner}>
                                    <Text style={styles.paywallBlurbHiddenText}>
                                        {!isProcessing && ageScore > 0 ? `${ageScore}` : '██'}
                                    </Text>
                                </View>
                            </PaywallBlurShell>

                            <Text style={styles.sectionKickerTightSharp}>Feature breakdown</Text>
                            {PSL_FEATURE_ROWS.map((row) => (
                                <View key={row.key} style={styles.paywallBreakRow}>
                                    <Text style={styles.paywallLabelSharp}>{row.label}</Text>
                                    <PaywallBlurShell minHeight={44}>
                                        <View style={styles.paywallBarsInner}>
                                            <View style={styles.paywallTeaserBar} />
                                            <View style={[styles.paywallTeaserBar, { width: '72%' }]} />
                                        </View>
                                    </PaywallBlurShell>
                                </View>
                            ))}

                            <TouchableOpacity style={styles.unlockInline} onPress={goPayment} activeOpacity={0.88}>
                                <Ionicons name="lock-open-outline" size={22} color={colors.background} />
                                <Text style={styles.unlockInlineText}>Unlock plan</Text>
                            </TouchableOpacity>
                            <Text style={styles.paywallPriceInline}>Full analysis · $9.99/mo</Text>
                        </View>
                    </View>

                    <View style={{ height: spacing.lg }} />
                </ScrollView>
            </View>
        );
    }

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
                        <Text style={styles.scoreOrbLabel}>PSL score</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 12 }} />
                        ) : (
                            <>
                                <Text style={[styles.scoreOrbNum, overallScore != null ? { color: getScoreColor(overallScore) } : null]}>
                                    {overallScore != null ? overallScore.toFixed(1) : '—'}
                                </Text>
                                <Text style={styles.scoreOrbOut}>/10</Text>
                            </>
                        )}
                    </View>
                    <View style={styles.scoreOrb}>
                        <Text style={styles.scoreOrbLabel}>Potential</Text>
                        {isProcessing ? (
                            <ActivityIndicator color={colors.foreground} style={{ marginVertical: 12 }} />
                        ) : (
                            <>
                                <Text style={[styles.scoreOrbNum, { color: getScoreColor(potentialScore) }]}>{potentialScore.toFixed(1)}</Text>
                                <Text style={styles.scoreOrbOut}>/10</Text>
                            </>
                        )}
                    </View>
                </View>

                {locked ? (
                    <>
                        <InsightRow label="PSL ranking" locked compact />
                        <InsightRow label="Appeal" locked compact />
                        <InsightRow label="Archetype" locked compact />
                        <InsightRow label="Approx. ascension time" locked compact />
                        <InsightRow label="Facial age (look)" locked compact />
                    </>
                ) : (
                    <View style={styles.statGrid}>
                        <View style={styles.statCell}>
                            <Text style={styles.statLabel}>PSL ranking</Text>
                            <Text style={styles.statValue}>{pslTier || '—'}</Text>
                        </View>
                        <View style={styles.statCell}>
                            <Text style={styles.statLabel}>Appeal</Text>
                            <Text style={[styles.statValue, { color: getScoreColor(appealScore) }]}>{appealScore.toFixed(1)}/10</Text>
                        </View>
                        <View style={styles.statCell}>
                            <Text style={styles.statLabel}>Archetype</Text>
                            <Text style={styles.statValue}>{archetype || '—'}</Text>
                        </View>
                        <View style={styles.statCell}>
                            <Text style={styles.statLabel}>Ascension (~mo)</Text>
                            <Text style={styles.statValue}>{ascensionMonths > 0 ? `~${ascensionMonths}` : '—'}</Text>
                        </View>
                        <View style={[styles.statCell, styles.statCellWide]}>
                            <Text style={styles.statLabel}>Facial age (look)</Text>
                            <Text style={styles.statValue}>{ageScore > 0 ? `${ageScore}` : '—'}</Text>
                        </View>
                    </View>
                )}

                {!locked ? (
                    <>
                        <Text style={styles.sectionKicker}>Focus</Text>
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

                        <Text style={styles.sectionKicker}>Feature breakdown</Text>
                        {PSL_FEATURE_ROWS.some((r) => {
                            const c = featureScores[r.key];
                            return (
                                c &&
                                (c.score != null ||
                                    (typeof c.tag === 'string' && c.tag.trim()) ||
                                    (typeof c.notes === 'string' && c.notes.trim()))
                            );
                        }) ? (
                            PSL_FEATURE_ROWS.map(({ key, label }) => {
                                const cell = featureScores[key] || {};
                                const sc = cell.score != null && cell.score !== '' ? Number(cell.score) : null;
                                const tag = typeof cell.tag === 'string' ? cell.tag : '';
                                const notes = typeof cell.notes === 'string' ? cell.notes : '';
                                return (
                                    <View key={key} style={styles.featureBlock}>
                                        <View style={styles.featureBlockHead}>
                                            <Text style={styles.featureBlockTitle}>{label}</Text>
                                            {sc != null && !Number.isNaN(sc) ? (
                                                <Text style={[styles.featureBlockScore, { color: getScoreColor(sc) }]}>
                                                    {sc.toFixed(1)}
                                                </Text>
                                            ) : null}
                                        </View>
                                        {tag ? <Text style={styles.featureTag}>{tag}</Text> : null}
                                        {notes ? <Text style={styles.featureNotes}>{clipProblem(notes, 140)}</Text> : null}
                                    </View>
                                );
                            })
                        ) : Array.isArray(a?.umax_metrics) && a.umax_metrics.length > 0 ? (
                            a.umax_metrics.map((row: any, i: number) => (
                                <View key={row.id || i} style={styles.featureBlock}>
                                    <View style={styles.featureBlockHead}>
                                        <Text style={styles.featureBlockTitle}>{row.label || row.id}</Text>
                                        {row.score != null ? (
                                            <Text style={[styles.featureBlockScore, { color: getScoreColor(Number(row.score)) }]}>
                                                {Number(row.score).toFixed(1)}
                                            </Text>
                                        ) : null}
                                    </View>
                                    {row.summary ? (
                                        <Text style={styles.featureNotes}>{clipProblem(String(row.summary), 140)}</Text>
                                    ) : null}
                                </View>
                            ))
                        ) : (
                            <View style={styles.insightCard}>
                                <Text style={styles.bodyText}>No per-feature breakdown for this scan.</Text>
                            </View>
                        )}

                        <Text style={styles.sectionKicker}>Proportions & side profile</Text>
                        <View style={styles.insightCard}>
                            {proportions?.facial_thirds ? (
                                <Text style={styles.bodyText}>Thirds: {String(proportions.facial_thirds)}</Text>
                            ) : null}
                            {proportions?.golden_ratio_percent != null && Number(proportions.golden_ratio_percent) > 0 ? (
                                <Text style={styles.bodyText}>
                                    Golden ratio proximity: {Number(proportions.golden_ratio_percent).toFixed(0)}%
                                </Text>
                            ) : null}
                            {proportions?.fwhr != null && Number(proportions.fwhr) > 0 ? (
                                <Text style={styles.bodyText}>FWHR: {Number(proportions.fwhr).toFixed(2)}</Text>
                            ) : null}
                            {proportions?.bigonial_bizygomatic_ratio != null && Number(proportions.bigonial_bizygomatic_ratio) > 0 ? (
                                <Text style={styles.bodyText}>
                                    Bigonial / bizygomatic: {Number(proportions.bigonial_bizygomatic_ratio).toFixed(2)}
                                </Text>
                            ) : null}
                            {sideProfile && Object.keys(sideProfile).length > 0 ? (
                                <Text style={[styles.bodyText, { marginTop: spacing.sm }]}>
                                    {Object.entries(sideProfile)
                                        .map(([k, v]) => `${k}: ${typeof v === 'boolean' ? (v ? 'yes' : 'no') : String(v)}`)
                                        .join(' · ')}
                                </Text>
                            ) : null}
                            {!(
                                proportions?.facial_thirds ||
                                (proportions?.golden_ratio_percent != null && Number(proportions.golden_ratio_percent) > 0) ||
                                (proportions?.fwhr != null && Number(proportions.fwhr) > 0) ||
                                (proportions?.bigonial_bizygomatic_ratio != null &&
                                    Number(proportions.bigonial_bizygomatic_ratio) > 0) ||
                                (sideProfile && Object.keys(sideProfile).length > 0)
                            ) ? (
                                <Text style={styles.bodyText}>No proportion / profile detail for this scan.</Text>
                            ) : null}
                        </View>

                        {auraTags.length > 0 ? (
                            <>
                                <Text style={styles.sectionKicker}>Aura tags</Text>
                                <View style={styles.moduleChips}>
                                    {auraTags.map((t, i) => (
                                        <View key={i} style={styles.moduleChip}>
                                            <Text style={styles.moduleChipText}>{t}</Text>
                                        </View>
                                    ))}
                                </View>
                            </>
                        ) : null}

                        {!Number.isNaN(mascIdx) && mogPct > 0 && !Number.isNaN(glowUp) ? (
                            <Text style={styles.mutedStatLine}>
                                Masculinity index {mascIdx.toFixed(1)}/10 · Mog ~{mogPct}%ile · Glow-up room {glowUp}/100
                            </Text>
                        ) : null}

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

                {locked ? (
                    <>
                        <Text style={styles.sectionKicker}>Full breakdown</Text>
                        <InsightRow label="Focus areas" locked>
                            {null}
                        </InsightRow>
                        <InsightRow label="Suggested modules" locked>
                            {null}
                        </InsightRow>
                    </>
                ) : null}

                <TouchableOpacity style={styles.cta} onPress={onPrimaryCta} activeOpacity={0.88}>
                    <Text style={styles.ctaText}>{locked ? 'Unlock plan' : postPay ? 'Choose your programs' : 'Continue'}</Text>
                    <Ionicons name={locked ? 'lock-open-outline' : 'arrow-forward'} size={20} color={colors.background} />
                </TouchableOpacity>

                {!locked && !postPay ? (
                    <TouchableOpacity style={styles.secondaryCta} onPress={() => navigation.navigate('Main')} activeOpacity={0.7}>
                        <Text style={styles.secondaryCtaText}>Skip to home</Text>
                    </TouchableOpacity>
                ) : null}

                {locked ? <Text style={styles.priceHint}>Full analysis with membership · $9.99/mo</Text> : null}
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    center: { justifyContent: 'center', alignItems: 'center' },
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
    paywallScroll: {
        paddingHorizontal: spacing.md,
        paddingTop: 48,
        paddingBottom: 32,
    },
    paywallCard: {
        marginTop: spacing.sm,
        borderRadius: borderRadius.xl,
        overflow: 'hidden',
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
    },
    paywallBlurSectionInner: {
        paddingHorizontal: spacing.md,
        paddingTop: spacing.md,
        paddingBottom: spacing.md,
    },
    paywallBlurShell: {
        borderRadius: borderRadius.lg,
        overflow: 'hidden',
        backgroundColor: colors.borderLight,
        position: 'relative',
    },
    paywallLabelSharp: {
        fontSize: 12,
        fontWeight: '700',
        color: colors.foreground,
        marginBottom: 6,
        letterSpacing: 0.2,
    },
    paywallScoresRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xs },
    paywallScoreCol: { flex: 1, minWidth: 0 },
    paywallValueInner: {
        minHeight: 52,
        flexDirection: 'row',
        alignItems: 'flex-end',
        justifyContent: 'center',
        paddingVertical: 10,
        gap: 2,
    },
    paywallScoreNum: { fontSize: 26, fontWeight: '800' },
    paywallScoreOut: { fontSize: 12, fontWeight: '600', color: colors.textMuted, paddingBottom: 4 },
    paywallBlurbInner: { padding: spacing.sm },
    paywallBlurbHiddenText: { fontSize: 13, color: colors.textSecondary, lineHeight: 19 },
    paywallBarsInner: { padding: spacing.sm, gap: 6, justifyContent: 'center', flex: 1 },
    paywallBreakRow: { marginBottom: spacing.sm },
    paywallTeaserBar: {
        height: 8,
        borderRadius: 4,
        backgroundColor: colors.card,
        width: '100%',
    },
    sectionKickerTightSharp: {
        fontSize: 10,
        fontWeight: '700',
        color: colors.textMuted,
        marginTop: spacing.md,
        marginBottom: spacing.sm,
        letterSpacing: 1,
    },
    unlockInline: {
        marginTop: spacing.lg,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        borderRadius: borderRadius.full,
        ...shadows.md,
    },
    unlockInlineText: { ...typography.button, color: colors.background, fontSize: 16 },
    paywallPriceInline: {
        textAlign: 'center',
        fontSize: 12,
        color: colors.textMuted,
        marginTop: spacing.sm,
        fontWeight: '600',
    },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.md,
    },
    headerTight: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.xs,
    },
    iconHit: { width: 40, height: 40, justifyContent: 'center' },
    headerTitle: { ...typography.h2 },
    headerTitleTight: { ...typography.h2, fontSize: 20 },
    kicker: { ...typography.label, color: colors.textMuted, textAlign: 'center', marginBottom: spacing.md },
    kickerTight: {
        ...typography.label,
        fontSize: 10,
        color: colors.textMuted,
        textAlign: 'center',
        marginBottom: spacing.sm,
    },
    muted: { marginTop: spacing.md, color: colors.textSecondary, fontSize: 14 },
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
    featureBlock: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        marginBottom: spacing.sm,
        borderWidth: 1,
        borderColor: colors.border,
    },
    featureBlockHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
    featureBlockTitle: { fontSize: 15, fontWeight: '700', color: colors.foreground },
    featureBlockScore: { fontSize: 18, fontWeight: '800' },
    featureTag: { fontSize: 12, fontWeight: '600', color: colors.textSecondary, marginBottom: 4 },
    featureNotes: { fontSize: 13, color: colors.textSecondary, lineHeight: 19 },
    mutedStatLine: {
        fontSize: 12,
        color: colors.textMuted,
        marginBottom: spacing.md,
        lineHeight: 18,
        fontWeight: '600',
    },
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
    insightCardCompact: {
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.sm,
        marginBottom: spacing.sm,
        borderRadius: borderRadius.lg,
    },
    insightLabel: { fontSize: 12, fontWeight: '700', color: colors.textMuted, marginBottom: spacing.sm, letterSpacing: 0.8 },
    insightLabelCompact: { fontSize: 11, marginBottom: 6 },
    insightBody: { minHeight: 48 },
    bodyText: { fontSize: 14, color: colors.textSecondary, lineHeight: 21 },
    archetypeText: { fontSize: 18, fontWeight: '700', color: colors.foreground },
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
    lockedBlockInner: {
        minHeight: 72,
        borderRadius: borderRadius.md,
        overflow: 'hidden',
        backgroundColor: colors.borderLight,
        justifyContent: 'center',
        paddingHorizontal: spacing.md,
    },
    lockedBlockInnerCompact: {
        minHeight: 52,
        paddingVertical: 4,
        paddingHorizontal: spacing.sm,
    },
    placeholderLine: {
        fontSize: 10,
        color: colors.border,
        letterSpacing: 0.5,
        marginVertical: 2,
    },
    lockOverlay: {
        ...StyleSheet.absoluteFillObject,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: 'rgba(255,255,255,0.3)',
    },
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
});
