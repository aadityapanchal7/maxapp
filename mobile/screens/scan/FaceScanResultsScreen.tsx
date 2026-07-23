import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    Platform,
    Animated,
    Easing,
    LayoutChangeEvent,
    Share,
    AppState,
    BackHandler,
    useWindowDimensions,
    Pressable,
} from 'react-native'
import { Alert } from '../../components/InAppAlert';
import Svg, { Circle, Defs, LinearGradient as SvgLinearGradient, Stop } from 'react-native-svg';
import * as MediaLibrary from 'expo-media-library';
import * as Sharing from 'expo-sharing';
import { captureRef } from 'react-native-view-shot';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { LiquidGlassFill } from '../../components/glass/LiquidGlass';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { clearFaceScanDraft, clearPendingFaceScanSubmit } from '../../lib/faceScanDraft';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { useFlag } from '../../constants/featureFlags';
import { archetypeLine } from '../../lib/personalization';
import { CachedImage } from '../../components/CachedImage';
import { userHasSignupPhone } from '../../utils/userPhone';
import { getMaxxDisplayLabel } from '../../utils/maxxDisplay';
import MosaicGrid, { type MosaicTile } from '../../components/scan/MosaicGrid';
import AnalyzingScreen from './AnalyzingScreen';
import { track } from '../../lib/analytics';

function formatSuggestedModuleTitle(id: string): string {
    const t = getMaxxDisplayLabel({ id }).trim();
    if (!t) return id;
    return t.charAt(0).toUpperCase() + t.slice(1);
}

function coerceAnalysisObject(analysis: unknown): any {
    if (analysis == null) return null;
    if (typeof analysis === 'string') {
        try {
            const p = JSON.parse(analysis);
            return p !== null && typeof p === 'object' ? p : null;
        } catch { return null; }
    }
    return typeof analysis === 'object' ? analysis : null;
}

function inferPslTierFromScore(score: number | null, isFirstScan = false): string {
    if (score == null || Number.isNaN(score)) return '';
    const s = Math.max(0, Math.min(10, score));
    let label: string;
    if (s < 3.0) label = 'Sub 3';
    else if (s < 5.0) label = 'Sub 5';
    else if (s < 6.0) label = 'LTN';
    else if (s < 7.0) label = 'MTN';
    else if (s < 8.0) label = 'HTN';
    else if (s < 9.0) label = 'Chadlite';
    else label = 'Chad';
    if (isFirstScan && (label === 'Chadlite' || label === 'Chad')) return 'HTN';
    return label;
}

const _BONE_UMAX_IDS = new Set(['jawline', 'cheekbones', 'nose', 'eyes', 'symmetry']);

function suggestedModulesFromUmax(analysis: any): string[] {
    const rows = analysis?.umax_metrics;
    if (!Array.isArray(rows) || rows.length === 0) return ['fitmax', 'skinmax'];
    const parsed: { id: string; score: number }[] = [];
    for (const row of rows) {
        if (!row || typeof row !== 'object') continue;
        const id = String((row as any).id || '');
        const sc = parseFloat(String((row as any).score ?? '5'));
        if (!id || Number.isNaN(sc)) continue;
        parsed.push({ id, score: Math.max(0, Math.min(10, sc)) });
    }
    if (!parsed.length) return ['fitmax', 'skinmax'];
    const out: string[] = [];
    let bone = false;
    for (const { id, score } of parsed) {
        if (score > 5.9) continue;
        if (_BONE_UMAX_IDS.has(id)) { if (!bone) { out.push('bonemax'); bone = true; } }
        else if (id === 'skin') out.push('skinmax');
    }
    if (!out.length) {
        const sorted = [...parsed].sort((x, y) => x.score - y.score);
        for (const { id } of sorted.slice(0, 3)) {
            if (_BONE_UMAX_IDS.has(id)) { if (!bone) { out.push('bonemax'); bone = true; } }
            else if (id === 'skin') out.push('skinmax');
        }
    }
    if (!out.length) return ['fitmax', 'skinmax'];
    return [...new Set(out)].slice(0, 3);
}

function parseOverall(analysis: any): number | null {
    if (!analysis) return null;
    const pr = analysis.psl_rating;
    if (pr?.psl_score != null && pr.psl_score !== '') {
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

function inflatePotentialForDisplay(raw: number): number {
    const headroom = Math.max(0, 10 - raw);
    const bumped = raw + 0.28 + headroom * 0.06;
    return Math.min(10, Math.round(bumped * 10) / 10);
}

function anchorPotentialFromRating(ratingDisplay: number | null): number {
    const r = ratingDisplay ?? 5;
    const x = Math.max(RATING_DISPLAY_MIN, Math.min(10, r));
    const pts: readonly [number, number][] = [
        [2.5, 7.55], [4.0, 8.32], [6.0, 8.95], [8.0, 9.35], [10.0, 9.85],
    ];
    if (x <= pts[0][0]) return pts[0][1];
    for (let i = 0; i < pts.length - 1; i++) {
        const [x0, y0] = pts[i];
        const [x1, y1] = pts[i + 1];
        if (x <= x1) { const t = (x - x0) / (x1 - x0); return y0 + t * (y1 - y0); }
    }
    return pts[pts.length - 1][1];
}

function clampDisplayRating(overall: number | null): number | null {
    if (overall == null || Number.isNaN(overall)) return null;
    return Math.round(Math.max(RATING_DISPLAY_MIN, Math.min(10, overall)) * 10) / 10;
}

function computeDisplayPotential(rawPotential: number, treatAsPaid: boolean, ratingDisplay: number | null): number {
    if (!treatAsPaid) return Math.round(Math.max(0, Math.min(10, rawPotential)) * 10) / 10;
    const anchor = anchorPotentialFromRating(ratingDisplay);
    const inflated = inflatePotentialForDisplay(rawPotential);
    const nudge = (inflated - 7) * 0.1;
    const v = anchor + nudge;
    return Math.round(Math.min(9.9, Math.max(6.4, v)) * 10) / 10;
}

type RouteParams = { postPay?: boolean };

async function captureRatingCardToPng(ref: React.RefObject<View | null>): Promise<string | null> {
    if (!ref.current) return null;
    await new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    try {
        const uri = await captureRef(ref.current, { format: 'png', quality: 1, result: 'tmpfile' });
        return typeof uri === 'string' ? uri : null;
    } catch (e) { console.error('captureRef failed', e); return null; }
}

// ─── Paywall blur shell ───────────────────────────────────────────────────────

function PaywallBlurShell({ children, minHeight }: { children: React.ReactNode; minHeight?: number }) {
    return (
        <View style={[s.paywallBlurShell, minHeight ? { minHeight } : null]}>
            {children}
            <BlurView intensity={Platform.OS === 'ios' ? 56 : 72} tint="light" style={StyleSheet.absoluteFill}
                experimentalBlurMethod={Platform.OS === 'android' ? 'dimezisBlurView' : undefined} />
            <View pointerEvents="none" style={[StyleSheet.absoluteFill, s.paywallFlatOverlay]} />
        </View>
    );
}

// ─── Processing view ──────────────────────────────────────────────────────────

const PROCESSING_TIMEOUT_MS = 60_000;

function ScanProcessingView({ onRetry, onBack }: { onRetry: () => void; onBack: () => void }) {
    const insets = useSafeAreaInsets();
    const [trackWidth, setTrackWidth] = useState(0);
    const progressAnim = useRef(new Animated.Value(12)).current;
    const [pctLabel, setPctLabel] = useState(12);
    const [timedOut, setTimedOut] = useState(false);

    useEffect(() => {
        const id = setTimeout(() => setTimedOut(true), PROCESSING_TIMEOUT_MS);
        return () => clearTimeout(id);
    }, []);

    useEffect(() => {
        if (timedOut) return;
        const sub = progressAnim.addListener(({ value }) => setPctLabel(Math.min(100, Math.max(0, Math.round(value)))));
        const loop = Animated.loop(Animated.sequence([
            Animated.timing(progressAnim, { toValue: 91, duration: 2400, useNativeDriver: false }),
            Animated.timing(progressAnim, { toValue: 14, duration: 600, useNativeDriver: false }),
        ]));
        loop.start();
        return () => { progressAnim.removeListener(sub); loop.stop(); };
    }, [progressAnim, timedOut]);

    const onTrackLayout = (e: LayoutChangeEvent) => setTrackWidth(e.nativeEvent.layout.width);
    const fillWidth = trackWidth > 0 ? progressAnim.interpolate({ inputRange: [0, 100], outputRange: [0, trackWidth], extrapolate: 'clamp' }) : 0;

    if (timedOut) {
        return (
            <View style={[s.root, s.fetchingRoot]}>
                <Text style={s.fetchErrorText}>This is taking longer than expected. Check your connection and try again.</Text>
                <TouchableOpacity style={s.fetchRetryBtn} onPress={() => { setTimedOut(false); onRetry(); }} activeOpacity={0.85}>
                    <Text style={s.fetchRetryText}>Retry</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.fetchSkipBtn} onPress={onBack} activeOpacity={0.85}>
                    <Text style={s.fetchSkipText}>Back</Text>
                </TouchableOpacity>
            </View>
        );
    }

    return (
        <View style={[s.root, s.loadingRoot]}>
            <View style={[s.loadingHeader, { paddingTop: Math.max(insets.top, 12) + 8 }]}>
                <View style={s.progressTopRow}>
                    <Text style={s.progressTitle}>Analyzing your scan</Text>
                    <Text style={s.progressPct}>{pctLabel}%</Text>
                </View>
                <View style={s.loadingTrackWrap}>
                    <View style={s.track} onLayout={onTrackLayout}>
                        <Animated.View style={[s.trackFill, { width: fillWidth }]} />
                    </View>
                </View>
                <Text style={s.loadingSub}>Building your facial ratings…</Text>
                <Text style={s.stayInAppNotice}>Stay in the app until this finishes.</Text>
            </View>
            <ActivityIndicator size="large" color={colors.foreground} style={{ marginTop: spacing.xl }} />
        </View>
    );
}

// ─── Animated ring ────────────────────────────────────────────────────────────

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

function MetricRing({ score, outOf = 10, delay = 0, color, gradient, gid = 'mr', size = 72 }: {
    score: number; outOf?: number; delay?: number; color?: string;
    // Two-stop jewel-tone gradient [from, to] for a richer, non-flat ring. When
    // set it overrides `color`. `gid` must be unique per mounted ring so the SVG
    // gradient defs don't collide.
    gradient?: readonly [string, string]; gid?: string; size?: number;
}) {
    const stk = Math.max(3, Math.round(size * 0.072));
    const r = (size - stk) / 2;
    const circ = 2 * Math.PI * r;
    const anim = useRef(new Animated.Value(0)).current;

    useEffect(() => {
        Animated.timing(anim, {
            toValue: Math.max(0, Math.min(outOf, score)),
            duration: 1000,
            delay,
            easing: Easing.out(Easing.cubic),
            useNativeDriver: false,
        }).start();
    }, [score]);

    const dashOffset = anim.interpolate({
        inputRange: [0, outOf],
        outputRange: [circ, 0],
        extrapolate: 'clamp',
    });

    const stroke = gradient ? `url(#${gid})` : (color || '#FFFFFF');

    return (
        <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
            <Svg width={size} height={size} style={{ position: 'absolute', transform: [{ rotate: '-90deg' }] }}>
                {gradient ? (
                    <Defs>
                        <SvgLinearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
                            <Stop offset="0" stopColor={gradient[0]} />
                            <Stop offset="1" stopColor={gradient[1]} />
                        </SvgLinearGradient>
                    </Defs>
                ) : null}
                <Circle cx={size / 2} cy={size / 2} r={r}
                    stroke="rgba(255,255,255,0.18)" strokeWidth={stk} fill="none" />
                <AnimatedCircle cx={size / 2} cy={size / 2} r={r}
                    stroke={stroke} strokeWidth={stk} fill="none"
                    strokeLinecap="round"
                    strokeDasharray={circ}
                    strokeDashoffset={dashOffset} />
            </Svg>
        </View>
    );
}

// ─── Floating hover wrapper ───────────────────────────────────────────────────
// Wraps a metric window in a slow, looping up/down "bop". `baseY` offsets the
// rest position (used to stagger the three windows into a downward triangle);
// the hover oscillates ±5 around it. Phase is delayed per card so they drift
// out of sync and feel alive rather than mechanical.
function HoverCard({ children, baseY = 0, delay = 0, style }: {
    children: React.ReactNode; baseY?: number; delay?: number; style?: any;
}) {
    const t = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        const native = Platform.OS !== 'web';
        const loop = Animated.loop(Animated.sequence([
            Animated.timing(t, { toValue: 1, duration: 1700, delay, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
            Animated.timing(t, { toValue: 0, duration: 1700, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
        ]));
        loop.start();
        return () => loop.stop();
    }, []);
    const translateY = t.interpolate({ inputRange: [0, 1], outputRange: [baseY - 5, baseY + 5] });
    return <Animated.View style={[style, { transform: [{ translateY }] }]}>{children}</Animated.View>;
}

// Minimal scroll cue — a chevron that gently bobs down in the white space at the
// bottom of the hero, inviting the user to scroll into "Your Analysis".
function ScrollCue({ onPress }: { onPress: () => void }) {
    const t = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        const native = Platform.OS !== 'web';
        const loop = Animated.loop(Animated.sequence([
            Animated.timing(t, { toValue: 1, duration: 950, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
            Animated.timing(t, { toValue: 0, duration: 950, easing: Easing.inOut(Easing.sin), useNativeDriver: native }),
        ]));
        loop.start();
        return () => loop.stop();
    }, []);
    const translateY = t.interpolate({ inputRange: [0, 1], outputRange: [-3, 6] });
    const opacity = t.interpolate({ inputRange: [0, 1], outputRange: [0.85, 0.35] });
    return (
        <TouchableOpacity
            style={s.scrollCue}
            onPress={onPress}
            activeOpacity={0.7}
            hitSlop={{ top: 16, bottom: 16, left: 24, right: 24 }}
            accessibilityRole="button"
            accessibilityLabel="Scroll to your analysis"
        >
            <Animated.View style={{ transform: [{ translateY }], opacity }}>
                <Ionicons name="chevron-down" size={26} color="rgba(21,19,26,0.55)" />
            </Animated.View>
        </TouchableOpacity>
    );
}

// Scan-frame corner brackets that float around the face in the hero.
const FBR = 40, FBW = 2.5, FBC = 'rgba(255,255,255,0.5)';
const fr = StyleSheet.create({
    base: { position: 'absolute', width: FBR, height: FBR },
    tl: { top: 0, left: 0, borderTopWidth: FBW, borderLeftWidth: FBW, borderColor: FBC, borderTopLeftRadius: 12 },
    tr: { top: 0, right: 0, borderTopWidth: FBW, borderRightWidth: FBW, borderColor: FBC, borderTopRightRadius: 12 },
    bl: { bottom: 0, left: 0, borderBottomWidth: FBW, borderLeftWidth: FBW, borderColor: FBC, borderBottomLeftRadius: 12 },
    br: { bottom: 0, right: 0, borderBottomWidth: FBW, borderRightWidth: FBW, borderColor: FBC, borderBottomRightRadius: 12 },
});

// ─── Insight card (stats section) ─────────────────────────────────────────────

function InsightCard({ kicker, value, sub, bg, wide = false }: {
    kicker: string; value: string; sub?: string; bg: string; wide?: boolean;
}) {
    return (
        <View style={[ic.card, wide && ic.wide, { backgroundColor: bg }]}>
            <Text style={ic.kicker}>{kicker}</Text>
            <Text style={ic.value} numberOfLines={2} adjustsFontSizeToFit>{value}</Text>
            {sub ? <Text style={ic.sub}>{sub}</Text> : null}
        </View>
    );
}

const ic = StyleSheet.create({
    card: { borderRadius: 20, padding: 18, flex: 1, minHeight: 100, justifyContent: 'flex-end' },
    wide: { flex: 0, width: '100%' },
    kicker: { fontFamily: 'Matter-Medium', fontSize: 11, color: 'rgba(255,255,255,0.55)', letterSpacing: 0.8, marginBottom: 6, textTransform: 'uppercase' },
    value: { fontFamily: 'Matter-SemiBold', fontSize: 22, color: '#FFFFFF', letterSpacing: -0.5, lineHeight: 26 },
    sub: { fontFamily: 'Matter-Regular', fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 4 },
});

// ─── Your Analysis: feature label map + palette ───────────────────────────────
// Friendly labels + accent palette for the per-feature sub-scores.
const UMAX_LABELS: Record<string, string> = {
    jawline: 'Jawline', cheekbones: 'Cheekbones', nose: 'Nose', eyes: 'Eyes',
    symmetry: 'Symmetry', skin: 'Skin', chin: 'Chin', lips: 'Lips', mouth: 'Mouth',
    hairline: 'Hairline', masculinity: 'Masculinity', harmony: 'Harmony',
    canthal_tilt: 'Canthal tilt', cheeks: 'Cheeks', forehead: 'Forehead',
    proportions: 'Proportions', maxilla: 'Maxilla', jaw: 'Jaw',
};
const FEATURE_PALETTE = ['#8E8FB5', '#9DB4E0', '#7FB1A0', '#C99BA0', '#B59AC9', '#C7A98B', '#7FA8C9', '#A9B58E'];

// ─── Your Analysis bento — frosted glass ──────────────────────────────────────
// Deliberate mixed card sizes (hero → wide → square rows) under named sections.
// Every card is translucent frosted glass tinted by its own accent — no opaque
// fills, no raw numbers. Tap a card to expand a glassy detail and elaborate.
const BENTO_INK = '#1B1822';
const BENTO_SUB = '#736F7E';

// Single accent per card (the glass takes a low-opacity wash of it).
const A_RATING = '#6E5BA8';
const A_POTENTIAL = '#5F6CC4';
const A_APPEAL = '#CC6F73';
const A_TIER = '#4A4A70';
const A_ARCH = '#C06A85';
const A_ASCEND = '#BC8B57';
const A_AGE = '#4E8C82';

type BentoFeatureItem = { key: string; name: string; value: string; accent: string };

// A qualitative word for a 0–10 score — we never show the raw number.
function band(score: number): string {
    if (score >= 8.5) return 'Elite';
    if (score >= 7) return 'Strong';
    if (score >= 5.5) return 'Refined';
    if (score >= 4) return 'Balanced';
    return 'Emerging';
}

// What each stat opens into when tapped — a short, plain-language elaboration.
const BLURBS: Record<string, string> = {
    Rating: 'Your overall facial rating — one read on how your features come together. It weighs structure, harmony, and proportion into a single signal.',
    Potential: 'Your realistic ceiling with a consistent plan. Not where you are today — where focused, steady work can take you.',
    Appeal: 'How balanced and harmonious your proportions are. High appeal means your features sit in pleasing ratio to one another.',
    Tier: 'The PSL bracket your face falls into — where you land on the standardized rating scale, from a single glance to the trained eye.',
    Archetype: 'The facial archetype your features map to most closely — the overall "type" your look reads as.',
    Ascension: 'How long a focused routine would take to move you up to the next tier.',
    'Facial age': 'How old your face reads at a glance versus your real age — a proxy for skin, structure, and vitality.',
};

function SectionHeader({ children }: { children: React.ReactNode }) {
    return <Text style={bento.section}>{children}</Text>;
}

// Big focal card — name + one qualitative word (no number). Pure-white pane
// with a soft shadow and a hairline accent edge + dot for identity. No fills,
// no gradients — the windows stay clean white.
function BentoHero({ label, value, sub, accent, locked, lockedSub, onPress }: {
    label: string; value: string; sub?: string; accent: string;
    locked: boolean; lockedSub?: string; onPress?: () => void;
}) {
    return (
        <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={[bento.hero, { borderColor: `${accent}66` }]}>
            <View style={[bento.dot, { backgroundColor: accent, marginBottom: 14 }]} />
            <Text style={bento.heroLabel}>{label}</Text>
            {locked ? (
                <View style={bento.heroLock}><Ionicons name="lock-closed" size={30} color={accent} /></View>
            ) : (
                <Text style={bento.heroWord} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
            )}
            <Text style={bento.heroSub}>{locked ? (lockedSub || 'Tap to learn more.') : (sub || '')}</Text>
        </TouchableOpacity>
    );
}

// Wide glass card.
function BentoWide({ label, value, sub, accent, locked, onPress }: {
    label: string; value: string; sub: string; accent: string;
    locked: boolean; onPress?: () => void;
}) {
    return (
        <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={[bento.wide, { borderColor: `${accent}66` }]}>
            <View style={bento.wideTop}>
                <View style={bento.rowCenter}>
                    <View style={[bento.dot, { backgroundColor: accent, marginRight: 9 }]} />
                    <Text style={bento.wideLabel}>{label}</Text>
                </View>
                {locked
                    ? <Ionicons name="lock-closed" size={17} color={accent} />
                    : <Text style={bento.wideWord}>{value}</Text>}
            </View>
            <Text style={bento.wideSub}>{locked ? 'Tap to learn more.' : sub}</Text>
        </TouchableOpacity>
    );
}

// Small square glass stat.
function BentoSquare({ label, value, accent, locked, onPress }: {
    label: string; value: string; accent: string; locked: boolean; onPress?: () => void;
}) {
    return (
        <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={[bento.square, { borderColor: `${accent}66` }]}>
            <View style={[bento.dot, { backgroundColor: accent }]} />
            <View>
                <Text style={bento.squareLabel}>{label}</Text>
                {locked
                    ? <Ionicons name="lock-closed" size={16} color={accent} style={{ marginTop: 6 }} />
                    : <Text style={bento.squareWord} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>}
            </View>
        </TouchableOpacity>
    );
}

// Feature mini glass card (per-feature breakdown).
function BentoFeature({ name, value, accent, locked, onPress }: {
    name: string; value: string; accent: string; locked: boolean; onPress?: () => void;
}) {
    return (
        <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={[bento.feat, { borderColor: `${accent}66` }]}>
            <View style={[bento.dot, { backgroundColor: accent }]} />
            <Text style={bento.featName} numberOfLines={1}>{name}</Text>
            {locked
                ? <Ionicons name="lock-closed" size={13} color={accent} style={{ opacity: 0.7 }} />
                : <Text style={bento.featWord} numberOfLines={1}>{value}</Text>}
        </TouchableOpacity>
    );
}

const GLASS_SHADOW = {
    shadowColor: '#3A2E55', shadowOpacity: 0.1, shadowRadius: 16, shadowOffset: { width: 0, height: 8 }, elevation: 3,
} as const;

// Canonical liquid-glass CARD — the same recipe as the planner's Today button.
// An OUTER view carries the soft float shadow; an INNER overflow-hidden clip
// owns the rounded shape, a bright hairline rim, a translucent wash (NOT a milky
// fill — glass has to stay see-through) and the LiquidGlassFill optics. Splitting
// outer/inner is what lets the float shadow survive the clip. `dark` = ink glass
// for the over-photo hero windows (keeps white text legible); light = frosted for
// the white analysis sheet. Pass onPress to make the whole pane tappable.
// Exact match for the planner Today-button float shadow (glassShadow).
const GLASS_FLOAT = {
    shadowColor: '#3A352B', shadowOpacity: 0.13, shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 }, elevation: 5,
} as const;

function GlassCard({
    children, style, contentStyle, radius = 20, dark = false, onPress, accessibilityLabel,
}: {
    children: React.ReactNode;
    style?: any;
    contentStyle?: any;
    radius?: number;
    dark?: boolean;
    onPress?: () => void;
    accessibilityLabel?: string;
}) {
    const uid = useId().replace(/:/g, '');
    const Clip: any = onPress ? TouchableOpacity : View;
    // Light variant = the EXACT planner Today-button glass (0.18 white wash,
    // 0.7 white hairline rim). Dark variant is the same recipe in ink, for the
    // hero windows that float over the photo (white text needs the darker pane).
    const fill = dark ? 'rgba(18,16,24,0.28)' : 'rgba(255,255,255,0.18)';
    const rim = dark ? 'rgba(255,255,255,0.24)' : 'rgba(255,255,255,0.7)';
    return (
        <View style={[{ borderRadius: radius, borderCurve: 'continuous' }, GLASS_FLOAT, style]}>
            <Clip
                {...(onPress ? { onPress, activeOpacity: 0.85, accessibilityRole: 'button', accessibilityLabel } : {})}
                style={[
                    {
                        borderRadius: radius, borderCurve: 'continuous', overflow: 'hidden',
                        borderWidth: StyleSheet.hairlineWidth, borderColor: rim, backgroundColor: fill,
                    },
                    contentStyle,
                ]}
            >
                <LiquidGlassFill dark={dark} idSuffix={uid} corners={false} />
                {children}
            </Clip>
        </View>
    );
}

const bento = StyleSheet.create({
    section: { fontFamily: 'Matter-Medium', fontSize: 13, color: '#A2A0A8', letterSpacing: 0.6, textTransform: 'uppercase', marginTop: 24, marginBottom: 12 },
    rowCenter: { flexDirection: 'row', alignItems: 'center' },
    dot: { width: 8, height: 8, borderRadius: 4 },

    hero: {
        backgroundColor: '#FFFFFF',
        borderRadius: 28, overflow: 'hidden', paddingHorizontal: 24, paddingVertical: 32, minHeight: 196,
        justifyContent: 'center', alignItems: 'center', borderWidth: 1, ...GLASS_SHADOW,
    },
    heroLabel: { fontFamily: 'Matter-Medium', fontSize: 13, color: BENTO_SUB, letterSpacing: 1, textTransform: 'uppercase' },
    heroWord: { fontFamily: fonts.serif, fontSize: 46, lineHeight: 52, color: BENTO_INK, letterSpacing: -0.8, marginTop: 8 },
    heroLock: { marginVertical: 12 },
    heroSub: { fontFamily: 'Matter-Regular', fontSize: 13, color: BENTO_SUB, marginTop: 10, textAlign: 'center' },

    wide: {
        backgroundColor: '#FFFFFF',
        borderRadius: 22, overflow: 'hidden', padding: 20, minHeight: 96, justifyContent: 'center', borderWidth: 1, ...GLASS_SHADOW,
    },
    wideTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    wideLabel: { fontFamily: 'Matter-SemiBold', fontSize: 15.5, color: BENTO_INK, letterSpacing: -0.1 },
    wideWord: { fontFamily: fonts.serif, fontSize: 22, color: BENTO_INK, letterSpacing: -0.3 },
    wideSub: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: BENTO_SUB, marginTop: 9 },

    row3: { flexDirection: 'row', gap: 10, marginTop: 10 },
    row2: { flexDirection: 'row', gap: 10, marginTop: 10 },

    square: {
        backgroundColor: '#FFFFFF',
        flex: 1, aspectRatio: 1, borderRadius: 20, overflow: 'hidden', padding: 16, justifyContent: 'space-between', borderWidth: 1, ...GLASS_SHADOW,
    },
    squareLabel: { fontFamily: 'Matter-Medium', fontSize: 12.5, color: BENTO_SUB, letterSpacing: 0.3, textTransform: 'uppercase' },
    squareWord: { fontFamily: fonts.serif, fontSize: 19, color: BENTO_INK, letterSpacing: -0.3, marginTop: 4 },

    featGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
    feat: { backgroundColor: '#FFFFFF', width: '31.5%', borderRadius: 16, overflow: 'hidden', paddingHorizontal: 12, paddingVertical: 14, marginBottom: 10, minHeight: 84, justifyContent: 'space-between', borderWidth: 1, ...GLASS_SHADOW },
    featName: { fontFamily: 'Matter-Medium', fontSize: 12.5, color: BENTO_INK, marginTop: 6 },
    featWord: { fontFamily: 'Matter-SemiBold', fontSize: 13.5, color: BENTO_SUB, marginTop: 2, letterSpacing: -0.1 },
});

// ─── Looksmax breakdown: comprehensive sections → mosaic tiles ─────────────────
// Each tile maps to a path in the analysis. Numeric features render /10; bone
// measurements (FWHR, gonial angle, projections) render their natural unit; only
// Tier and Archetype stay qualitative. When unlocked we drop tiles with no data;
// when locked we keep the full structure as the paywall tease.
const MOSAIC_PALETTE = [
    '#6E5BA8', '#5F6CC4', '#CC6F73', '#4E8C82', '#BC8B57', '#C06A85',
    '#4A6FA5', '#7FA86B', '#A06A9C', '#5E8C6A', '#C2803E', '#5AA0A8',
];

const METRIC_DETAIL: Record<string, string> = {
    jaw: 'Definition of the mandible and gonial angle — a wide jaw with a clean angle reads masculine and structured.',
    chin: 'Projection and width of the chin. A forward, defined chin balances the lower third and strengthens the profile.',
    cheekbones: 'Height and width of the zygomatic bones. High, wide cheekbones add shadowing and an angular midface.',
    midface: 'Midface ratio — compactness from pupils to lip. A shorter, fuller midface is a strong harmony marker.',
    brow_ridge: 'Brow-bone prominence and how it sets over the eyes. A developed, slightly forward brow deepens the eye area.',
    symmetry: 'Left-vs-right balance across your features — the single biggest driver of perceived harmony.',
    fwhr: 'Facial width-to-height ratio. Higher reads more dominant; the attractive male range sits around 1.9–2.0.',
    eyes: 'Overall eye area — shape, size and spacing. The visual centre of the face and the first thing people read.',
    canthal_tilt: 'Angle from inner to outer eye corner. A positive tilt (outer corner higher) is the coveted hunter-eye marker.',
    hunter_eyes: 'Positive canthal tilt + a low-set, hooded brow + low eyelid exposure — an intense, "sloaded" eye look.',
    under_eye: 'Under-eye support: hollowing, dark circles and puffiness. Flat, bright under-eyes read healthy and rested.',
    nose: 'Bridge, tip and proportion of the nose to the rest of the face. Straight and proportionate scores highest.',
    lips: 'Fullness and shape of the lips. A balanced upper-to-lower ratio with defined borders is ideal.',
    philtrum: 'Distance from nose to upper lip. A shorter philtrum keeps the lower third compact and youthful.',
    maxilla: 'Forward growth of the upper jaw. Strong maxillary projection lifts the midface, cheekbones and eye area.',
    mandible: 'Forward growth and strength of the lower jaw — drives jawline projection on the side profile.',
    gonial: 'The jaw angle where the mandible turns up toward the ear. Around 120° with a defined corner is the sweet spot.',
    submental: 'The neck-to-jaw (submental) angle. A crisp angle makes the jawline pop in profile.',
    eline: "Ricketts' E-line — nose tip to chin. Lips sitting just behind this line is the balanced-profile ideal.",
    fhp: 'Forward head posture drops the chin and shortens the neck — postural, and very fixable.',
    skin: 'Clarity and evenness — breakouts, redness and marks. The fastest-moving lever in any plan.',
    skin_texture: 'Pore visibility and surface smoothness. Refined texture catches light evenly and reads premium.',
    masculinity: 'Sexual dimorphism — how strongly your features read masculine. Drives your "type" more than raw score.',
    hairline: 'Hairline shape and maturity. A full, even hairline frames the upper third and supports every other feature.',
    hair_density: 'Density and coverage of scalp hair. Thickness frames the face and responds fast to early action.',
    facial_hair: 'Beard density and pattern — a strong frame for the lower third and a quick way to add jaw definition.',
    tier: 'The PSL bracket your face falls into on the looksmaxxing scale — Sub 5 up through HTN, Chadlite and Chad.',
    archetype: 'The facial "type" your features map to most closely — the overall vibe your look reads as.',
    mog: 'Where you place against other men your age. "Top 15%" means you out-mog roughly 85 of every 100.',
    upside: 'How much non-surgical headroom you have left. Higher means more to gain from a consistent plan.',
};

type MosaicSection = { key: string; title: string; tiles: MosaicTile[] };

function _fnum(v: unknown): number | null {
    const n = parseFloat(String(v ?? ''));
    return Number.isNaN(n) ? null : n;
}
const _clamp10 = (n: number) => Math.max(0, Math.min(10, n));
const _one = (n: number) => `${Math.round(n * 10) / 10}`;

function buildMosaicSections(a: any, locked: boolean, archetype: string, pslTier: string): MosaicSection[] {
    const pr = a && typeof a.psl_rating === 'object' ? a.psl_rating : {};
    const fs = pr && typeof pr.feature_scores === 'object' ? pr.feature_scores
        : a && typeof a.feature_scores === 'object' ? a.feature_scores : {};
    const prop = pr && typeof pr.proportions === 'object' ? pr.proportions : {};
    const side = pr && typeof pr.side_profile === 'object' ? pr.side_profile : {};

    let ai = 0;
    const accent = () => MOSAIC_PALETTE[ai++ % MOSAIC_PALETTE.length];

    type T = MosaicTile & { present: boolean };

    // /10 feature tile pulled from feature_scores[key].
    const feat = (key: string, label: string, detailKey: string = key): T => {
        const cell = fs && typeof fs[key] === 'object' ? fs[key] : null;
        const sc = cell ? _fnum(cell.score) : null;
        const present = sc != null;
        return {
            key: `m-${key}`, label, accent: accent(), locked,
            value: present ? _one(_clamp10(sc as number)) : '—',
            unit: present ? '/10' : undefined,
            score: present ? _clamp10(sc as number) : undefined,
            tag: cell && typeof cell.tag === 'string' && cell.tag ? cell.tag : undefined,
            detail: cell && typeof cell.notes === 'string' && cell.notes ? cell.notes : METRIC_DETAIL[detailKey],
            present,
        };
    };

    // Natural-unit / qualitative tile (no /10): projections, angles, tier, etc.
    const meas = (key: string, label: string, raw: string | number | boolean | null, detailKey: string = key): T => {
        let v = '';
        if (typeof raw === 'boolean') v = raw ? 'Yes' : 'No';
        else if (raw != null) v = String(raw).trim();
        const present = v.length > 0 && v !== '0';
        return {
            key: `m-${key}`, label, accent: accent(), locked,
            value: present ? v : '—',
            detail: METRIC_DETAIL[detailKey],
            present,
        };
    };

    // A /10 tile from a bare numeric field (masculinity index, etc.).
    const num10 = (key: string, label: string, raw: unknown, detailKey: string = key): T => {
        const n = _fnum(raw);
        const present = n != null;
        return {
            key: `m-${key}`, label, accent: accent(), locked,
            value: present ? _one(_clamp10(n as number)) : '—',
            unit: present ? '/10' : undefined,
            score: present ? _clamp10(n as number) : undefined,
            detail: METRIC_DETAIL[detailKey],
            present,
        };
    };

    const section = (key: string, title: string, tiles: T[]): MosaicSection | null => {
        const kept = locked ? tiles : tiles.filter((t) => t.present);
        if (!kept.length) return null;
        return { key, title, tiles: kept.map(({ present: _p, ...rest }) => rest) };
    };

    const mogP = _fnum(pr.mog_percentile);
    const mogVal = mogP != null ? `Top ${Math.max(1, Math.min(99, Math.round(100 - mogP)))}%` : null;
    const fwhr = _fnum(prop.fwhr);

    const sections: (MosaicSection | null)[] = [
        section('verdict', 'The verdict', [
            meas('tier', 'PSL tier', pslTier || null, 'tier'),
            meas('archetype', 'Archetype', archetype || null, 'archetype'),
            meas('mog', 'Mogs', mogVal, 'mog'),
            { ...num10('upside', 'Upside', pr.glow_up_potential, 'upside'), unit: _fnum(pr.glow_up_potential) != null ? '/100' : undefined, score: undefined } as T,
        ]),
        section('bone', 'Bone structure', [
            feat('jaw', 'Jawline'),
            feat('chin', 'Chin'),
            feat('cheekbones', 'Cheekbones'),
            feat('midface', 'Midface'),
            feat('brow_ridge', 'Brow ridge'),
            feat('symmetry', 'Symmetry'),
            meas('fwhr', 'FWHR', fwhr != null ? (Math.round(fwhr * 100) / 100).toFixed(2) : null, 'fwhr'),
        ]),
        section('eyes', 'Eyes', [
            feat('eyes', 'Eye area'),
            feat('canthal_tilt', 'Canthal tilt'),
            feat('hunter_eyes', 'Hunter eyes'),
        ]),
        section('mouth', 'Nose & mouth', [
            feat('nose', 'Nose'),
            feat('lips', 'Lips'),
            feat('philtrum', 'Philtrum'),
        ]),
        section('side', 'Side profile', [
            meas('maxilla', 'Maxilla', side.maxillary_projection ?? null, 'maxilla'),
            meas('mandible', 'Mandible', side.mandibular_projection ?? null, 'mandible'),
            meas('gonial', 'Gonial angle', side.gonial_angle ?? null, 'gonial'),
            meas('submental', 'Neck angle', side.submental_angle ?? null, 'submental'),
            meas('eline', 'E-line', side.ricketts_e_line ?? null, 'eline'),
            meas('fhp', 'Head posture', typeof side.forward_head_posture === 'boolean' ? (side.forward_head_posture ? 'Forward' : 'Neutral') : null, 'fhp'),
        ]),
        section('skin', 'Skin', [
            feat('skin', 'Clarity', 'skin'),
            feat('skin_texture', 'Texture'),
            feat('under_eye', 'Under-eye'),
        ]),
        section('frame', 'Frame & dimorphism', [
            num10('masculinity', 'Masculinity', pr.masculinity_index, 'masculinity'),
            feat('hairline', 'Hairline'),
            feat('hair_density', 'Hair density'),
            feat('facial_hair', 'Facial hair'),
        ]),
    ];

    return sections.filter((x): x is MosaicSection => x !== null);
}

// ─── Main screen ──────────────────────────────────────────────────────────────

export default function FaceScanResultsScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { width: SCREEN_W, height: SCREEN_H } = useWindowDimensions();
    const insets = useSafeAreaInsets();
    const { isPaid, isScanUser, isFreeTier, refreshUser, user } = useAuth() as any;
    const personalizedUI = useFlag('personalizedUI');
    const postPayParam = !!(route.params as RouteParams)?.postPay;
    const scanIdParam = (route.params as any)?.scanId as string | undefined;
    // Funnel V4 results gate: the SAME page, reduced to its hero — the scan
    // photo + the three headline rings with their teaser values VISIBLE
    // (rating / appeal / potential are in the redacted payload by design) and
    // a single unlock CTA into the paywall. Everything below the fold is
    // paid-only and hidden here.
    const gateV4 = !!(route.params as any)?.gateV4;
    const viewingHistory = !!scanIdParam;
    const postSubscriptionOnboarding = !!(user?.onboarding as any)?.post_subscription_onboarding;

    const [scan, setScan] = useState<any>(null);
    const [hydrating, setHydrating] = useState(true);
    const [processing, setProcessing] = useState(false);
    const [advancing, setAdvancing] = useState(false);
    const advancedRef = useRef(false);
    // Save/Share now snapshot the REAL views the user sees, not an off-screen
    // designed card: rootRef = the full-screen hero (scan photo + the 3 rings),
    // analysisRef = the white "Your Analysis" sheet.
    const rootRef = useRef<View>(null);
    const analysisRef = useRef<View>(null);
    const [shareCaptureBusy, setShareCaptureBusy] = useState(false);
    // Only true for the brief window while we snapshot for Save/Share, so the
    // "max" watermark is burned into the exported images but never shown in-app.
    const [exportWatermark, setExportWatermark] = useState(false);
    const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
    const scrollRef = useRef<ScrollView>(null);
    const didTrackResultsView = useRef(false);

    // Tap-a-stat → glassy elaboration overlay (never auto-navigates to paywall).
    const [detail, setDetail] = useState<{ name: string; blurb: string; accent: string; locked: boolean } | null>(null);
    const detailAnim = useRef(new Animated.Value(0)).current;
    const openDetail = useCallback((name: string, accent: string, lk: boolean) => {
        const blurb = BLURBS[name] || `How your ${name.toLowerCase()} scores against ideal facial proportions — one of the building blocks of your overall rating.`;
        setDetail({ name, blurb, accent, locked: lk });
    }, []);
    const closeDetail = useCallback(() => {
        Animated.timing(detailAnim, { toValue: 0, duration: 150, easing: Easing.in(Easing.cubic), useNativeDriver: true })
            .start(() => setDetail(null));
    }, [detailAnim]);
    useEffect(() => {
        if (!detail) return;
        detailAnim.setValue(0);
        Animated.spring(detailAnim, { toValue: 1, useNativeDriver: true, damping: 15, stiffness: 190, mass: 0.7 }).start();
    }, [detail, detailAnim]);

    const bootstrap = useCallback(async () => {
        setHydrating(true);
        try {
            const result = scanIdParam ? await api.getScanById(scanIdParam) : await api.getLatestScan();
            if (postPayParam || result?.is_unlocked) {
                try { await refreshUser(); } catch (e) { console.error(e); }
            }
            setScan(result);
        } catch (e) { console.error(e); setScan(null); }
        finally { setHydrating(false); }
    }, [postPayParam, refreshUser, scanIdParam]);

    useEffect(() => { bootstrap(); }, [bootstrap]);

    // Funnel V4: the user can arrive here BEFORE the background upload from the
    // capture step has landed (they were answering the effort question while it
    // ran) — there's no scan row yet. Keep re-fetching until it appears; the
    // regular processing poll takes over from there.
    useEffect(() => {
        if (!gateV4 || hydrating || scan) return;
        const t = setTimeout(() => { void bootstrap(); }, 3000);
        return () => clearTimeout(t);
    }, [gateV4, hydrating, scan, bootstrap]);

    useEffect(() => {
        if (hydrating) return;
        if (didTrackResultsView.current) return;
        didTrackResultsView.current = true;
        track('onboarding_step', { step: 'results_view' });
    }, [hydrating]);

    // Clear the in-flight submit flag + captured-photo draft ONLY when this is
    // the genuine post-upload hand-off (FaceScanScreen passes justSubmitted).
    // FaceScanScreen deliberately leaves them set so any interruption before
    // this point recovers straight back to results instead of losing the
    // photos. Gating on justSubmitted (not merely !viewingHistory) is critical:
    // post-pay redirects into this screen (from Home / Payment) must NOT wipe an
    // unrelated in-progress scan draft. The App-level recovery clears its own.
    const justSubmitted = !!(route.params as any)?.justSubmitted;
    useEffect(() => {
        if (!justSubmitted) return;
        void clearPendingFaceScanSubmit().catch(() => undefined);
        void clearFaceScanDraft().catch(() => undefined);
    }, [justSubmitted]);

    useEffect(() => {
        if (scan?.processing_status !== 'processing') return;
        setProcessing(true);
        const appStateRef = { current: AppState.currentState };
        let cancelled = false;
        let timer: ReturnType<typeof setTimeout> | null = null;
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
                if (result.processing_status !== 'processing') { setProcessing(false); return; }
            } catch (e) { console.error(e); }
            if (!cancelled) timer = setTimeout(tick, nextDelay());
        };
        const tick = () => {
            if (appStateRef.current !== 'active') { timer = setTimeout(tick, nextDelay()); return; }
            void doPoll();
        };
        timer = setTimeout(tick, nextDelay());
        const appSub = AppState.addEventListener('change', (next) => {
            const prev = appStateRef.current;
            appStateRef.current = next;
            if (prev.match(/inactive|background/) && next === 'active') void doPoll();
        });
        return () => { cancelled = true; if (timer) clearTimeout(timer); appSub.remove(); };
    }, [scan?.processing_status, scanIdParam]);

    // ── Gate watchdog ─────────────────────────────────────────────────────
    // The funnelV4 gate renders the no-exit AnalyzingScreen while the upload/
    // analysis lands. It must NEVER be infinite: a scan row stranded in
    // "processing" (server died mid-analysis) or an upload that silently
    // failed (row never appears) used to hard-trap users here — full screen,
    // reset stack, no back. After the timeout (or instantly when the row is
    // already stale on arrival) fall through to ScanProcessingView, which has
    // Retry + Back.
    const gateWaiting =
        gateV4 && (scan?.processing_status === 'processing' || (!hydrating && !scan));
    const [gateTimedOut, setGateTimedOut] = useState(false);
    useEffect(() => {
        if (!gateWaiting) { setGateTimedOut(false); return; }
        const createdRaw = (scan as { created_at?: string } | null)?.created_at;
        const createdMs = createdRaw ? Date.parse(createdRaw) : NaN;
        const STALE_ON_ARRIVAL_MS = 4 * 60_000; // backend reaps at 3 min; belt + suspenders
        if (Number.isFinite(createdMs) && Date.now() - createdMs > STALE_ON_ARRIVAL_MS) {
            setGateTimedOut(true);
            return;
        }
        const t = setTimeout(() => setGateTimedOut(true), PROCESSING_TIMEOUT_MS * 2);
        return () => clearTimeout(t);
    }, [gateWaiting, scan]);

    const a = coerceAnalysisObject(scan?.analysis);
    const treatAsPaid = isPaid === true || isScanUser === true || scan?.is_unlocked === true;
    const locked = !treatAsPaid;
    const postPay = !!postPayParam && !locked && postSubscriptionOnboarding;
    // The full "Your Analysis" breakdown is shown ONLY for the user's first scan
    // ever (incl. the locked onboarding teaser + the post-pay reveal). Daily /
    // repeat scans show just the three headline rings at the top — nothing else.
    const isFirstScanEver = locked || postPayParam || scan?.is_first_scan === true;

    // Finish the post-pay flow: clear the post-subscription flag (so HomeScreen
    // stops redirecting back here) and land on Main. Programs are picked later in
    // the marketplace — there's no longer a dedicated picker step.
    const advancePostPay = useCallback(async () => {
        try { await api.dismissPostSubscriptionOnboarding(); } catch (e) { console.error(e); }
        try { await refreshUser(); } catch (e) { console.error(e); }
        navigation.reset({ index: 0, routes: [{ name: 'Main' }] });
    }, [navigation, refreshUser]);

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
    const facialSummary = (user?.onboarding as any)?.facial_scan_summary;
    const archetype =
        (typeof pr?.archetype === 'string' ? pr.archetype.trim() : '') ||
        (typeof pi?.archetype === 'string' ? pi.archetype.trim() : '') ||
        (typeof facialSummary?.archetype === 'string' ? facialSummary.archetype.trim() : '');
    let pslTier = typeof pr?.psl_tier === 'string' ? pr.psl_tier.trim() : '';
    if (!pslTier && typeof a?.psl_tier === 'string') pslTier = a.psl_tier.trim();
    if (!pslTier && typeof facialSummary?.psl_tier === 'string') pslTier = facialSummary.psl_tier.trim();
    if (!pslTier) { const t = inferPslTierFromScore(overallScore); if (t) pslTier = t; }
    // ── New viral metrics (halo / failo / sex+trust / dimorphism / glow-up / first move) ──
    const _num10 = (v: any): number | null => {
        const n = parseFloat(String(v ?? ''));
        return Number.isNaN(n) ? null : Math.max(0, Math.min(10, n));
    };
    const haloFeature = String(pr?.halo_feature || pi?.halo_feature || a?.halo_feature || facialSummary?.halo_feature || '').trim();
    const bottleneck = String(pr?.bottleneck || pi?.bottleneck || a?.bottleneck || facialSummary?.bottleneck || '').trim();
    const bottleneckMax = String(pr?.bottleneck_max || pi?.bottleneck_max || a?.bottleneck_max || facialSummary?.bottleneck_max || '').trim();
    const sexAppeal = _num10(pr?.sex_appeal ?? pi?.sex_appeal ?? a?.sex_appeal ?? facialSummary?.sex_appeal);
    const trustAppeal = _num10(pr?.trust_appeal ?? pi?.trust_appeal ?? a?.trust_appeal ?? facialSummary?.trust_appeal);
    const appealQuadrant = String(pr?.appeal_quadrant || pi?.appeal_quadrant || a?.appeal_quadrant || facialSummary?.appeal_quadrant || '').trim();
    const dimorphism = _num10(pr?.dimorphism ?? pi?.dimorphism ?? a?.dimorphism ?? facialSummary?.dimorphism);
    const dimorphismNote = String(pr?.dimorphism_note || pi?.dimorphism_note || a?.dimorphism_note || facialSummary?.dimorphism_note || '').trim();
    const glowUpLabel = String(pr?.glow_up_label || pi?.glow_up_label || a?.glow_up_label || facialSummary?.glow_up_label || '').trim();
    const firstMove: string[] = (
        Array.isArray(pr?.first_move) ? pr.first_move
        : Array.isArray(pi?.first_move) ? pi.first_move
        : Array.isArray(a?.first_move) ? a.first_move
        : Array.isArray(facialSummary?.first_move) ? facialSummary.first_move
        : []
    ).map(String).filter(Boolean).slice(0, 2);
    const glowUpGain = ratingDisplay != null ? Math.max(0, Math.round((potentialDisplay - ratingDisplay) * 10) / 10) : null;

    // Account-after-scan: an unclaimed (anon) user creates their account first;
    // a claimed user goes straight to the referral/paywall step.
    const isAnon = !!user?.email && String(user.email).endsWith('@anon.trymax.app');
    // V4 gate: the paywall is the next step (account comes after purchase) —
    // unless this is a resumed already-paid/free-tier user, who skips straight
    // to the account step. Legacy locked-results paths keep their old routing.
    const goPayment = () => {
        if (gateV4) {
            navigation.navigate(isPaid || isFreeTier ? 'CreateAccount' : 'Payment');
            return;
        }
        navigation.navigate(isAnon ? 'CreateAccount' : 'ReferralCode');
    };

    const onPrimaryCta = async () => {
        if (isScanUser) { navigation.reset({ index: 0, routes: [{ name: 'FaceScan' }] }); return; }
        if (locked) { goPayment(); return; }
        if (postPay) { void advancePostPay(); return; }
        navigation.navigate('Main');
    };

    const postPayOnboardingFlow = postPay && !viewingHistory;

    const headerBack = () => {
        if (postPayOnboardingFlow) {
            // The post-pay reveal hides the main header Back on purpose (the CTA
            // is the way forward) — but the FALLBACK views (scan row stuck in
            // 'processing', failed analysis) still render a Back control that
            // routes here. It must never be a dead button: a wedged scan used to
            // leave post-pay users tapping a Back that silently no-oped, with
            // gestures and Android back disabled — a hard trap. Finish the
            // post-pay hand-off instead (clear the flag, land on Main), exactly
            // what the happy-path CTA does.
            advancedRef.current = true;
            setAdvancing(true);
            void advancePostPay();
            return;
        }
        if (isScanUser) { navigation.reset({ index: 0, routes: [{ name: 'FaceScan' }] }); return; }
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

    // Snapshot the two views the user actually sees, in order:
    //   [0] the full-screen hero (scan photo + 3 rings) — captured at scroll-top
    //       so the photo background fills the frame,
    //   [1] the white "Your Analysis" sheet — captures full-height on its own.
    // Restores the scroll position (the Share/Save buttons live in the sheet).
    const captureBothViews = async (): Promise<string[]> => {
        const uris: string[] = [];
        // Burn in the "max" watermark for the export only, then wait a frame so
        // it's painted before we snapshot.
        setExportWatermark(true);
        await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
        try {
            // View 2 first — no scroll needed (the user is already on the sheet).
            const analysis = await captureRatingCardToPng(analysisRef);
            // View 1 — jump to the top so the hero fills the screen, then snapshot
            // the whole screen (root holds the fixed background photo).
            scrollRef.current?.scrollTo({ y: 0, animated: false });
            await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
            const hero = await captureRatingCardToPng(rootRef);
            // Restore — bring the buttons back into view.
            scrollRef.current?.scrollToEnd({ animated: false });
            if (hero) uris.push(hero);
            if (analysis) uris.push(analysis);
        } finally {
            setExportWatermark(false);
        }
        return uris;
    };

    const onSaveScanPhoto = async () => {
        if (Platform.OS === 'web') {
            Alert.alert('Save on web', 'Open Max on your phone to save your results to Photos.');
            return;
        }
        setShareCaptureBusy(true);
        try {
            const uris = await captureBothViews();
            if (!uris.length) { Alert.alert('Save failed', 'Could not create the images. Try again.'); return; }
            const perm = await MediaLibrary.requestPermissionsAsync();
            if (!perm.granted) { Alert.alert('Permission needed', 'Allow Photos access to save your results.'); return; }
            for (const u of uris) await MediaLibrary.saveToLibraryAsync(u);
            Alert.alert('Saved', uris.length > 1 ? 'Saved 2 images to Photos.' : 'Saved to Photos.');
        } catch (e) { console.error(e); Alert.alert('Save failed', 'Could not save to Photos. Try again.'); }
        finally { setShareCaptureBusy(false); }
    };

    const onShareRating = async () => {
        const tierLine = pslTier ? ` · Tier: ${pslTier}` : '';
        const r = ratingDisplay != null ? ratingDisplay.toFixed(1) : '—';
        const msg = `My facial analysis on Max: ${r}/10 · Potential: ${potentialDisplay.toFixed(1)}/10${tierLine}`;
        if (Platform.OS === 'web') {
            try {
                const nav = typeof globalThis !== 'undefined' ? (globalThis as any).navigator : undefined;
                if (nav?.share) { await nav.share({ title: 'My Max results', text: msg }); return; }
                if (nav?.clipboard?.writeText) { await nav.clipboard.writeText(msg); Alert.alert('Copied', 'Results text copied to clipboard.'); return; }
            } catch { /* fall through */ }
            Alert.alert('My Max results', msg);
            return;
        }
        setShareCaptureBusy(true);
        try {
            const uris = await captureBothViews();
            if (!uris.length) { await Share.share({ message: msg, title: 'My Max results' }); return; }
            const canShareFiles = await Sharing.isAvailableAsync();
            if (canShareFiles) {
                // expo-sharing sends one file per sheet — share each view in turn.
                for (const u of uris) {
                    try {
                        await Sharing.shareAsync(u, { mimeType: 'image/png', dialogTitle: 'Share your Max results' });
                    } catch (e: any) {
                        if (e?.message === 'User did not share') break; // user cancelled — stop
                        throw e;
                    }
                }
            } else {
                await Share.share({ title: 'My Max results', message: msg, url: uris[0] } as any);
            }
        } catch (e: any) {
            if (e?.message !== 'User did not share') console.error(e);
            try { await Share.share({ message: msg, title: 'My Max results' }); } catch { /* ignore */ }
        } finally { setShareCaptureBusy(false); }
    };

    // ── Early exit states ──────────────────────────────────────────────────────

    // gateV4 + no scan row yet = the background upload is still in flight.
    // The gate waits on the classic rotating-bust AnalyzingScreen (step 1 while
    // the upload lands, step 2 once the analysis is processing); other paths
    // keep the plain processing view with its retry affordance.
    if (scan?.processing_status === 'processing' || (gateV4 && !hydrating && !scan)) {
        if (gateV4 && !gateTimedOut) {
            return (
                <AnalyzingScreen
                    currentStep={scan ? 2 : 1}
                    onCancel={() => setGateTimedOut(true)}
                />
            );
        }
        return <ScanProcessingView onRetry={bootstrap} onBack={headerBack} />;
    }
    if ((hydrating && !scan) || (advancing && !scan)) {
        return <View style={[s.root, s.fetchingRoot]}><ActivityIndicator size="large" color={colors.foreground} /></View>;
    }
    if (!hydrating && !scan) {
        return (
            <View style={[s.root, s.fetchingRoot]}>
                <Text style={s.fetchErrorText}>Couldn&apos;t load your scan.</Text>
                <TouchableOpacity style={s.fetchRetryBtn} onPress={bootstrap} activeOpacity={0.85}>
                    <Text style={s.fetchRetryText}>Try again</Text>
                </TouchableOpacity>
                {treatAsPaid ? (
                    <TouchableOpacity style={s.fetchSkipBtn} onPress={() => {
                        advancedRef.current = true; setAdvancing(true);
                        if (postPayParam) advancePostPay(); else navigation.navigate('Main');
                    }} activeOpacity={0.85}>
                        <Text style={s.fetchSkipText}>Skip for now</Text>
                    </TouchableOpacity>
                ) : null}
            </View>
        );
    }
    // Failed scan or completed scan with no analysis both render as a blank
    // screen — catch them here and give the user an actionable error + retry.
    const scanFailed = scan?.processing_status === 'failed';
    const missingAnalysis = !hydrating && scan && scan.processing_status === 'completed' && !a;
    if (scanFailed || missingAnalysis) {
        const goRescan = () => {
            if (isScanUser) navigation.reset({ index: 0, routes: [{ name: 'FaceScan' }] });
            else if (navigation.canGoBack()) navigation.goBack();
            else navigation.navigate('FaceScan');
        };
        return (
            <View style={[s.root, s.fetchingRoot]}>
                <Text style={s.fetchErrorText}>
                    {scanFailed
                        ? 'Analysis didn’t complete. Try scanning again with clear, well-lit photos.'
                        : 'Results aren’t ready yet. Pull to retry or scan again.'}
                </Text>
                <TouchableOpacity style={s.fetchRetryBtn} onPress={missingAnalysis ? bootstrap : goRescan} activeOpacity={0.85}>
                    <Text style={s.fetchRetryText}>{missingAnalysis ? 'Retry' : 'Scan again'}</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.fetchSkipBtn} onPress={headerBack} activeOpacity={0.85}>
                    <Text style={s.fetchSkipText}>Back</Text>
                </TouchableOpacity>
            </View>
        );
    }

    // Metric cards data
    const METRICS = [
        {
            key: 'rating',
            label: 'Rating',
            score: ratingDisplay ?? 0,
            // Dark purple (luminous violet → deep purple) — same style as Potential.
            gradient: ['#A77BFF', '#5B2BB0'] as const,
            desc: ratingDisplay != null && ratingDisplay >= 7
                ? 'You rank in the top tier of facial attractiveness.'
                : ratingDisplay != null && ratingDisplay >= 5
                    ? 'Above average with strong structural features.'
                    : 'Significant improvement is achievable with consistent effort.',
        },
        {
            key: 'appeal',
            label: 'Appeal',
            score: appealScore,
            // Dark green (luminous → deep emerald) — same style as Potential.
            gradient: ['#4FD08A', '#157A45'] as const,
            desc: appealScore >= 7
                ? 'Exceptional facial harmony and symmetry.'
                : appealScore >= 5
                    ? 'Strong appeal with balanced proportions.'
                    : 'Targeted improvements can meaningfully increase your appeal.',
        },
        {
            key: 'potential',
            label: 'Potential',
            score: potentialDisplay,
            // Electric azure → indigo-violet — deep and premium, not pastel blue.
            gradient: ['#4DA3FF', '#6C5CE7'] as const,
            desc: potentialDisplay >= 9
                ? 'Near maximum potential — maintain your gains.'
                : potentialDisplay >= 8
                    ? 'High ceiling — consistent effort will get you there.'
                    : 'Significant potential unlocked through dedicated looksmaxxing.',
        },
    ];

    // The "Your Analysis" bento: named sections with deliberately mixed card
    // sizes — a Rating hero, a wide Potential card, square stat rows, and a
    // per-feature grid. Appeal is the one free metric; everything else stays
    // locked behind the paywall (lock icon in place of the value).
    const umaxRows: any[] = Array.isArray(a?.umax_metrics) ? a.umax_metrics : [];
    const features: BentoFeatureItem[] = umaxRows
        .map((row, i): BentoFeatureItem | null => {
            const id = String(row?.id || '').trim();
            const sc = parseFloat(String(row?.score ?? ''));
            if (!id || Number.isNaN(sc)) return null;
            const name = UMAX_LABELS[id] || (id.charAt(0).toUpperCase() + id.slice(1).replace(/_/g, ' '));
            return {
                key: `umax-${id}-${i}`,
                name,
                value: `${Math.round(Math.max(0, Math.min(10, sc)) * 10) / 10}`,
                accent: FEATURE_PALETTE[i % FEATURE_PALETTE.length],
            };
        })
        .filter((x): x is BentoFeatureItem => x !== null);

    return (
        <View style={s.root} ref={rootRef} collapsable={false}>

            {/* ── Fixed photo background ───────────────────────────────── */}
            {frontUri ? (
                <CachedImage uri={frontUri} style={StyleSheet.absoluteFill} resizeMode="cover" />
            ) : (
                <View style={[StyleSheet.absoluteFill, { backgroundColor: '#1A1A1A' }]} />
            )}
            <LinearGradient
                pointerEvents="none"
                colors={['rgba(0,0,0,0.10)', 'rgba(0,0,0,0.06)', 'rgba(0,0,0,0.16)', 'rgba(0,0,0,0.30)']}
                locations={[0, 0.42, 0.7, 1]}
                style={StyleSheet.absoluteFill}
            />

            {/* ── Fixed back button ─────────────────────────────────────── */}
            {!postPayOnboardingFlow ? (
                <TouchableOpacity
                    style={[s.backBtn, { top: Math.max(insets.top, 14) + 4 }]}
                    onPress={headerBack}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    accessibilityRole="button"
                    accessibilityLabel="Back"
                >
                    <Ionicons name="arrow-back" size={20} color="#FFFFFF" />
                </TouchableOpacity>
            ) : null}

            {/* ── Scrollable content ────────────────────────────────────── */}
            <ScrollView
                ref={scrollRef}
                style={{ flex: 1 }}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={{ paddingBottom: 0 }}
            >
                {/* Hero section — transparent, full screen height. Before any
                    scroll the only things over the photo are the face-frame
                    brackets and the three floating, hovering windows. */}
                <View style={{ height: SCREEN_H }}>
                    {/* Face-framing brackets — a portrait frame centered over the
                        face (front-scan faces sit roughly mid-frame, slightly high) */}
                    <View
                        pointerEvents="none"
                        style={{
                            position: 'absolute',
                            left: SCREEN_W * 0.24,
                            right: SCREEN_W * 0.24,
                            top: SCREEN_H * 0.30,
                            height: SCREEN_H * 0.30,
                        }}
                    >
                        <View style={[fr.base, fr.tl]} />
                        <View style={[fr.base, fr.tr]} />
                        <View style={[fr.base, fr.bl]} />
                        <View style={[fr.base, fr.br]} />
                    </View>

                    {/* White dissolve — a long, gradual ramp so the portrait melts
                        into the white sheet with no visible seam. Stays mostly
                        translucent (photo shows through) and only reaches pure
                        white in the last sliver, right where the sheet begins. */}
                    <LinearGradient
                        pointerEvents="none"
                        colors={[
                            'rgba(255,255,255,0)',
                            'rgba(255,255,255,0.04)',
                            'rgba(255,255,255,0.12)',
                            'rgba(255,255,255,0.28)',
                            'rgba(255,255,255,0.5)',
                            'rgba(255,255,255,0.78)',
                            '#FFFFFF',
                            '#FFFFFF',
                        ]}
                        locations={[0, 0.18, 0.34, 0.48, 0.6, 0.7, 0.78, 1]}
                        style={[s.heroWhiteFade, { height: SCREEN_H * 0.46 }]}
                    />

                    {/* 3 floating windows — staggered into a downward triangle
                        (center sits lower) and gently bopping up and down. */}
                    <View style={[s.cardsRow, { bottom: SCREEN_H * 0.17 }]} pointerEvents="box-none">
                        {METRICS.map((m, i) => (
                            <HoverCard key={m.key} style={s.cardHover} baseY={i === 1 ? 18 : 0} delay={i * 260}>
                                <GlassCard
                                    dark
                                    radius={22}
                                    onPress={() => setExpandedIdx(i)}
                                    accessibilityLabel={`${m.label} score`}
                                    style={s.metricCardOuter}
                                    contentStyle={s.metricCardContent}
                                >
                                    <View style={s.ringWrap}>
                                        <MetricRing
                                            score={locked && !gateV4 ? 0 : m.score}
                                            outOf={10}
                                            delay={i * 180}
                                            gradient={m.gradient}
                                            gid={`ring-${m.key}`}
                                            size={72}
                                        />
                                        <View style={s.ringCenter} pointerEvents="none">
                                            {locked && !gateV4 ? (
                                                <Ionicons name="lock-closed" size={18} color="rgba(255,255,255,0.6)" />
                                            ) : isProcessing ? (
                                                <ActivityIndicator color="#FFFFFF" size="small" />
                                            ) : (
                                                <Text style={s.metricScore}>{m.score.toFixed(1)}</Text>
                                            )}
                                        </View>
                                    </View>
                                    <Text style={s.metricLabel}>{m.label}</Text>
                                </GlassCard>
                            </HoverCard>
                        ))}
                    </View>

                    {/* Scroll cue — invites the user down into the locked breakdown
                        (archetype + verdict) that sits below the teaser rings. */}
                    <ScrollCue onPress={() => scrollRef.current?.scrollTo({ y: SCREEN_H - 60, animated: true })} />
                </View>

                {/* ── Stats section — the analysis breakdown. In the V4 gate it
                    renders too, fully LOCKED (archetype + verdict masked), so the
                    teaser conveys everything the unlock buys — not just 3 rings.
                    Extra bottom padding in the gate clears the floating CTA. ── */}
                {(
                <View ref={analysisRef} collapsable={false} style={[s.statsSection, { paddingBottom: Math.max(insets.bottom, 24) + (gateV4 ? 100 : 24) }]}>

                    {/* Export-only "max" watermark for the analysis capture (white). */}
                    {exportWatermark ? (
                        <View style={s.watermarkAnalysis} pointerEvents="none">
                            <Text style={[s.watermarkText, s.watermarkOnLight]}>max</Text>
                        </View>
                    ) : null}

                    {/* Full breakdown only on the first scan ever; daily/repeat
                        scans show just the three rings above. */}
                    {isFirstScanEver ? (
                        <Text style={s.statsSectionTitle}>Your Analysis</Text>
                    ) : null}

                    {/* Face archetype — same unified gate as the verdict cards
                        below: the "Archetype" label is part of the locked paywall
                        promise (so the user knows it was measured); the value is
                        masked when locked and revealed when paid. Renders for any
                        non-processing scan so the locked teaser and the paid reveal
                        always carry the same card (parity), only the value differs. */}
                    {isFirstScanEver && !isProcessing ? (
                        <GlassCard radius={20} style={s.archetypeCardOuter} contentStyle={s.archetypeCardContent}>
                            <Text style={s.archetypeKicker}>YOUR ARCHETYPE</Text>
                            {locked ? (
                                <>
                                    <Text style={s.archetypeName}>—</Text>
                                    <Text style={s.archetypeDesc}>Unlock to reveal which archetype your face reads as.</Text>
                                </>
                            ) : archetype ? (
                                <>
                                    <Text style={s.archetypeName} numberOfLines={2} adjustsFontSizeToFit>{archetype}</Text>
                                    {archetypeLine(archetype, ratingDisplay) ? (
                                        <Text style={s.archetypeDesc}>{archetypeLine(archetype, ratingDisplay)}</Text>
                                    ) : null}
                                </>
                            ) : (
                                <>
                                    <Text style={s.archetypeName}>Not measured</Text>
                                    <Text style={s.archetypeDesc}>This scan didn't return an archetype.</Text>
                                </>
                            )}
                        </GlassCard>
                    ) : null}

                    {/* ── Verdict: the viral read + the one First Move ─────── */}
                    {isFirstScanEver && !isProcessing ? (
                        <View style={s.verdict}>
                            {/* Always render every metric card when not processing so
                                the locked teaser and the paid reveal carry the SAME
                                set (parity). Locked masks the value; unlocked shows
                                the real value, or a graceful "Not measured" when the
                                data is genuinely absent — never drop the card. */}
                            {(
                                <GlassCard dark radius={22} style={s.firstMoveCardOuter} contentStyle={s.firstMoveCardContent}>
                                    <View style={{ flex: 1 }}>
                                        <Text style={s.firstMoveKicker}>YOUR FIRST MOVE</Text>
                                        {locked ? (
                                            <View style={s.firstMoveLockRow}>
                                                <Ionicons name="lock-closed" size={19} color="#FFFFFF" />
                                                <Text style={s.firstMoveValue}>Locked</Text>
                                            </View>
                                        ) : (
                                            <Text style={s.firstMoveValue}>{firstMove.length > 0 ? formatSuggestedModuleTitle(firstMove[0]) : 'Not measured'}</Text>
                                        )}
                                        <Text style={s.firstMoveSub}>
                                            {locked ? 'Unlock to see exactly where to start.' : 'Start here. The one move that moves the needle most.'}
                                        </Text>
                                    </View>
                                </GlassCard>
                            )}

                            {(
                                <View style={s.verdictRow}>
                                    <GlassCard radius={18} style={s.verdictCardOuter} contentStyle={s.verdictCardContent}>
                                        <View style={[s.verdictDot, { backgroundColor: '#2F6B4E' }]} />
                                        <Text style={s.verdictLabel}>YOUR HALO</Text>
                                        <Text style={s.verdictValue} numberOfLines={2} adjustsFontSizeToFit>{locked ? '—' : (haloFeature || 'Not measured')}</Text>
                                        <Text style={s.verdictSub}>Your biggest natural edge.</Text>
                                    </GlassCard>
                                    <GlassCard radius={18} style={s.verdictCardOuter} contentStyle={s.verdictCardContent}>
                                        <View style={[s.verdictDot, { backgroundColor: '#C0452C' }]} />
                                        <Text style={s.verdictLabel}>BOTTLENECK</Text>
                                        <Text style={s.verdictValue} numberOfLines={2} adjustsFontSizeToFit>{locked ? '—' : (bottleneck || 'Not measured')}</Text>
                                        <Text style={s.verdictSub}>{!locked && bottleneckMax ? `Fix it with ${formatSuggestedModuleTitle(bottleneckMax)}.` : 'What is holding you back.'}</Text>
                                    </GlassCard>
                                </View>
                            )}

                            {(
                                <GlassCard radius={18} style={s.appealCardOuter} contentStyle={s.appealCardContent}>
                                    <Text style={s.verdictLabel}>SEX APPEAL vs TRUST APPEAL</Text>
                                    {locked ? (
                                        <View style={s.appealRow}>
                                            <View style={s.appealCol}>
                                                <Text style={s.appealNum}>—</Text>
                                                <Text style={s.appealColLabel}>Sex appeal</Text>
                                            </View>
                                            <View style={s.appealDivider} />
                                            <View style={s.appealCol}>
                                                <Text style={s.appealNum}>—</Text>
                                                <Text style={s.appealColLabel}>Trust appeal</Text>
                                            </View>
                                        </View>
                                    ) : (
                                        <>
                                            <View style={s.appealRow}>
                                                <View style={s.appealCol}>
                                                    <Text style={s.appealNum}>{(sexAppeal ?? 0).toFixed(1)}</Text>
                                                    <Text style={s.appealColLabel}>Sex appeal</Text>
                                                </View>
                                                <View style={s.appealDivider} />
                                                <View style={s.appealCol}>
                                                    <Text style={s.appealNum}>{(trustAppeal ?? 0).toFixed(1)}</Text>
                                                    <Text style={s.appealColLabel}>Trust appeal</Text>
                                                </View>
                                            </View>
                                            {appealQuadrant ? <Text style={s.appealQuadrant}>{appealQuadrant}</Text> : null}
                                        </>
                                    )}
                                </GlassCard>
                            )}

                            {(
                                <View style={s.verdictRow}>
                                    <GlassCard radius={18} style={s.verdictCardOuter} contentStyle={s.verdictCardContent}>
                                        <View style={[s.verdictDot, { backgroundColor: '#4A4A70' }]} />
                                        <Text style={s.verdictLabel}>DIMORPHISM</Text>
                                        <Text style={s.verdictValue}>{locked ? '—' : (dimorphism == null ? 'Not measured' : `${dimorphism.toFixed(1)}/10`)}</Text>
                                        <Text style={s.verdictSub} numberOfLines={2}>{locked || !dimorphismNote ? 'Masculine vs soft balance.' : dimorphismNote}</Text>
                                    </GlassCard>
                                    <GlassCard radius={18} style={s.verdictCardOuter} contentStyle={s.verdictCardContent}>
                                        <View style={[s.verdictDot, { backgroundColor: '#BC8B57' }]} />
                                        <Text style={s.verdictLabel}>GLOW-UP POTENTIAL</Text>
                                        <Text style={s.verdictValue}>{locked ? '—' : (glowUpLabel || 'Not measured')}</Text>
                                        <Text style={s.verdictSub}>{!locked && glowUpGain ? `Est. +${glowUpGain.toFixed(1)} points` : 'How much is in your control.'}</Text>
                                    </GlassCard>
                                </View>
                            )}
                        </View>
                    ) : null}

                    {/* While the scan is still computing, a quiet placeholder. The
                        dense per-feature breakdown was removed — the read above (the
                        seven coach metrics) is the analysis now. */}
                    {isProcessing ? (
                        <View style={s.processingPlaceholder}>
                            <ActivityIndicator color={colors.foreground} />
                            <Text style={s.processingText}>Calculating your scores…</Text>
                        </View>
                    ) : null}

                    {/* Share / Save row */}
                    {!locked && !isProcessing ? (
                        <View style={s.shareRow}>
                            <TouchableOpacity style={[s.shareBtn, shareCaptureBusy && s.shareBtnDisabled]}
                                onPress={onSaveScanPhoto} activeOpacity={0.7} disabled={shareCaptureBusy}>
                                <Ionicons name="download-outline" size={14} color={colors.textMuted} />
                                <Text style={s.shareBtnText}>Save</Text>
                            </TouchableOpacity>
                            <View style={s.shareDot} />
                            <TouchableOpacity style={[s.shareBtn, shareCaptureBusy && s.shareBtnDisabled]}
                                onPress={onShareRating} activeOpacity={0.7} disabled={shareCaptureBusy}>
                                <Ionicons name="share-outline" size={14} color={colors.textMuted} />
                                <Text style={s.shareBtnText}>Share</Text>
                            </TouchableOpacity>
                        </View>
                    ) : null}

                    <Text style={s.disclaimer}>For general wellness only. Not medical advice.</Text>

                    {/* CTA — hidden in the V4 gate (the floating gate CTA below is
                        the single sticky "Unlock full results" there). */}
                    {!viewingHistory && !gateV4 ? (
                        <>
                            <TouchableOpacity style={s.cta} onPress={onPrimaryCta} activeOpacity={0.85} accessibilityLabel="Unlock full results">
                                <Text style={s.ctaText}>
                                    {isScanUser ? 'Scan Again' : locked ? 'Unlock full results' : postPay ? 'Get started' : 'Continue'}
                                </Text>
                                <Ionicons name={isScanUser ? 'camera-outline' : locked ? 'lock-open-outline' : 'arrow-forward'}
                                    size={17} color="#FFFFFF" />
                            </TouchableOpacity>
                            {!isScanUser && !locked && !postSubscriptionOnboarding ? (
                                <TouchableOpacity style={s.skipBtn} onPress={() => navigation.navigate('Main')} activeOpacity={0.7}>
                                    <Text style={s.skipText}>Go to home</Text>
                                </TouchableOpacity>
                            ) : null}
                        </>
                    ) : null}
                </View>
                )}
            </ScrollView>

            {/* ── V4 gate CTA — overlays the hero (nothing below the fold) ── */}
            {gateV4 ? (
                <View style={[s.gateCtaWrap, { bottom: Math.max(insets.bottom, 20) + 10 }]} pointerEvents="box-none">
                    <TouchableOpacity style={s.cta} onPress={goPayment} activeOpacity={0.85} accessibilityRole="button" accessibilityLabel="Unlock full results">
                        <Text style={s.ctaText}>Unlock full results</Text>
                        <Ionicons name="lock-open-outline" size={17} color="#FFFFFF" />
                    </TouchableOpacity>
                </View>
            ) : null}

            {/* ── Expanded metric overlay ───────────────────────────────── */}
            {expandedIdx !== null ? (
                <Pressable
                    style={[StyleSheet.absoluteFill, s.expandedOverlay]}
                    onPress={() => setExpandedIdx(null)}
                >
                    <BlurView intensity={70} tint="dark" style={StyleSheet.absoluteFill} />
                    <Pressable style={s.expandedCard} onPress={() => {}}>
                        <MetricRing
                            score={locked && !gateV4 ? 0 : METRICS[expandedIdx].score}
                            outOf={10}
                            delay={0}
                            gradient={METRICS[expandedIdx].gradient}
                            gid={`ring-exp-${METRICS[expandedIdx].key}`}
                            size={160}
                        />
                        <View style={s.expandedCenter} pointerEvents="none">
                            {locked && !gateV4 ? (
                                <Ionicons name="lock-closed" size={38} color="rgba(255,255,255,0.85)" />
                            ) : (
                                <View style={s.expandedScoreRow}>
                                    <Text style={s.expandedScore}>{METRICS[expandedIdx].score.toFixed(1)}</Text>
                                    <Text style={s.expandedUnit}>/10</Text>
                                </View>
                            )}
                        </View>
                        <Text style={s.expandedLabel}>{METRICS[expandedIdx].label}</Text>
                        <Text style={s.expandedDesc}>
                            {locked && !gateV4
                                ? 'Unlock your full results to reveal this score.'
                                : METRICS[expandedIdx].desc}
                        </Text>
                        {locked ? (
                            <TouchableOpacity style={s.expandedUnlock} onPress={() => { setExpandedIdx(null); goPayment(); }} activeOpacity={0.85} accessibilityLabel="Unlock full results">
                                <Ionicons name="lock-open-outline" size={15} color="#111111" />
                                <Text style={s.expandedUnlockText}>Unlock full results</Text>
                            </TouchableOpacity>
                        ) : null}
                        <TouchableOpacity style={s.expandedClose} onPress={() => setExpandedIdx(null)}
                            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                            <Ionicons name="close" size={20} color="rgba(255,255,255,0.7)" />
                        </TouchableOpacity>
                    </Pressable>
                </Pressable>
            ) : null}

            {/* ── Glassy stat elaboration overlay (no paywall jump) ─────── */}
            {detail ? (
                <Pressable style={[StyleSheet.absoluteFill, s.detailOverlay]} onPress={closeDetail}>
                    <Animated.View style={[StyleSheet.absoluteFill, { opacity: detailAnim }]}>
                        <BlurView intensity={36} tint="dark" style={StyleSheet.absoluteFill} />
                        <View style={[StyleSheet.absoluteFill, s.detailScrim]} />
                    </Animated.View>
                    <Animated.View
                        style={[
                            s.detailCardWrap,
                            {
                                opacity: detailAnim,
                                transform: [
                                    { scale: detailAnim.interpolate({ inputRange: [0, 1], outputRange: [0.84, 1] }) },
                                    { translateY: detailAnim.interpolate({ inputRange: [0, 1], outputRange: [22, 0] }) },
                                ],
                            },
                        ]}
                    >
                        <Pressable style={[s.detailCard, { borderColor: `${detail.accent}55` }]} onPress={() => {}}>
                            <View style={s.detailInner}>
                                <View style={[bento.dot, { backgroundColor: detail.accent, marginBottom: 16 }]} />
                                <Text style={s.detailName}>{detail.name}</Text>
                                <Text style={s.detailBlurb}>{detail.blurb}</Text>
                                {detail.locked ? (
                                    <View style={s.detailLockRow}>
                                        <Ionicons name="lock-closed" size={13} color={detail.accent} />
                                        <Text style={[s.detailLockText, { color: detail.accent }]}>
                                            Unlock your full results to see your score
                                        </Text>
                                    </View>
                                ) : null}
                            </View>
                            <TouchableOpacity style={s.detailClose} onPress={closeDetail}
                                hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                                <Ionicons name="close" size={18} color={BENTO_INK} />
                            </TouchableOpacity>
                        </Pressable>
                    </Animated.View>
                </Pressable>
            ) : null}

            {/* Off-screen share card retired — Save/Share now snapshot the real
                hero + analysis views (see captureBothViews). */}

            {/* Export-only "max" watermark over the hero capture (dark photo). */}
            {exportWatermark ? (
                <View style={s.watermark} pointerEvents="none">
                    <Text style={[s.watermarkText, s.watermarkOnDark]}>max</Text>
                </View>
            ) : null}
        </View>
    );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: '#111111' },

    /* ── Verdict block (viral metrics + first move) ── */
    verdict: { marginTop: 6, marginBottom: 6 },
    firstMoveCardOuter: { marginBottom: 12 },
    firstMoveCardContent: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingVertical: 20 },
    firstMoveKicker: { fontFamily: 'Matter-SemiBold', fontSize: 11, letterSpacing: 1.2, color: 'rgba(255,255,255,0.55)', marginBottom: 6 },
    firstMoveLockRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    firstMoveValue: { fontFamily: fonts.serif, fontSize: 28, color: '#FFFFFF', letterSpacing: -0.5 },
    firstMoveSub: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: 'rgba(255,255,255,0.5)', marginTop: 6 },
    verdictRow: { flexDirection: 'row', gap: 10, marginBottom: 12 },
    verdictCardOuter: { flex: 1, minHeight: 118 },
    verdictCardContent: { flex: 1, minHeight: 118, padding: 16 },
    verdictDot: { width: 8, height: 8, borderRadius: 4, marginBottom: 10 },
    verdictLabel: { fontFamily: 'Matter-Medium', fontSize: 10.5, letterSpacing: 0.8, color: BENTO_SUB, textTransform: 'uppercase' },
    verdictValue: { fontFamily: fonts.serif, fontSize: 20, color: BENTO_INK, letterSpacing: -0.3, marginTop: 5 },
    verdictSub: { fontFamily: 'Matter-Regular', fontSize: 11.5, color: BENTO_SUB, marginTop: 6, lineHeight: 15 },
    appealCardOuter: { marginBottom: 12 },
    appealCardContent: { padding: 18 },
    appealRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
    appealCol: { flex: 1, alignItems: 'center' },
    appealDivider: { width: StyleSheet.hairlineWidth, alignSelf: 'stretch', backgroundColor: 'rgba(0,0,0,0.1)' },
    appealNum: { fontFamily: fonts.serif, fontSize: 30, color: BENTO_INK, letterSpacing: -0.5 },
    appealColLabel: { fontFamily: 'Matter-Medium', fontSize: 11.5, color: BENTO_SUB, marginTop: 2 },
    appealQuadrant: { fontFamily: 'Matter-SemiBold', fontSize: 13.5, color: '#B0556F', textAlign: 'center', marginTop: 14 },

    /* ── Loading / fetching ── */
    loadingRoot: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.lg },
    fetchingRoot: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.xl, backgroundColor: colors.background },
    fetchErrorText: { ...typography.body, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.md },
    fetchRetryBtn: { backgroundColor: colors.foreground, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: borderRadius.full },
    fetchRetryText: { ...typography.button, color: colors.background },
    fetchSkipBtn: { marginTop: spacing.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.sm + 2, borderRadius: borderRadius.full, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
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

    /* ── Paywall ── */
    paywallBlurShell: { borderRadius: 8, overflow: 'hidden', backgroundColor: colors.surface, position: 'relative', alignSelf: 'stretch', width: '100%' },
    paywallFlatOverlay: { backgroundColor: 'rgba(245,245,243,0.55)' },

    /* ── Back button ── */
    backBtn: {
        position: 'absolute',
        left: 20,
        zIndex: 10,
        width: 40, height: 40, borderRadius: 20,
        backgroundColor: 'rgba(0,0,0,0.35)',
        borderWidth: 1, borderColor: 'rgba(255,255,255,0.18)',
        alignItems: 'center', justifyContent: 'center',
    },

    /* ── Metric cards row — floats over the photo, above the white dissolve ── */
    cardsRow: {
        position: 'absolute',
        left: 20, right: 20,
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: 10,
    },
    cardHover: { flex: 1 },
    metricCardOuter: { flex: 1 },
    metricCardContent: { alignItems: 'center', paddingVertical: 16, paddingHorizontal: 8 },
    ringWrap: { width: 72, height: 72, alignItems: 'center', justifyContent: 'center' },
    ringCenter: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
    metricScore: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 17,
        color: '#FFFFFF',
        letterSpacing: -0.5,
    },
    metricLabel: {
        fontFamily: 'Matter-Medium',
        fontSize: 11,
        color: 'rgba(255,255,255,0.65)',
        letterSpacing: 0.3,
        marginTop: 8,
    },

    /* white fade at the bottom of the hero — height is set inline per screen */
    heroWhiteFade: {
        position: 'absolute',
        left: 0, right: 0, bottom: 0,
    },

    /* minimal scroll cue sitting in the white space at the hero's base.
       bottom must clear the 48px sheet overlap so the white sheet (a later
       sibling) doesn't paint over it. */
    scrollCue: {
        position: 'absolute',
        bottom: 66,
        left: 0, right: 0,
        alignItems: 'center',
        zIndex: 5,
    },

    /* ── Stats section ── */
    statsSection: {
        backgroundColor: '#FFFFFF',
        paddingHorizontal: 20,
        // Keep "Your Analysis" below the first viewport — only the white sheet
        // (no title) shows before the user scrolls.
        paddingTop: 64,
        // Overlap into the gradient's solid-white tail (bottom ~22% of the fade is
        // pure #FFFFFF) so the opaque sheet's top edge is white-on-white — no seam.
        marginTop: -48,
    },
    statsSectionTitle: {
        fontFamily: fonts.serif,
        fontSize: 28,
        color: colors.foreground,
        letterSpacing: -0.8,
        marginBottom: 20,
    },
    archetypeLine: {
        fontFamily: 'Matter-Regular',
        fontSize: 14,
        lineHeight: 20,
        color: colors.textMuted,
        marginTop: -10,
        marginBottom: 22,
    },
    /* Face archetype — the identity headline card above the read. */
    archetypeCardOuter: { marginBottom: 12 },
    archetypeCardContent: { padding: 18 },
    archetypeKicker: { fontFamily: 'Matter-Medium', fontSize: 10.5, letterSpacing: 0.8, color: BENTO_SUB, textTransform: 'uppercase' },
    archetypeName: { fontFamily: fonts.serif, fontSize: 30, color: BENTO_INK, letterSpacing: -0.6, marginTop: 7, lineHeight: 34 },
    archetypeDesc: { fontFamily: 'Matter-Regular', fontSize: 13, lineHeight: 19, color: BENTO_SUB, marginTop: 9 },
    breakdownHint: {
        fontFamily: 'Matter-Regular',
        fontSize: 13,
        color: colors.textMuted,
        marginTop: -6,
        marginBottom: 2,
    },

    /* ── Insight grid ── */
    insightGrid: { gap: 10, marginBottom: 24 },
    insightRow: { flexDirection: 'row', gap: 10 },

    processingPlaceholder: { alignItems: 'center', paddingVertical: 40, gap: 12 },
    processingText: { fontFamily: 'Matter-Regular', fontSize: 14, color: colors.textMuted },

    /* ── Recommended ── */
    recsSection: { marginBottom: 24 },
    recsHeading: { fontSize: 10, fontWeight: '600', color: colors.textMuted, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 12, opacity: 0.7 },
    recsPills: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    recPill: { paddingVertical: 8, paddingHorizontal: 16, borderRadius: borderRadius.full, borderWidth: 1, borderColor: 'rgba(0,0,0,0.1)' },
    recPillText: { fontSize: 12, fontWeight: '500', color: colors.foreground, letterSpacing: 0.1 },

    /* ── Paywall teaser ── */
    paywallTeaser: { alignItems: 'center', paddingVertical: 24, marginBottom: 4 },
    paywallTitle: { fontFamily: fonts.serif, fontSize: 18, fontWeight: '500', color: colors.foreground, letterSpacing: -0.3 },
    paywallSub: { fontSize: 13, lineHeight: 19, color: colors.textMuted, textAlign: 'center', marginTop: 8, maxWidth: 240 },

    /* ── Share ── */
    shareRow: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 16, marginBottom: 20 },
    shareBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6 },
    shareBtnText: { fontSize: 12, fontWeight: '500', color: colors.textMuted },
    shareBtnDisabled: { opacity: 0.3 },
    shareDot: { width: 3, height: 3, borderRadius: 1.5, backgroundColor: colors.textMuted, opacity: 0.25 },

    /* ── Export-only "max" watermark (burned into Save/Share images, never shown live) ── */
    watermark: { position: 'absolute', left: 20, bottom: 20 },
    watermarkAnalysis: { position: 'absolute', right: 20, top: 18 },
    watermarkText: { fontFamily: fonts.serif, fontSize: 18, letterSpacing: 0.5 },
    watermarkOnDark: {
        color: 'rgba(255,255,255,0.92)',
        textShadowColor: 'rgba(0,0,0,0.55)',
        textShadowOffset: { width: 0, height: 1 },
        textShadowRadius: 6,
    },
    watermarkOnLight: { color: 'rgba(17,17,19,0.72)' },

    /* ── Disclaimer ── */
    disclaimer: { fontSize: 9, color: colors.textMuted, textAlign: 'center', marginBottom: 20, opacity: 0.3 },

    /* ── CTA ── */
    cta: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
        backgroundColor: colors.foreground, paddingVertical: 16, borderRadius: borderRadius.full,
    },
    ctaText: { fontSize: 14, fontWeight: '600', color: colors.background, letterSpacing: 0.3 },
    /* V4 gate: the CTA floats over the hero (below the rings). */
    gateCtaWrap: { position: 'absolute', left: 24, right: 24, zIndex: 10 },
    skipBtn: { alignItems: 'center', paddingVertical: 14 },
    skipText: { fontSize: 12, color: colors.textMuted, fontWeight: '500' },

    /* ── Expanded overlay ── */
    expandedOverlay: { zIndex: 100, alignItems: 'center', justifyContent: 'center' },
    expandedCard: {
        width: 280,
        alignItems: 'center',
        paddingTop: 32,
        paddingBottom: 32,
        paddingHorizontal: 24,
        borderRadius: 32,
        backgroundColor: 'rgba(255,255,255,0.08)',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.18)',
        overflow: 'hidden',
    },
    expandedCenter: {
        position: 'absolute',
        top: 32, left: 24, right: 24,
        height: 160,
        alignItems: 'center',
        justifyContent: 'center',
    },
    expandedScoreRow: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        justifyContent: 'center',
    },
    expandedScore: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 40,
        color: '#FFFFFF',
        letterSpacing: -1.5,
        lineHeight: 42,
    },
    expandedUnit: {
        fontFamily: 'Matter-Regular',
        fontSize: 14,
        color: 'rgba(255,255,255,0.5)',
        marginLeft: 2,
        marginBottom: 6,
    },
    expandedUnlock: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 7,
        backgroundColor: '#FFFFFF',
        borderRadius: 999,
        paddingHorizontal: 18,
        paddingVertical: 11,
        marginTop: 18,
    },
    expandedUnlockText: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 14,
        color: '#111111',
        letterSpacing: 0.1,
    },
    expandedLabel: {
        fontFamily: 'Matter-SemiBold',
        fontSize: 18,
        color: '#FFFFFF',
        letterSpacing: -0.3,
        marginTop: 12,
    },
    expandedDesc: {
        fontFamily: 'Matter-Regular',
        fontSize: 13,
        color: 'rgba(255,255,255,0.6)',
        textAlign: 'center',
        lineHeight: 19,
        marginTop: 10,
        maxWidth: 200,
    },
    expandedClose: {
        position: 'absolute',
        top: 14,
        right: 14,
        width: 32, height: 32,
        borderRadius: 16,
        backgroundColor: 'rgba(255,255,255,0.1)',
        alignItems: 'center', justifyContent: 'center',
    },

    /* ── Glassy stat detail overlay ── */
    detailOverlay: { zIndex: 120, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28 },
    detailScrim: { backgroundColor: 'rgba(20,18,26,0.35)' },
    detailCardWrap: { width: '100%', maxWidth: 380 },
    detailCard: {
        borderRadius: 28, overflow: 'hidden', borderWidth: 1,
        backgroundColor: '#FFFFFF',
        shadowColor: '#000', shadowOpacity: 0.22, shadowRadius: 28, shadowOffset: { width: 0, height: 16 }, elevation: 10,
    },
    detailInner: { paddingHorizontal: 24, paddingTop: 26, paddingBottom: 26 },
    detailName: { fontFamily: fonts.serif, fontSize: 27, color: BENTO_INK, letterSpacing: -0.6, marginBottom: 12 },
    detailBlurb: { fontFamily: 'Matter-Regular', fontSize: 15, lineHeight: 23, color: '#46424E' },
    detailLockRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: 18 },
    detailLockText: { fontFamily: 'Matter-Medium', fontSize: 13, letterSpacing: 0.1 },
    detailClose: {
        position: 'absolute', top: 14, right: 14,
        width: 30, height: 30, borderRadius: 15,
        backgroundColor: 'rgba(255,255,255,0.6)',
        alignItems: 'center', justifyContent: 'center',
    },
});
