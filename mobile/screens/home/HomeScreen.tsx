import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Animated, Image, ActivityIndicator } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { buildMaxxMaps, mergeSchedules, type MergedScheduleTask } from '../../utils/scheduleAggregation';

const MAX_TAG_PILLS = 3;
const HOME_TODAY_TASK_PREVIEW = 3;

/** Module step titles first (detail cards); else concern labels (e.g. SkinMax). */
function getMaxxTagLabels(maxx: any): string[] {
    const modules = maxx.modules || [];
    if (modules.length > 0) {
        return modules.map((m: any) => m.title).filter(Boolean);
    }
    const concerns = maxx.concerns || [];
    return concerns.map((c: any) => c.label || c.id).filter(Boolean);
}

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

export default function HomeScreen() {
    const navigation = useNavigation<any>();
    const { user, refreshUser } = useAuth();
    const [maxes, setMaxes] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [scheduleRows, setScheduleRows] = useState<MergedScheduleTask[]>([]);
    const [schedulesLoading, setSchedulesLoading] = useState(true);
    const [schedulesError, setSchedulesError] = useState<string | null>(null);

    const fadeAnim = useRef(new Animated.Value(0)).current;
    const slideAnim = useRef(new Animated.Value(20)).current;
    const postPayRedirected = useRef(false);

    useEffect(() => {
        if (!(user?.onboarding as any)?.post_subscription_onboarding) {
            postPayRedirected.current = false;
        }
    }, [user?.onboarding]);

    useFocusEffect(
        React.useCallback(() => {
            const ob = user?.onboarding as { post_subscription_onboarding?: boolean } | undefined;
            if (!ob?.post_subscription_onboarding || postPayRedirected.current) return;
            postPayRedirected.current = true;
            (async () => {
                try {
                    await refreshUser();
                } catch (e) {
                    console.error(e);
                } finally {
                    navigation.navigate('FaceScanResults', { postPay: true });
                }
            })();
        }, [user?.onboarding, navigation, refreshUser]),
    );

    useFocusEffect(React.useCallback(() => { loadData(); }, []));

    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
            Animated.timing(slideAnim, { toValue: 0, duration: 500, useNativeDriver: true }),
        ]).start();
    }, []);

    const loadData = async () => {
        try {
            const res = await api.getMaxxes();
            setMaxes(res.maxes || []);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const loadTodaySchedules = async () => {
        setSchedulesError(null);
        try {
            const full = await api.getActiveSchedulesFull();
            const maxxRes = await api.getMaxxes().catch(() => ({ maxes: [] as any[] }));
            const { labels, colors: colorMap } = buildMaxxMaps(maxxRes.maxes || []);
            const merged = mergeSchedules(full.schedules || [], labels, colorMap);
            const today = new Date().toISOString().split('T')[0];
            setScheduleRows(merged.byDate[today] || []);
        } catch (e: any) {
            const msg =
                e?.response?.data?.detail || e?.message || 'Could not load today’s tasks.';
            setSchedulesError(String(msg));
            setScheduleRows([]);
        } finally {
            setSchedulesLoading(false);
        }
    };

    useFocusEffect(
        React.useCallback(() => {
            loadData();
            setSchedulesLoading(true);
            loadTodaySchedules();
        }, []),
    );

    const userName = user?.first_name || user?.email?.split('@')[0] || 'there';
    const selectedGoals: string[] = (user?.onboarding?.goals || []).map((g: string) => g.toLowerCase());

    // Filter maxes from RDS down to only the ones the user selected
    const activeMaxxes = maxes.filter(m => selectedGoals.includes(m.id?.toLowerCase()));

    return (
        <View style={styles.container}>
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
                <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>
                    <View style={styles.hero}>
                        <View style={styles.heroTop}>
                            <View>
                                <Text style={styles.greeting}>Welcome back,</Text>
                                <Text style={styles.userName}>{userName}</Text>
                            </View>
                            <TouchableOpacity style={styles.profileButton} onPress={() => navigation.navigate('Profile')} activeOpacity={0.7}>
                                <View style={styles.profileIcon}>
                                    {user?.profile?.avatar_url ? (
                                        <Image
                                            source={{ uri: api.resolveAttachmentUrl(user.profile.avatar_url) }}
                                            style={styles.profileAvatar}
                                        />
                                    ) : (
                                        <Text style={styles.profileInitial}>{(user?.first_name?.charAt(0) || user?.email?.charAt(0) || 'U').toUpperCase()}</Text>
                                    )}
                                </View>
                            </TouchableOpacity>
                        </View>
                    </View>

                    <View style={styles.todaySection}>
                        <View style={styles.todayHeader}>
                            <Text style={styles.todayLabel}>TODAY&apos;S TASKS</Text>
                            {schedulesLoading ? (
                                <ActivityIndicator size="small" color={colors.textMuted} />
                            ) : null}
                        </View>
                        {schedulesError ? (
                            <Text style={styles.todayError}>{schedulesError}</Text>
                        ) : null}
                        {!schedulesLoading && !schedulesError && scheduleRows.length === 0 ? (
                            <Text style={styles.todayEmpty}>No tasks scheduled for today across your active programs.</Text>
                        ) : null}
                        {scheduleRows.slice(0, HOME_TODAY_TASK_PREVIEW).map((row, idx) => (
                            <TouchableOpacity
                                key={`${row.scheduleId}-${row.task_id}`}
                                style={[styles.todayRow, idx > 0 && styles.todayRowBorder]}
                                onPress={() => navigation.navigate('Schedule', { scheduleId: row.scheduleId })}
                                activeOpacity={0.75}
                            >
                                <View style={[styles.todayAccent, { backgroundColor: row.moduleColor }]} />
                                <View style={styles.todayRowBody}>
                                    <Text style={styles.todayTime}>{formatTimeTo12Hour(row.time)}</Text>
                                    <Text style={styles.todayTitle} numberOfLines={1}>{row.title}</Text>
                                    <Text style={styles.todayModule} numberOfLines={1}>{row.moduleLabel}</Text>
                                </View>
                                <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                            </TouchableOpacity>
                        ))}
                        {!schedulesLoading && !schedulesError && scheduleRows.length > HOME_TODAY_TASK_PREVIEW ? (
                            <Text style={styles.todayMore}>
                                +{scheduleRows.length - HOME_TODAY_TASK_PREVIEW} more on Master schedule
                            </Text>
                        ) : null}
                    </View>

                    <View style={styles.masterScheduleWrap}>
                        <TouchableOpacity
                            style={styles.masterScheduleCard}
                            onPress={() => navigation.navigate('MasterScheduleTab')}
                            activeOpacity={0.75}
                        >
                            <View style={styles.masterScheduleIcon}>
                                <Ionicons name="calendar-outline" size={22} color={colors.foreground} />
                            </View>
                            <View style={styles.masterScheduleTextCol}>
                                <Text style={styles.masterScheduleTitle}>Master schedule</Text>
                                <Text style={styles.masterScheduleSub} numberOfLines={2}>
                                    All tasks from every active program, color-coded by module
                                </Text>
                            </View>
                            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                        </TouchableOpacity>
                    </View>

                    <View style={styles.section}>
                        <View style={styles.sectionHeader}>
                            <Text style={styles.sectionLabel}>MY ACTIVE MAXXES</Text>
                            {activeMaxxes.length > 0 && <Text style={styles.sectionCount}>{activeMaxxes.length}</Text>}
                        </View>

                        {activeMaxxes.map((maxx) => {
                            const allTags = getMaxxTagLabels(maxx);
                            const previewTags = allTags.slice(0, MAX_TAG_PILLS);
                            const moreCount = allTags.length - previewTags.length;
                            return (
                                <TouchableOpacity
                                    key={maxx.id}
                                    style={styles.courseCard}
                                    onPress={() => navigation.navigate('MaxxDetail', { maxxId: maxx.id })}
                                    activeOpacity={0.7}
                                >
                                    <View style={styles.courseRow}>
                                        <View style={[styles.courseIcon, maxx.color ? { backgroundColor: maxx.color + '22' } : {}]}>
                                            <Ionicons name={(maxx.icon || 'book-outline') as any} size={20} color={maxx.color || colors.textSecondary} />
                                        </View>
                                        <View style={styles.courseContent}>
                                            <Text style={styles.courseTitle} numberOfLines={1}>{maxx.label}</Text>
                                            <Text style={[styles.emptyDesc, { fontSize: 12, marginBottom: 6, textAlign: 'left' }]} numberOfLines={2}>{maxx.description}</Text>
                                            {previewTags.length > 0 && (
                                                <View style={styles.moduleRow}>
                                                    {previewTags.map((t, i) => (
                                                        <View key={`${maxx.id}-tag-${i}`} style={styles.modulePill}>
                                                            <Text style={styles.moduleText} numberOfLines={1}>{t}</Text>
                                                        </View>
                                                    ))}
                                                    {moreCount > 0 && (
                                                        <Text style={styles.moduleMoreHint} numberOfLines={1}>
                                                            +{moreCount} more…
                                                        </Text>
                                                    )}
                                                </View>
                                            )}
                                        </View>
                                        <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                                    </View>
                                </TouchableOpacity>
                            );
                        })}

                        {activeMaxxes.length === 0 && (
                            <TouchableOpacity style={styles.emptyCard} onPress={() => navigation.navigate('EditPersonal', { onlyGoals: true })} activeOpacity={0.7}>
                                <Text style={styles.emptyTitle}>No Maxxes active</Text>
                                <Text style={styles.emptyDesc}>Select a max goal in your profile to begin.</Text>
                                <View style={styles.emptyButton}>
                                    <Text style={styles.emptyButtonText}>Select Goals</Text>
                                </View>
                            </TouchableOpacity>
                        )}

                        {activeMaxxes.length > 0 && (
                            <TouchableOpacity style={[styles.emptyButton, { marginTop: spacing.md, alignSelf: 'center' }]} onPress={() => navigation.navigate('EditPersonal', { onlyGoals: true })} activeOpacity={0.7}>
                                <Text style={styles.emptyButtonText}>Add More Maxxes</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                </Animated.View>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    scrollContent: { paddingBottom: spacing.xxxl },
    hero: { paddingHorizontal: spacing.lg, paddingTop: 64, paddingBottom: spacing.lg },
    heroTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    greeting: { fontSize: 13, color: colors.textMuted, marginBottom: 2, letterSpacing: 0.3 },
    userName: { fontSize: 28, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
    profileButton: { padding: 2 },
    profileIcon: {
        width: 40, height: 40, borderRadius: 20,
        backgroundColor: colors.foreground, alignItems: 'center', justifyContent: 'center',
        ...shadows.sm,
    },
    profileAvatar: { width: 40, height: 40, borderRadius: 20 },
    profileInitial: { fontSize: 16, fontWeight: '600', color: colors.buttonText },
    todaySection: {
        marginHorizontal: spacing.lg,
        marginTop: spacing.md,
        marginBottom: spacing.sm,
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.md,
        ...shadows.sm,
    },
    todayHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.sm,
    },
    todayLabel: { ...typography.label, fontSize: 11 },
    todayError: { ...typography.bodySmall, color: colors.error, marginBottom: spacing.xs },
    todayEmpty: { ...typography.bodySmall, color: colors.textMuted, lineHeight: 20 },
    todayRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingVertical: spacing.sm,
    },
    todayRowBorder: {
        borderTopWidth: 1,
        borderTopColor: colors.borderLight,
    },
    todayAccent: { width: 4, height: 40, borderRadius: 2 },
    todayRowBody: { flex: 1, minWidth: 0 },
    todayTime: { fontSize: 12, fontWeight: '700', color: colors.foreground },
    todayTitle: { fontSize: 14, fontWeight: '600', color: colors.foreground, marginTop: 2 },
    todayModule: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
    todayMore: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xs, textAlign: 'center' },
    masterScheduleWrap: { paddingHorizontal: spacing.lg, marginTop: spacing.sm },
    masterScheduleCard: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.lg,
        ...shadows.sm,
    },
    masterScheduleIcon: {
        width: 44,
        height: 44,
        borderRadius: borderRadius.lg,
        backgroundColor: colors.surface,
        alignItems: 'center',
        justifyContent: 'center',
    },
    masterScheduleTextCol: { flex: 1, minWidth: 0 },
    masterScheduleTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground, marginBottom: 4 },
    masterScheduleSub: { ...typography.bodySmall, color: colors.textMuted, lineHeight: 18 },
    section: { paddingHorizontal: spacing.lg, marginTop: spacing.md },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
    sectionLabel: { ...typography.label },
    sectionCount: {
        fontSize: 11, fontWeight: '600', color: colors.textSecondary,
        backgroundColor: colors.surface,
        paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10,
    },
    courseCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        paddingVertical: spacing.xl,
        paddingHorizontal: spacing.lg,
        marginBottom: spacing.md,
        ...shadows.md,
    },
    courseRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    courseIcon: {
        width: 48, height: 48, borderRadius: borderRadius.md,
        backgroundColor: colors.surface,
        alignItems: 'center', justifyContent: 'center',
    },
    courseContent: { flex: 1 },
    courseTitle: { fontSize: 18, fontWeight: '700', color: colors.foreground, marginBottom: 8 },
    progressRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    progressBar: { flex: 1, height: 6, backgroundColor: colors.borderLight, borderRadius: 3, overflow: 'hidden' },
    progressFill: { height: '100%', backgroundColor: colors.foreground, borderRadius: 3 },
    coursePercent: { fontSize: 13, fontWeight: '500', color: colors.textMuted, width: 40, textAlign: 'right' },
    moduleRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: spacing.xs,
        marginTop: spacing.sm,
    },
    modulePill: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 999,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.borderLight,
    },
    moduleText: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textSecondary,
        maxWidth: 130,
    },
    moduleMoreHint: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textMuted,
        alignSelf: 'center',
        marginLeft: 2,
    },
    emptyCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xxl,
        alignItems: 'center',
        ...shadows.md,
    },
    emptyTitle: { fontSize: 17, fontWeight: '600', color: colors.foreground, marginBottom: spacing.xs },
    emptyDesc: { fontSize: 13, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.lg },
    emptyButton: {
        backgroundColor: colors.foreground,
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.sm + 2,
        borderRadius: borderRadius.full,
        ...shadows.sm,
    },
    emptyButtonText: { fontSize: 13, fontWeight: '600', color: colors.buttonText },
});
