import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
    View, Text, StyleSheet, ScrollView, TouchableOpacity,
    Animated, ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { useNavigation, useFocusEffect, CommonActions } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle } from 'react-native-svg';
import { LinearGradient } from 'expo-linear-gradient';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useFirstRunWalkthrough } from '../../features/mainTour/useMainAppTour';
import FirstRunWalkthrough from '../../features/mainTour/FirstRunWalkthrough';
import { colors, spacing, typography, fonts, borderRadius } from '../../theme/dark';
import { normalizeMaxxTintHex } from '../../components/MaxxProgramRow';
import { buildMaxxMaps, mergeSchedules, normalizeMaxxId, moduleColorForSchedule, type MergedScheduleTask } from '../../utils/scheduleAggregation';
import { useMaxxesQuery, useActiveSchedulesFullQuery } from '../../hooks/useAppQueries';
import { useReviewTriggers } from '../../hooks/useReviewTriggers';
import { queryKeys } from '../../lib/queryClient';
import { useFlag } from '../../constants/featureFlags';
import { usePersonalization } from '../../hooks/usePersonalization';
import { CachedImage } from '../../components/CachedImage';
import { StreakFireBadge } from '../../components/StreakFireBadge';
import InboxBell from '../../components/notifications/InboxBell';
import { getMaxxDisplayLabel } from '../../utils/maxxDisplay';

/* ─── Progress Ring ─── */

const RING_SIZE = 120;
const RING_STROKE = 6;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

function ProgressRing({ done, total }: { done: number; total: number }) {
    const pct = total > 0 ? done / total : 0;
    const offset = RING_CIRCUMFERENCE * (1 - pct);

    return (
        <View style={ring.wrap}>
            <Svg width={RING_SIZE} height={RING_SIZE}>
                <Circle
                    cx={RING_SIZE / 2}
                    cy={RING_SIZE / 2}
                    r={RING_RADIUS}
                    stroke={colors.border}
                    strokeWidth={RING_STROKE}
                    fill="none"
                />
                {total > 0 && (
                    <Circle
                        cx={RING_SIZE / 2}
                        cy={RING_SIZE / 2}
                        r={RING_RADIUS}
                        stroke={colors.foreground}
                        strokeWidth={RING_STROKE}
                        fill="none"
                        strokeDasharray={`${RING_CIRCUMFERENCE} ${RING_CIRCUMFERENCE}`}
                        strokeDashoffset={offset}
                        strokeLinecap="round"
                        rotation="-90"
                        origin={`${RING_SIZE / 2}, ${RING_SIZE / 2}`}
                    />
                )}
            </Svg>
            <View style={ring.label}>
                <Text style={ring.fraction}>
                    {done}<Text style={ring.fractionMuted}>/{total}</Text>
                </Text>
                <Text style={ring.sub}>done</Text>
            </View>
        </View>
    );
}

const ring = StyleSheet.create({
    wrap: { width: RING_SIZE, height: RING_SIZE, alignItems: 'center', justifyContent: 'center' },
    label: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
    fraction: { fontSize: 26, fontFamily: fonts.sansBold, fontWeight: '700', color: colors.foreground, letterSpacing: -1 },
    fractionMuted: { fontSize: 16, fontWeight: '400', color: colors.textMuted },
    sub: { fontSize: 10, fontFamily: fonts.sansMedium, fontWeight: '500', color: colors.textMuted, letterSpacing: 1, textTransform: 'uppercase', marginTop: 1 },
});

/* ─── Helpers ─── */

type DayCell = { date: string; index: number; total: number; done: number; isToday: boolean };

// Whole calendar days between two 'YYYY-MM-DD' dates (UTC-anchored so DST never
// shifts the count). Used to turn the journey-start anchor into a day number.
function diffDaysISO(fromISO: string, toISO: string): number {
    return Math.round(
        (Date.parse(`${toISO}T00:00:00Z`) - Date.parse(`${fromISO}T00:00:00Z`)) / 86400000,
    );
}

// Onboarding "Stoic" black-and-white palette (matches OnboardingV2Screen).
const BW = {
    bg: '#F1F1EF',
    ink: '#000000',
    onInk: '#FFFFFF',
    card: '#FFFFFF',
    sub: '#6B6B6B',
    mute: '#9A9A9A',
    hair: 'rgba(0,0,0,0.06)',
    pillOff: '#E7E7E4',
    track: '#E2E1DE',
} as const;

function formatTimeTo12Hour(time24: string) {
    if (!time24 || typeof time24 !== 'string' || !time24.includes(':')) return time24 || '';
    try {
        const [hoursStr, minutesStr] = time24.split(':');
        const hours = parseInt(hoursStr, 10);
        const minutes = parseInt(minutesStr, 10);
        if (isNaN(hours) || isNaN(minutes)) return time24;
        const period = hours >= 12 ? 'PM' : 'AM';
        const hours12 = hours % 12 || 12;
        return `${hours12}:${minutes.toString().padStart(2, '0')} ${period}`;
    } catch {
        return time24;
    }
}

function formatScheduleDayLabel(isoDate: string | undefined | null) {
    if (!isoDate || typeof isoDate !== 'string') return null;
    const parts = isoDate.split('-').map((p) => parseInt(p, 10));
    if (parts.length !== 3 || parts.some((n) => isNaN(n))) return null;
    const [y, m, d] = parts;
    const dt = new Date(y, m - 1, d);
    // Relative label for the nearby days; fall back to the full date otherwise.
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffDays = Math.round((dt.getTime() - today.getTime()) / 86_400_000);
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Tomorrow';
    if (diffDays === -1) return 'Yesterday';
    return dt.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

/* ─── Gradient habit card (per-max colour, grainy gradient fill) ─── */

function hexToRgb(hex: string): { r: number; g: number; b: number } {
    const h = (hex || '').replace('#', '');
    const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const n = parseInt(f || '6b6b6b', 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
// amt > 0 lightens toward white, amt < 0 darkens toward black.
function shade(hex: string, amt: number): string {
    const { r, g, b } = hexToRgb(hex);
    const t = amt >= 0 ? 255 : 0;
    const p = Math.abs(amt);
    return `rgb(${Math.round(r + (t - r) * p)},${Math.round(g + (t - g) * p)},${Math.round(b + (t - b) * p)})`;
}
function luminance(hex: string): number {
    const { r, g, b } = hexToRgb(hex);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}
function textOn(hex: string): string {
    return luminance(hex) > 0.62 ? '#15130F' : '#FFFFFF';
}

function GradientHabit({
    row, done, busy, onToggle, onOpen, testID,
}: {
    row: MergedScheduleTask; done: boolean; busy: boolean; onToggle: () => void; onOpen: () => void; testID?: string;
}) {
    const c = row.moduleColor && /^#/.test(row.moduleColor) ? row.moduleColor : '#8E8E93';
    // Unchecked: white card with black text. Checked: brand color gradient with
    // white text (the gradient darkens toward the base, so white reads even on
    // the lighter brand hues like amber — don't flip to dark on those).
    const txt = done ? '#FFFFFF' : '#111113';
    const subColor = done ? 'rgba(255,255,255,0.72)' : 'rgba(0,0,0,0.45)';
    return (
        <TouchableOpacity style={gh.card} activeOpacity={0.92} onPress={onOpen} testID={testID} accessibilityLabel={row.title}>
            {done ? (
                <>
                    {/* colored gradient fill — only when completed */}
                    <LinearGradient
                        colors={[shade(c, 0.3), c, shade(c, -0.14)]}
                        start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                        style={StyleSheet.absoluteFill}
                    />
                    <LinearGradient
                        pointerEvents="none"
                        colors={['rgba(255,255,255,0.22)', 'rgba(255,255,255,0)']}
                        start={{ x: 0, y: 0 }} end={{ x: 0.7, y: 0.8 }}
                        style={StyleSheet.absoluteFill}
                    />
                </>
            ) : (
                /* white background when unchecked */
                <View style={[StyleSheet.absoluteFill, { backgroundColor: '#FFFFFF' }]} />
            )}
            <View style={gh.inner}>
                <TouchableOpacity
                    style={gh.checkHit}
                    onPress={onToggle}
                    disabled={busy}
                    hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: done, disabled: busy }}
                >
                    {busy ? (
                        <ActivityIndicator size="small" color={txt} />
                    ) : done ? (
                        <View style={[gh.checkDone, { backgroundColor: 'rgba(255,255,255,0.28)' }]}>
                            <Ionicons name="checkmark" size={20} color={c} />
                        </View>
                    ) : (
                        <View style={[gh.checkOpen, { borderColor: 'rgba(0,0,0,0.18)' }]} />
                    )}
                </TouchableOpacity>
                <View style={gh.body}>
                    <Text style={[gh.title, { color: txt }]} numberOfLines={1}>{row.title}</Text>
                    <Text style={[gh.sub, { color: subColor }]} numberOfLines={1}>
                        {row.moduleLabel || formatTimeTo12Hour(row.time)}
                    </Text>
                </View>
            </View>
        </TouchableOpacity>
    );
}

const gh = StyleSheet.create({
    card: {
        minHeight: 88, borderRadius: 22, overflow: 'hidden', marginBottom: 12,
        shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 3,
    },
    inner: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 16, paddingHorizontal: 16, paddingVertical: 18 },
    checkHit: { padding: 2 },
    checkDone: { width: 48, height: 48, borderRadius: 24, backgroundColor: 'rgba(0,0,0,0.82)', alignItems: 'center', justifyContent: 'center' },
    checkOpen: { width: 48, height: 48, borderRadius: 24, borderWidth: 2 },
    body: { flex: 1, minWidth: 0 },
    title: { fontSize: 17, fontFamily: fonts.sansSemiBold, fontWeight: '600', letterSpacing: -0.3 },
    sub: { fontSize: 13.5, fontFamily: fonts.sans, marginTop: 3 },
});

/* ─── Screen ─── */

export default function HomeScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const { user, refreshUser } = useAuth();
    const maxesQuery = useMaxxesQuery();
    const schedulesQuery = useActiveSchedulesFullQuery();

    const taskToggleInFlightRef = useRef(new Set<string>());

    // One-time "welcome to Chad" popup for grandfathered Chad-Lite subscribers
    // (the single-plan pivot upgraded them server-side; the migration sets
    // profile.chad_upgrade_notice, cleared by the ack call so it never re-shows).
    const chadNoticeShown = useRef(false);
    useEffect(() => {
        if (chadNoticeShown.current) return;
        if (!(user?.profile as any)?.chad_upgrade_notice) return;
        chadNoticeShown.current = true;
        Alert.alert(
            'You’ve been upgraded to Chad',
            'Everything Chad has — unlimited coaching, 3 active routines, daily scans, the full library — is now yours, at no extra cost. Thanks for being one of our loyal customers.',
            [{ text: 'Let’s go', style: 'default' }],
        );
        void api.ackChadUpgrade().catch(() => undefined);
    }, [user]);

    const fadeAnim = useRef(new Animated.Value(0)).current;
    const slideAnim = useRef(new Animated.Value(18)).current;
    const postPayRedirected = useRef(false);
    const maxes = maxesQuery.data?.maxes ?? [];
    const loading = maxesQuery.isPending && !maxesQuery.data;
    const schedulesLoading = schedulesQuery.isPending && !schedulesQuery.data;

    // Pull-to-refresh — Instagram pattern. Spinner shows ONLY during a
    // user-initiated swipe-down, not on background refetches. Refetch
    // both queries in parallel and clear the spinner when both resolve.
    const [pulling, setPulling] = useState(false);
    const onPullRefresh = React.useCallback(async () => {
        setPulling(true);
        try {
            await Promise.all([maxesQuery.refetch(), schedulesQuery.refetch()]);
        } finally {
            setPulling(false);
        }
    }, [maxesQuery, schedulesQuery]);

    const { scheduleRows, scheduleStreak, schedulesError } = useMemo(() => {
        const full = schedulesQuery.data;
        if (!full) {
            return {
                scheduleRows: [] as MergedScheduleTask[],
                scheduleStreak: { current: 0, last_perfect_date: undefined as string | null | undefined, today_date: undefined as string | undefined },
                schedulesError: null as string | null,
            };
        }
        try {
            const { labels, colors: colorMap } = buildMaxxMaps(maxes);
            const merged = mergeSchedules(full.schedules || [], labels, colorMap);
            const today =
                full.today_date ||
                full.schedule_streak?.today_date ||
                new Date().toISOString().split('T')[0];
            const streak = full.schedule_streak
                ? {
                      current: full.schedule_streak.current ?? 0,
                      last_perfect_date: full.schedule_streak.last_perfect_date,
                      today_date: full.schedule_streak.today_date,
                  }
                : { current: 0 };
            return {
                scheduleRows: merged.byDate[today] || [],
                scheduleStreak: streak,
                schedulesError: null,
            };
        } catch (e: unknown) {
            // Show the backend's user-safe `detail` if present; otherwise a
            // friendly fallback. Never surface the raw axios message
            // ("Request failed with status code 500") to the user.
            const msg =
                (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
                'Could not load today\u2019s tasks.';
            return {
                scheduleRows: [] as MergedScheduleTask[],
                scheduleStreak: { current: 0 },
                schedulesError: String(msg),
            };
        }
    }, [schedulesQuery.data, maxes]);

    // Day strip + "Day X of N" \u2014 derived from the full schedule horizon. Each
    // entry is one scheduled date with its completion tally.
    const { days, todayIndex, dayCount, byDate, today } = useMemo(() => {
        const full = schedulesQuery.data;
        const fallbackToday = new Date().toISOString().split('T')[0];
        if (!full) return { days: [] as DayCell[], todayIndex: 1, dayCount: 0, byDate: {} as Record<string, MergedScheduleTask[]>, today: fallbackToday };
        try {
            const { labels, colors: colorMap } = buildMaxxMaps(maxes);
            const merged = mergeSchedules(full.schedules || [], labels, colorMap);
            const today =
                full.today_date || full.schedule_streak?.today_date || fallbackToday;
            // Stable Day-1 anchor from the backend (account/first-max date). When
            // present, day numbers are real calendar days since onboarding —
            // incrementing daily and immune to schedule regeneration. Falls back
            // to positional indexing if an older backend isn't sending it yet.
            const f = full as any;
            const journeyStart: string | null =
                f.journey_start_date || f.schedule_streak?.journey_start_date || null;
            const backendDayNumber: number | null =
                f.day_number ?? f.schedule_streak?.day_number ?? null;
            const dayNumberFor = (d: string) =>
                journeyStart ? diffDaysISO(journeyStart, d) + 1 : null;
            const dates = Object.keys(merged.byDate)
                .filter((d) => (merged.byDate[d] || []).length > 0)
                .sort();
            const cells: DayCell[] = dates.map((d, i) => {
                const rows = merged.byDate[d] || [];
                const total = rows.length;
                const done = rows.filter((r) => r.status === 'completed').length;
                return { date: d, index: dayNumberFor(d) ?? i + 1, total, done, isToday: d === today };
            });
            const tIndex =
                backendDayNumber ??
                dayNumberFor(today) ??
                (dates.filter((d) => d <= today).length || 1);
            return { days: cells, todayIndex: tIndex, dayCount: dates.length, byDate: merged.byDate, today };
        } catch {
            return { days: [] as DayCell[], todayIndex: 1, dayCount: 0, byDate: {} as Record<string, MergedScheduleTask[]>, today: fallbackToday };
        }
    }, [schedulesQuery.data, maxes]);

    // Which day's tasks the HABITS list shows. Null → today; tapping a day pill
    // selects that date. (Synthetic days on the empty strip just show no tasks.)
    const [selectedDate, setSelectedDate] = useState<string | null>(null);
    // Day strip auto-scroll: bring the current day into view on load (and again
    // when the calendar day rolls over), so a user on day 15 isn't staring at
    // day 1. Only fires once per `today` value so it never fights a manual scroll.
    const stripRef = useRef<ScrollView>(null);
    const scrolledToTodayRef = useRef<string | null>(null);
    const activeDate = selectedDate ?? today;
    const selectedRows = byDate[activeDate] || [];

    // The strip is ALWAYS shown — even with no program, so the day rhythm reads.
    // When there's no real schedule yet, synthesize a 30-day strip (today = 1).
    const stripDays: DayCell[] = days.length > 0
        ? days
        : Array.from({ length: 30 }, (_, i) => ({ date: `synthetic-${i + 1}`, index: i + 1, total: 0, done: 0, isToday: i === 0 }));

    const querySchedulesError =
        schedulesQuery.isError && schedulesQuery.error
            ? (schedulesQuery.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
              'Could not load today\u2019s tasks.'
            : null;
    const displaySchedulesError = schedulesError || querySchedulesError;

    const todayDisplayLabel = useMemo(() => {
        const full = schedulesQuery.data;
        const raw =
            full?.today_date ||
            full?.schedule_streak?.today_date ||
            new Date().toISOString().split('T')[0];
        return (
            formatScheduleDayLabel(raw) ||
            new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
        );
    }, [schedulesQuery.data]);

    // Header label + day index update when a non-today pill is tapped.
    const activeDisplayLabel = useMemo(() => {
        if (!selectedDate) return todayDisplayLabel;
        return (
            formatScheduleDayLabel(selectedDate) ||
            new Date(selectedDate + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
        );
    }, [selectedDate, todayDisplayLabel]);

    const activeDayIndex = useMemo(() => {
        if (!selectedDate) return todayIndex;
        return stripDays.find((d) => d.date === selectedDate)?.index ?? todayIndex;
    }, [selectedDate, stripDays, todayIndex]);

    // Face-scan kill switch: when off, a just-paid user is NOT redirected into
    // the scan-results flow (the scan is removed). Flip the flag to restore it.
    const faceScan = useFlag('faceScan');

    useEffect(() => {
        if (!(user?.onboarding as { post_subscription_onboarding?: boolean })?.post_subscription_onboarding) {
            postPayRedirected.current = false;
        }
    }, [user?.onboarding]);

    useFocusEffect(
        React.useCallback(() => {
            if (!faceScan) return;
            const ob = user?.onboarding as { post_subscription_onboarding?: boolean } | undefined;
            if (!ob?.post_subscription_onboarding || postPayRedirected.current) return;
            postPayRedirected.current = true;
            // The scan is OPTIONAL. A skipper has no scan row, so the reveal
            // redirect would just transit FaceScanResults' no-scan spinner (or
            // its 8s "Couldn't load your scan" watchdog screen) before bouncing
            // back here. Skip the reveal entirely: clear the server flag so the
            // first-run walkthrough can start, and never show a scan-results
            // surface to someone who chose not to scan.
            if (!user?.first_scan_completed) {
                void api.dismissPostSubscriptionOnboarding()
                    .then(() => refreshUser())
                    .catch(() => { postPayRedirected.current = false; });   // retry next focus
                return;
            }
            navigation.navigate('FaceScanResults', { postPay: true });
        }, [user?.onboarding, user?.first_scan_completed, navigation, faceScan, refreshUser]),
    );

    // First-run walkthrough (replaced the spotlight tour): shows only when Home
    // is focused and no post-pay redirect is pending. Anchor-free — see
    // features/mainTour/FirstRunWalkthrough.
    const tourRedirectPending =
        faceScan &&
        !!(user?.onboarding as { post_subscription_onboarding?: boolean } | undefined)?.post_subscription_onboarding &&
        !postPayRedirected.current;
    const walkthrough = useFirstRunWalkthrough({ redirectPending: tourRedirectPending });

    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
            Animated.timing(slideAnim, { toValue: 0, duration: 500, useNativeDriver: true }),
        ]).start();
    }, [fadeAnim, slideAnim]);

    // Today's first still-pending task — the walkthrough's "start with this"
    // action. Null while the funnel-completion pass is still building the plan.
    const walkthroughFirstRow = useMemo(
        () => (byDate[today] || []).find((r) => r.status !== 'completed') ?? null,
        [byDate, today],
    );

    // Funnel-completion settle: the server builds the first max in the
    // BACKGROUND after onboarding completes (services.funnel_completion), so a
    // brand-new user lands here seconds before their schedule exists. The
    // cached schedules query would show the empty state until a manual
    // refresh — banned. Poll the query (bounded: ~90s) while a completed user
    // with quiz picks has zero schedules; stops the moment rows land.
    const settlePollCount = useRef(0);
    useEffect(() => {
        const ob = user?.onboarding as {
            completed?: boolean;
            goals?: unknown[];
            funnel_auto_enroll_pending?: boolean;
            funnel_auto_enrolled?: string;
        } | undefined;
        const eligible =
            ob?.completed === true &&
            Array.isArray(ob?.goals) && ob.goals.length > 0 &&
            // Funnel-era users only (the completion pass stamps these) — a
            // veteran who deliberately paused every schedule must not trigger
            // 90s of background refetching on every Home visit.
            !!(ob?.funnel_auto_enroll_pending || ob?.funnel_auto_enrolled) &&
            schedulesQuery.isSuccess &&
            ((schedulesQuery.data?.schedules as unknown[] | undefined)?.length ?? 0) === 0;
        if (!eligible || settlePollCount.current >= 22) return;
        const id = setInterval(() => {
            settlePollCount.current += 1;
            if (settlePollCount.current >= 22) { clearInterval(id); return; }
            void queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull });
        }, 4000);
        return () => clearInterval(id);
    }, [user?.onboarding, schedulesQuery.isSuccess, schedulesQuery.data, queryClient]);

    const personalizedUI = useFlag('personalizedUI');
    const pers = usePersonalization();
    // The programs the user has actively STARTED and that are running right now
    // — one chip per LIVE schedule (a native maxx OR a creator course). Built
    // from the active schedules, not the onboarding goals (which surfaced
    // programs the user merely picked but never began).
    const activeMaxxes = useMemo(() => {
        const { labels, colors: colorMap } = buildMaxxMaps(maxes);
        const out: { id: string; label: string; color: string; maxxId: string; isCourse: boolean }[] = [];
        const seen = new Set<string>();
        for (const s of ((schedulesQuery.data?.schedules || []) as any[])) {
            const mid = normalizeMaxxId(s.maxx_id);
            const nativeLabel = mid ? labels[mid] : '';
            const isCourse = !nativeLabel;
            const label = String(nativeLabel || s.course_title || s.maxx_id || 'Program');
            const key = (isCourse ? (s.course_title || s.id) : mid).toString().toLowerCase();
            if (!key || seen.has(key)) continue;
            seen.add(key);
            out.push({ id: String(s.id), label, color: moduleColorForSchedule(s, colorMap), maxxId: mid, isCourse });
        }
        out.sort((a, b) => a.label.localeCompare(b.label));
        return out;
    }, [schedulesQuery.data, maxes]);

    // scheduleId -> normalized maxxId, so the task guide can pin the right
    // per-Max icon (skinmax / heightmax / ...). Built from the raw schedules
    // (not the deduped chip list) so every schedule resolves.
    const maxxIdBySchedule = useMemo(() => {
        const m: Record<string, string> = {};
        for (const s of ((schedulesQuery.data?.schedules || []) as any[])) {
            m[String(s.id)] = normalizeMaxxId(s.maxx_id);
        }
        return m;
    }, [schedulesQuery.data]);

    const completedCount = scheduleRows.filter(r => r.status === 'completed').length;
    const totalCount = scheduleRows.length;

    // Positive-moment triggers: rank level-up celebration + throttled review asks
    // (level-up / full day). Reads gamification from the schedules-full payload.
    useReviewTriggers(
        schedulesQuery.data?.gamification,
        totalCount > 0 && completedCount === totalCount,
        schedulesQuery.data?.today_date,
    );

    const toggleTodayTask = async (row: MergedScheduleTask) => {
        const key = `${row.scheduleId}:${row.task_id}`;
        if (taskToggleInFlightRef.current.has(key)) return;
        taskToggleInFlightRef.current.add(key);

        const completing = row.status !== 'completed';
        const newStatus = completing ? 'completed' : 'pending';
        // Optimistic update FIRST (synchronous) so the checkbox flips instantly —
        // never gated on the network. THEN cancel any in-flight refetch so it
        // can't clobber the optimistic state. Awaiting cancelQueries before the
        // flip (the old order) added a network-shaped delay before the check.
        const prevData = queryClient.getQueryData(queryKeys.schedulesActiveFull);
        queryClient.setQueryData(queryKeys.schedulesActiveFull, (old: any) => {
            if (!old?.schedules) return old;
            return {
                ...old,
                schedules: old.schedules.map((s: any) => s.id !== row.scheduleId ? s : {
                    ...s,
                    days: (s.days ?? []).map((d: any) => ({
                        ...d,
                        tasks: (d.tasks ?? []).map((t: any) =>
                            t.task_id === row.task_id ? { ...t, status: newStatus } : t
                        ),
                    })),
                }),
            };
        });
        void queryClient.cancelQueries({ queryKey: queryKeys.schedulesActiveFull });
        try {
            if (completing) {
                await api.completeScheduleTask(row.scheduleId, row.task_id);
                // A COMPLETE can earn a streak/achievement/celebration → re-sync.
                void queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull });
            } else {
                await api.uncompleteScheduleTask(row.scheduleId, row.task_id);
                // Un-checking can BREAK today's perfect day, which lowers the
                // streak — so re-sync here too, otherwise the fire badge would
                // stay stuck at the value it reached when the day was complete.
                void queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull });
            }
        } catch (e) {
            console.error('toggleTodayTask', e);
            queryClient.setQueryData(queryKeys.schedulesActiveFull, prevData);
        } finally {
            taskToggleInFlightRef.current.delete(key);
        }
    };

    /* ───── JSX ───── */

    return (
        <View style={s.root}>
            <ScrollView
                showsVerticalScrollIndicator={false}
                contentContainerStyle={s.scroll}
                refreshControl={
                    <RefreshControl
                        refreshing={pulling}
                        onRefresh={onPullRefresh}
                        tintColor={colors.foreground}
                    />
                }
            >
                <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>

                    {/* ── TOP BAR ── */}
                    <View style={[s.topBar, { paddingTop: Math.max(insets.top + 12, 52) }]}>
                        <View style={{ flex: 1 }} />
                        <View style={s.topRight}>
                            {scheduleStreak.current > 0 && (
                                <StreakFireBadge streakDays={scheduleStreak.current} variant="header" />
                            )}
                            <InboxBell />
                            <TouchableOpacity
                                style={s.avatarHit}
                                onPress={() => navigation.dispatch(CommonActions.navigate({ name: 'Profile' }))}
                                activeOpacity={0.7}
                                accessibilityRole="button"
                                accessibilityLabel="Open profile"
                            >
                                <View style={s.avatar}>
                                    {user?.profile?.avatar_url ? (
                                        <CachedImage
                                            uri={api.resolveAttachmentUrl(user.profile.avatar_url)}
                                            style={s.avatarImg}
                                        />
                                    ) : (
                                        <Text style={s.avatarInitial}>
                                            {(user?.first_name?.charAt(0) || user?.email?.charAt(0) || 'U').toUpperCase()}
                                        </Text>
                                    )}
                                </View>
                            </TouchableOpacity>
                        </View>
                    </View>

                    {/* ── HEADER + DAY STRIP ── */}
                    <View>
                            <View style={s.header}>
                                <Text style={s.kicker} numberOfLines={1}>
                                    {(activeDisplayLabel || 'TODAY').toUpperCase()}
                                </Text>
                                <Text style={s.dayTitle}>
                                    DAY {activeDayIndex}
                                    <Text style={s.dayTitleMuted}> / 365</Text>
                                </Text>
                            </View>
                        <ScrollView
                            ref={stripRef}
                            horizontal
                            showsHorizontalScrollIndicator={false}
                            contentContainerStyle={s.stripScroll}
                        >
                            {stripDays.map((d) => {
                                const onPill = selectedDate ? d.date === selectedDate : d.isToday;
                                const complete = d.total > 0 && d.done >= d.total;
                                const partial = d.done > 0 && d.done < d.total;
                                // A past day that had tasks but zero completed — the day
                                // elapsed unfulfilled and doesn't count toward the streak.
                                // Marked with a dashed outline so it reads as "missed",
                                // distinct from a solid-outline upcoming day.
                                const missed = d.total > 0 && d.done === 0 && !d.isToday && d.date < today;
                                // Pill background: black only when complete; colorless otherwise.
                                // Selected-but-incomplete gets a border outline instead.
                                const pillStyle = complete
                                    ? { backgroundColor: BW.ink, borderWidth: 0 }
                                    : onPill
                                        ? { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: BW.ink }
                                        : missed
                                            ? { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: BW.track, borderStyle: 'dashed' as const }
                                            : { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: BW.track };
                                const numColor = complete ? BW.onInk : onPill ? BW.ink : BW.mute;
                                const dotStyle = complete
                                    ? { backgroundColor: BW.onInk }
                                    : partial
                                        ? { backgroundColor: onPill ? BW.ink : BW.mute }
                                        : { borderWidth: 1.5, borderColor: onPill ? BW.ink : BW.track };
                                return (
                                    <TouchableOpacity
                                        key={d.date}
                                        style={[s.dayPill, pillStyle]}
                                        activeOpacity={0.85}
                                        onPress={() => setSelectedDate(d.date)}
                                        onLayout={d.isToday && days.length > 0 ? (e) => {
                                            // Scroll the current day into view once per calendar
                                            // day, leaving ~96px of prior-day context to its left.
                                            // Gated on real data (days.length > 0): the synthetic
                                            // placeholder strip that renders while schedules load
                                            // must not burn the once-per-day guard, or the real
                                            // strip never auto-scrolls.
                                            if (scrolledToTodayRef.current === today) return;
                                            scrolledToTodayRef.current = today;
                                            const x = e.nativeEvent.layout.x;
                                            stripRef.current?.scrollTo({ x: Math.max(0, x - 96), animated: false });
                                        } : undefined}
                                        accessibilityRole="button"
                                        accessibilityLabel={`Day ${d.index}`}
                                    >
                                        <Text style={[s.dayNum, { color: numColor }]}>{d.index}</Text>
                                        <View style={[s.dayDot, dotStyle]} />
                                    </TouchableOpacity>
                                );
                            })}
                        </ScrollView>
                    </View>

                    {/* ── HABITS ── */}
                    <View style={s.section}>
                            <Text style={s.sectionLabel}>HABITS</Text>

                            {displaySchedulesError ? (
                                <Text style={s.errorText}>{displaySchedulesError}</Text>
                            ) : null}

                            {schedulesLoading && scheduleRows.length === 0 ? (
                                <ActivityIndicator color={BW.mute} style={{ marginTop: 24 }} />
                            ) : null}

                            {!schedulesLoading && !displaySchedulesError && selectedRows.length === 0 ? (
                                <View style={s.emptyTasks}>
                                    <Text style={s.emptyText}>
                                        {activeDate === today
                                            ? 'No habits for today. Start a program to begin.'
                                            : 'No habits scheduled for this day.'}
                                    </Text>
                                </View>
                            ) : null}

                            {selectedRows.map((row, rowIdx) => {
                                const done = row.status === 'completed';
                                const rowKey = `${row.scheduleId}:${row.task_id}`;
                                // No spinner: the optimistic flip already shows the
                                // result instantly. Concurrent taps are guarded
                                // inside toggleTodayTask (taskToggleInFlightRef).
                                const busy = false;
                                return (
                                    <GradientHabit
                                        key={rowKey}
                                        testID={`habit-card-${rowIdx}`}
                                        row={row}
                                        done={done}
                                        busy={busy}
                                        onToggle={() => toggleTodayTask(row)}
                                        onOpen={() => navigation.navigate('TaskGuide', {
                                            scheduleId: row.scheduleId,
                                            taskId: row.task_id,
                                            maxxId: maxxIdBySchedule[row.scheduleId],
                                            moduleColor: row.moduleColor,
                                            moduleLabel: row.moduleLabel,
                                            done: done,
                                        })}
                                    />
                                );
                            })}
                        </View>

                    {/* ── EMPTY: no programs yet ── */}
                    {activeMaxxes.length === 0 && !schedulesLoading && (
                        <TouchableOpacity
                            style={s.emptyPrograms}
                            onPress={() => navigation.navigate('Explore')}
                            activeOpacity={0.72}
                        >
                            <Ionicons name="compass-outline" size={20} color={BW.mute} />
                            <Text style={s.emptyProgramText}>
                                {personalizedUI && pers.primaryGoalLabel
                                    ? `Ready to start on ${pers.primaryGoalLabel}? Explore has a plan.`
                                    : 'Browse maxes in Explore'}
                            </Text>
                        </TouchableOpacity>
                    )}

                    <Text style={s.wellnessNote}>
                        General wellness only — not medical advice. Follow routines at your own risk.
                    </Text>

                </Animated.View>
            </ScrollView>

            <FirstRunWalkthrough
                visible={walkthrough.visible}
                maxxLabel={activeMaxxes.find((m) => !m.isCourse)?.label ?? activeMaxxes[0]?.label ?? null}
                firstTask={walkthroughFirstRow
                    ? { title: walkthroughFirstRow.title, time: formatTimeTo12Hour(walkthroughFirstRow.time) }
                    : null}
                onOpenFirstTask={() => {
                    const row = walkthroughFirstRow;
                    if (!row) return;
                    navigation.navigate('TaskGuide', {
                        scheduleId: row.scheduleId,
                        taskId: row.task_id,
                        maxxId: maxxIdBySchedule[row.scheduleId],
                        moduleColor: row.moduleColor,
                        moduleLabel: row.moduleLabel,
                        done: false,
                    });
                }}
                onOpenChat={() => navigation.navigate('Chat')}
                onFinish={walkthrough.finish}
            />
        </View>
    );
}

/* ─────────────────────── STYLES ─────────────────────── */

const PAD = 24;

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BW.bg },
    scroll: { paddingBottom: spacing.xxxl + 40 },
    wellnessNote: {
        fontSize: 11,
        lineHeight: 15,
        color: BW.mute,
        textAlign: 'center',
        marginTop: 28,
        paddingHorizontal: PAD + 8,
    },

    /* Top bar */
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: PAD,
        paddingBottom: 8,
    },
    topRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    avatarHit: { padding: 2 },
    avatar: {
        width: 38, height: 38, borderRadius: 19,
        backgroundColor: BW.ink, alignItems: 'center', justifyContent: 'center',
    },
    avatarImg: { width: 38, height: 38, borderRadius: 19 },
    avatarInitial: { fontSize: 15, fontFamily: fonts.sansSemiBold, fontWeight: '600', color: BW.onInk },

    /* Header — greeting + kicker + DAY X / N */
    header: { paddingHorizontal: PAD, paddingTop: 10, paddingBottom: 18 },
    greeting: {
        fontSize: 16, fontFamily: fonts.serif, color: BW.mute,
        letterSpacing: -0.2, marginBottom: 8,
    },
    kicker: {
        fontSize: 12, fontFamily: fonts.sansSemiBold, fontWeight: '600',
        color: BW.mute, letterSpacing: 1.4, textTransform: 'uppercase', marginBottom: 6,
    },
    dayTitle: { fontSize: 44, fontFamily: fonts.sansBold, fontWeight: '800', color: BW.ink, letterSpacing: -1.5 },
    dayTitleMuted: { color: BW.mute, fontWeight: '700' },

    /* Day strip */
    stripScroll: { paddingHorizontal: PAD, gap: 10, paddingBottom: 8 },
    dayPill: {
        width: 58, height: 84, borderRadius: 16, backgroundColor: BW.pillOff,
        alignItems: 'center', justifyContent: 'center', gap: 12,
    },
    dayPillOn: { backgroundColor: BW.ink },
    dayNum: { fontSize: 17, fontFamily: fonts.sansSemiBold, fontWeight: '600', color: BW.ink },
    dayNumOn: { color: BW.onInk },
    dayDot: { width: 12, height: 12, borderRadius: 6 },

    /* Section */
    section: { paddingHorizontal: PAD, paddingTop: 26 },
    sectionLabel: {
        fontSize: 13, fontFamily: fonts.sansBold, fontWeight: '800',
        color: BW.ink, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16,
    },
    errorText: { ...typography.bodySmall, color: colors.error, marginBottom: spacing.sm },
    emptyTasks: { paddingVertical: 24, alignItems: 'center' },
    emptyText: { fontSize: 14, fontFamily: fonts.sans, color: BW.mute, marginBottom: 4 },

    /* Habit cards */
    habit: {
        flexDirection: 'row', alignItems: 'center', gap: 16,
        minHeight: 88, borderRadius: 20, paddingHorizontal: 16,
        backgroundColor: BW.card, borderWidth: StyleSheet.hairlineWidth, borderColor: BW.hair,
        marginBottom: 12,
    },
    habitDone: { backgroundColor: BW.ink, borderColor: BW.ink },
    habitCheckHit: { padding: 2 },
    habitCircle: {
        width: 52, height: 52, borderRadius: 26,
        borderWidth: 1.5, borderColor: BW.mute, backgroundColor: 'transparent',
        alignItems: 'center', justifyContent: 'center',
    },
    habitCircleDone: { backgroundColor: BW.onInk, borderColor: BW.onInk },
    habitBody: { flex: 1, minWidth: 0 },
    habitTitle: { fontSize: 17, fontFamily: fonts.sansSemiBold, fontWeight: '600', color: BW.ink, letterSpacing: -0.3 },
    habitTitleDone: { color: BW.onInk },
    habitSub: { fontSize: 14, fontFamily: fonts.sans, color: BW.mute, marginTop: 3 },
    habitSubDone: { color: 'rgba(255,255,255,0.6)' },

    /* CTA */
    cta: {
        marginHorizontal: PAD, marginTop: 22, height: 58, borderRadius: 999,
        backgroundColor: BW.ink, alignItems: 'center', justifyContent: 'center',
    },
    ctaText: { fontSize: 15, fontFamily: fonts.sansBold, fontWeight: '800', color: BW.onInk, letterSpacing: 0.6 },

    /* Empty: no programs */
    emptyPrograms: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
        paddingVertical: 20, paddingHorizontal: PAD,
    },
    emptyProgramText: { fontSize: 13, fontFamily: fonts.sans, color: BW.mute, letterSpacing: 0.2 },
});
