import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
    View, Text, StyleSheet, ScrollView, TouchableOpacity,
    Animated, ActivityIndicator,
} from 'react-native';
import { useNavigation, useFocusEffect, CommonActions } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle } from 'react-native-svg';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { maxHomeMaxxesForUser } from '../../utils/maxxLimits';
import { colors, spacing, typography, fonts, borderRadius } from '../../theme/dark';
import { normalizeMaxxTintHex } from '../../components/MaxxProgramRow';
import { buildMaxxMaps, mergeSchedules, type MergedScheduleTask } from '../../utils/scheduleAggregation';
import { useMaxxesQuery, useActiveSchedulesFullQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { CachedImage } from '../../components/CachedImage';
import { StreakFireBadge } from '../../components/StreakFireBadge';
import { getMaxxDisplayLabel } from '../../utils/maxxDisplay';
import { AttachStep } from 'react-native-spotlight-tour';
import { TOUR_STEP } from '../../features/mainTour/mainTourSteps';

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
    return dt.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

function greetingForHour(): string {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning,';
    if (h < 17) return 'Good afternoon,';
    return 'Good evening,';
}

/* ─── Screen ─── */

export default function HomeScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const { user } = useAuth();
    const maxesQuery = useMaxxesQuery();
    const schedulesQuery = useActiveSchedulesFullQuery();

    const [completingTaskKey, setCompletingTaskKey] = useState<string | null>(null);

    const fadeAnim = useRef(new Animated.Value(0)).current;
    const slideAnim = useRef(new Animated.Value(18)).current;
    const postPayRedirected = useRef(false);

    const maxes = maxesQuery.data?.maxes ?? [];
    const loading = maxesQuery.isPending && !maxesQuery.data;
    const schedulesLoading = schedulesQuery.isPending && !schedulesQuery.data;

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
            const msg =
                (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ||
                (e as Error)?.message ||
                'Could not load today\u2019s tasks.';
            return {
                scheduleRows: [] as MergedScheduleTask[],
                scheduleStreak: { current: 0 },
                schedulesError: String(msg),
            };
        }
    }, [schedulesQuery.data, maxes]);

    const querySchedulesError =
        schedulesQuery.isError && schedulesQuery.error
            ? String((schedulesQuery.error as Error)?.message || 'Could not load today\u2019s tasks.')
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

    useEffect(() => {
        if (!(user?.onboarding as { post_subscription_onboarding?: boolean })?.post_subscription_onboarding) {
            postPayRedirected.current = false;
        }
    }, [user?.onboarding]);

    useFocusEffect(
        React.useCallback(() => {
            const ob = user?.onboarding as { post_subscription_onboarding?: boolean } | undefined;
            if (!ob?.post_subscription_onboarding || postPayRedirected.current) return;
            postPayRedirected.current = true;
            navigation.navigate('FaceScanResults', { postPay: true });
        }, [user?.onboarding, navigation]),
    );

    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
            Animated.timing(slideAnim, { toValue: 0, duration: 500, useNativeDriver: true }),
        ]).start();
    }, [fadeAnim, slideAnim]);

    const userName = user?.first_name || user?.email?.split('@')[0] || 'there';
    const maxHomeSlots = maxHomeMaxxesForUser(user);
    const rawGoalIds = (user?.onboarding?.goals || []) as string[];
    const cappedGoalIds = useMemo(() => {
        const g = (user?.onboarding?.goals || []) as string[];
        return g.slice(0, maxHomeMaxxesForUser(user));
    }, [user?.onboarding?.goals, user?.is_paid, user?.subscription_tier]);

    const activeIdSet = useMemo(() => new Set(cappedGoalIds.map((g: string) => g.toLowerCase())), [cappedGoalIds]);
    const activeMaxxes = useMemo(() => {
        const filtered = maxes.filter((m: { id?: string }) => activeIdSet.has((m.id ?? '').toLowerCase()));
        filtered.sort((a: any, b: any) =>
            getMaxxDisplayLabel(a).localeCompare(getMaxxDisplayLabel(b)),
        );
        return filtered;
    }, [maxes, activeIdSet]);

    const completedCount = scheduleRows.filter(r => r.status === 'completed').length;
    const totalCount = scheduleRows.length;

    const toggleTodayTask = async (row: MergedScheduleTask) => {
        const key = `${row.scheduleId}-${row.task_id}`;
        if (completingTaskKey) return;
        setCompletingTaskKey(key);
        const completing = row.status !== 'completed';
        const newStatus = completing ? 'completed' : 'pending';
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
        setCompletingTaskKey(null);
        try {
            if (completing) {
                await api.completeScheduleTask(row.scheduleId, row.task_id);
            } else {
                await api.uncompleteScheduleTask(row.scheduleId, row.task_id);
            }
            void queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull });
        } catch (e) {
            console.error('toggleTodayTask', e);
            queryClient.setQueryData(queryKeys.schedulesActiveFull, prevData);
        }
    };

    const greeting = greetingForHour();

    /* ───── JSX ───── */

    return (
        <View style={s.root}>
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={s.scroll}>
                <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>

                    {/* ── TOP BAR ── */}
                    <View style={[s.topBar, { paddingTop: Math.max(insets.top + 12, 52) }]}>
                        <View style={s.topLeft}>
                            <Text style={s.greeting}>{greeting}</Text>
                            <Text style={s.userName} numberOfLines={1}>{userName}</Text>
                        </View>
                        <View style={s.topRight}>
                            {scheduleStreak.current > 0 && (
                                <StreakFireBadge streakDays={scheduleStreak.current} variant="header" />
                            )}
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

                    {/* ── PROGRAMS (horizontal scroll, top of screen) ── */}
                    {activeMaxxes.length > 0 && (
                        <AttachStep index={TOUR_STEP.PROGRAMS}>
                            <View style={s.programsBar}>
                                <ScrollView
                                    horizontal
                                    showsHorizontalScrollIndicator={false}
                                    contentContainerStyle={s.programsScroll}
                                >
                                    {activeMaxxes.map((maxx: { id?: string; color?: string; icon?: string }) => {
                                        if (!maxx.id) return null;
                                        const tint = normalizeMaxxTintHex(maxx.color);
                                        return (
                                            <TouchableOpacity
                                                key={maxx.id}
                                                style={s.programPill}
                                                onPress={() => navigation.navigate('MaxxDetail', { maxxId: maxx.id })}
                                                activeOpacity={0.72}
                                            >
                                                <View style={[s.programDot, { backgroundColor: tint }]} />
                                                <Text style={s.programName} numberOfLines={1}>
                                                    {getMaxxDisplayLabel(maxx)}
                                                </Text>
                                            </TouchableOpacity>
                                        );
                                    })}
                                    <TouchableOpacity
                                        style={s.addPill}
                                        onPress={() => navigation.navigate('EditPersonal', { onlyGoals: true })}
                                        activeOpacity={0.65}
                                        hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                                    >
                                        <Ionicons name="add" size={16} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </ScrollView>
                            </View>
                        </AttachStep>
                    )}

                    {/* ── PROGRESS HERO ── */}
                    <AttachStep index={TOUR_STEP.PROGRESS} fill>
                        <TouchableOpacity
                            style={s.progressHero}
                            onPress={() => navigation.navigate('MasterScheduleTab')}
                            activeOpacity={0.8}
                            accessibilityRole="button"
                            accessibilityLabel={`${completedCount} of ${totalCount} tasks completed. Open schedule.`}
                        >
                            {schedulesLoading ? (
                                <ActivityIndicator size="large" color={colors.textMuted} style={{ height: RING_SIZE }} />
                            ) : (
                                <ProgressRing done={completedCount} total={totalCount} />
                            )}
                            <View style={s.progressMeta}>
                                <Text style={s.dateLabel}>{todayDisplayLabel}</Text>
                                {scheduleStreak.current > 0 && (
                                    <View style={s.streakRow}>
                                        <View style={s.streakDot} />
                                        <Text style={s.streakText}>
                                            {scheduleStreak.current} day{scheduleStreak.current === 1 ? '' : 's'} streak
                                        </Text>
                                    </View>
                                )}
                            </View>
                        </TouchableOpacity>
                    </AttachStep>

                    {/* ── TASKS ── */}
                    <View style={s.section}>
                        <View style={s.sectionHead}>
                            <Text style={s.sectionLabel}>Today's tasks</Text>
                            {scheduleRows.length > 0 && (
                                <Text style={s.sectionCount}>
                                    {completedCount}/{totalCount}
                                </Text>
                            )}
                        </View>

                        {displaySchedulesError ? (
                            <Text style={s.errorText}>{displaySchedulesError}</Text>
                        ) : null}

                        {!schedulesLoading && !displaySchedulesError && scheduleRows.length === 0 ? (
                            <View style={s.emptyTasks}>
                                <Text style={s.emptyText}>No tasks for today.</Text>
                                <Text style={s.emptyHint}>Start a program to see your daily schedule here.</Text>
                            </View>
                        ) : null}

                        {scheduleRows.map((row, idx) => {
                            const done = row.status === 'completed';
                            const rowKey = `${row.scheduleId}-${row.task_id}`;
                            const busy = completingTaskKey === rowKey;
                            return (
                                <View key={rowKey}>
                                    {idx > 0 && <View style={s.hairline} />}
                                    <View style={[s.taskRow, done && s.taskRowDone]}>
                                        <TouchableOpacity
                                            style={s.checkHit}
                                            onPress={() => toggleTodayTask(row)}
                                            disabled={busy}
                                            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                                            accessibilityRole="checkbox"
                                            accessibilityState={{ checked: done, disabled: busy }}
                                        >
                                            {busy ? (
                                                <ActivityIndicator size="small" color={colors.textMuted} />
                                            ) : done ? (
                                                <View style={[s.checkCircle, s.checkDone]}>
                                                    <Ionicons name="checkmark" size={11} color={colors.buttonText} />
                                                </View>
                                            ) : (
                                                <View style={s.checkCircle} />
                                            )}
                                        </TouchableOpacity>
                                        <TouchableOpacity
                                            style={s.taskTap}
                                            onPress={() => navigation.navigate('Schedule', { scheduleId: row.scheduleId })}
                                            activeOpacity={0.75}
                                        >
                                            <View style={[s.taskAccent, { backgroundColor: row.moduleColor }]} />
                                            <View style={s.taskBody}>
                                                <Text style={[s.taskTime, done && s.taskMuted]}>{formatTimeTo12Hour(row.time)}</Text>
                                                <Text style={[s.taskTitle, done && s.taskTitleDone]} numberOfLines={1}>{row.title}</Text>
                                            </View>
                                        </TouchableOpacity>
                                    </View>
                                </View>
                            );
                        })}

                        {!schedulesLoading && !displaySchedulesError && scheduleRows.length > 0 && (
                            <TouchableOpacity
                                onPress={() => navigation.navigate('MasterScheduleTab')}
                                style={s.scheduleBtn}
                                activeOpacity={0.7}
                            >
                                <Text style={s.scheduleBtnText}>View full schedule</Text>
                                <Ionicons name="arrow-forward" size={12} color={colors.textMuted} />
                            </TouchableOpacity>
                        )}
                    </View>

                    {/* ── EMPTY: no programs yet ── */}
                    {activeMaxxes.length === 0 && !schedulesLoading && (
                        <TouchableOpacity
                            style={s.emptyPrograms}
                            onPress={() => navigation.navigate('EditPersonal', { onlyGoals: true })}
                            activeOpacity={0.72}
                        >
                            <Ionicons name="sparkles-outline" size={20} color={colors.textMuted} />
                            <Text style={s.emptyProgramText}>Select goals to start your first program</Text>
                        </TouchableOpacity>
                    )}

                </Animated.View>
            </ScrollView>
        </View>
    );
}

/* ─────────────────────── STYLES ─────────────────────── */

const PAD = 24;

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    scroll: { paddingBottom: spacing.xxxl + 40 },

    /* Top bar */
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: PAD,
        paddingBottom: 16,
    },
    topLeft: { flex: 1, minWidth: 0 },
    greeting: {
        fontSize: 13,
        fontFamily: fonts.sans,
        color: colors.textMuted,
        letterSpacing: 0.2,
        marginBottom: 2,
    },
    userName: {
        fontFamily: fonts.serif,
        fontSize: 28,
        fontWeight: '400',
        lineHeight: 34,
        letterSpacing: -0.6,
        color: colors.foreground,
    },
    topRight: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    avatarHit: { padding: 2 },
    avatar: {
        width: 38,
        height: 38,
        borderRadius: 19,
        backgroundColor: colors.foreground,
        alignItems: 'center',
        justifyContent: 'center',
    },
    avatarImg: { width: 38, height: 38, borderRadius: 19 },
    avatarInitial: { fontSize: 15, fontWeight: '600', color: colors.buttonText },

    /* Progress hero */
    progressHero: {
        alignItems: 'center',
        paddingVertical: 28,
        marginHorizontal: PAD,
        borderTopWidth: 1,
        borderBottomWidth: 1,
        borderColor: colors.border,
    },
    progressMeta: {
        alignItems: 'center',
        marginTop: 14,
        gap: 6,
    },
    dateLabel: {
        fontSize: 13,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.textSecondary,
        letterSpacing: 0.3,
    },
    streakRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
    },
    streakDot: {
        width: 6,
        height: 6,
        borderRadius: 3,
        backgroundColor: colors.foreground,
    },
    streakText: {
        fontSize: 12,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.foreground,
        letterSpacing: 0.4,
    },

    /* Section */
    section: {
        paddingHorizontal: PAD,
        paddingTop: 24,
    },
    sectionHead: {
        flexDirection: 'row',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        marginBottom: 12,
    },
    sectionLabel: {
        fontSize: 11,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.textMuted,
        letterSpacing: 2,
        textTransform: 'uppercase',
    },
    sectionCount: {
        fontSize: 12,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.textMuted,
        letterSpacing: 0.3,
    },

    /* Tasks */
    hairline: {
        height: StyleSheet.hairlineWidth,
        backgroundColor: colors.borderLight,
    },
    taskRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        paddingVertical: 14,
    },
    taskRowDone: { opacity: 0.45 },
    checkHit: {
        width: 28,
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
    },
    checkCircle: {
        width: 20,
        height: 20,
        borderRadius: 10,
        borderWidth: 1.5,
        borderColor: colors.border,
        backgroundColor: 'transparent',
    },
    checkDone: {
        backgroundColor: colors.foreground,
        borderColor: colors.foreground,
        alignItems: 'center',
        justifyContent: 'center',
    },
    taskTap: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        minWidth: 0,
    },
    taskAccent: {
        width: 2,
        alignSelf: 'stretch',
        minHeight: 36,
        borderRadius: 1,
        flexShrink: 0,
    },
    taskBody: { flex: 1, minWidth: 0 },
    taskTime: {
        fontSize: 11,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.textMuted,
        letterSpacing: 0.6,
        marginBottom: 2,
    },
    taskTitle: {
        fontSize: 15,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.foreground,
        letterSpacing: -0.2,
    },
    taskTitleDone: {
        textDecorationLine: 'line-through',
        color: colors.textMuted,
    },
    taskMuted: { color: colors.textMuted },
    errorText: { ...typography.bodySmall, color: colors.error, marginBottom: spacing.sm },
    emptyTasks: {
        paddingVertical: 24,
        alignItems: 'center',
    },
    emptyText: {
        fontSize: 14,
        fontFamily: fonts.sans,
        color: colors.textMuted,
        marginBottom: 4,
    },
    emptyHint: {
        fontSize: 12,
        fontFamily: fonts.sans,
        color: colors.textMuted,
        textAlign: 'center',
        lineHeight: 18,
        maxWidth: 240,
    },

    scheduleBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        height: 40,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.full,
        backgroundColor: 'transparent',
        marginTop: 16,
        gap: 8,
    },
    scheduleBtnText: {
        fontSize: 11,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.foreground,
        letterSpacing: 1.2,
        textTransform: 'uppercase',
    },

    /* Programs bar (top, below greeting) */
    programsBar: {
        paddingBottom: 4,
    },
    programsScroll: {
        gap: 8,
        paddingHorizontal: PAD,
    },
    programPill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 7,
        paddingHorizontal: 14,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.full,
        backgroundColor: colors.card,
    },
    programDot: {
        width: 7,
        height: 7,
        borderRadius: 4,
    },
    programName: {
        fontSize: 12,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.foreground,
        letterSpacing: -0.1,
        maxWidth: 120,
    },
    addPill: {
        paddingVertical: 6,
        paddingHorizontal: 4,
        alignItems: 'center',
        justifyContent: 'center',
        alignSelf: 'center',
    },
    emptyPrograms: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        paddingVertical: 20,
        paddingHorizontal: PAD,
    },
    emptyProgramText: {
        fontSize: 13,
        fontFamily: fonts.sans,
        color: colors.textMuted,
        letterSpacing: 0.2,
    },
});
