import React, { useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Alert, Platform } from 'react-native';
import { useNavigation, useRoute, useFocusEffect } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { useMaxxQuery, useMaxxScheduleQuery, useActiveSchedulesSummaryQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import FitmaxScreen from './FitmaxScreen';

const SCHEDULE_CAPABLE_MAXXES = ['skinmax', 'heightmax', 'hairmax', 'fitmax', 'bonemax'];

/** Same as HomeScreen: module titles if present, else concern labels (e.g. skinmax concerns). */
function getMaxxTagLabels(maxx: any): string[] {
    const modules = maxx.modules || [];
    if (modules.length > 0) {
        return modules.map((m: any) => m.title).filter(Boolean);
    }
    const concerns = maxx.concerns || [];
    return concerns.map((c: any) => c.label || c.id).filter(Boolean);
}

/** Heightmax module title → HEIGHTMAX_PROTOCOLS key (must match backend). */
const HEIGHT_TITLE_TO_KEY: Record<string, string> = {
    Posturemaxxing: 'posturemaxxing',
    Sprintmaxxing: 'sprintmaxxing',
    'Deep Sleep Routine': 'deep_sleep_routine',
    'Decompress / Lengthen': 'decompress_lengthen',
    'Height Killers': 'height_killers',
    'Look Taller Instantly': 'look_taller_instantly',
    'Height Fuel': 'height_fuel',
    'Hormones to Max': 'hormones_to_max',
};

function formatStartedDate(iso: string | undefined): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Per-module line: "Not started" or "Started Mon Jan 1, 2026" using active schedule + context.
 */
function getModuleStatusLine(
    maxxId: string,
    moduleTitle: string,
    activeSchedule: any | null,
): string {
    if (!activeSchedule) return 'Not started';

    const ctx = activeSchedule.schedule_context || {};
    const dateStr = formatStartedDate(activeSchedule.created_at);

    if (maxxId === 'heightmax') {
        const key = HEIGHT_TITLE_TO_KEY[moduleTitle];
        if (!key) return 'Not started';
        return dateStr ? `Started ${dateStr}` : 'Started';
    }

    if (maxxId === 'skinmax') {
        const concern = (ctx.selected_concern || ctx.skin_concern) as string | undefined;
        const titleToConcern: Record<string, string> = {
            'Acne / Congestion': 'acne',
            'Pigmentation / Uneven Tone': 'pigmentation',
            'Texture / Scarring': 'texture',
            'Redness / Sensitivity': 'redness',
            'Aging / Skin Quality': 'aging',
        };
        const mod = titleToConcern[moduleTitle];
        if (!concern) return dateStr ? `Started ${dateStr}` : 'Started';
        if (mod && mod === concern) return dateStr ? `Started ${dateStr}` : 'Started';
        return 'Not started';
    }

    if (maxxId === 'hairmax') {
        const concern = ctx.selected_concern as string | undefined;
        const byConcern: Record<string, string[]> = {
            wash_routine: ['Shampoo & Conditioner Basics', 'When to Wash'],
            anti_dandruff: ['Shampoo & Conditioner Basics', 'When to Wash'],
            oils_masks: ['Oils & Hair Masks'],
            minoxidil: ['Minoxidil Protocol'],
            dermastamp: ['Dermastamp / Dermaroller'],
        };
        const titles = concern ? byConcern[concern] : undefined;
        if (!concern) return dateStr ? `Started ${dateStr}` : 'Started';
        if (titles?.includes(moduleTitle)) return dateStr ? `Started ${dateStr}` : 'Started';
        return 'Not started';
    }

    if (maxxId === 'bonemax') {
        return dateStr ? `Started ${dateStr}` : 'Started';
    }

    return 'Not started';
}

const STALE_FOCUS_MS = 25_000;

export default function MaxxDetailScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const queryClient = useQueryClient();
    const { maxxId } = route.params || {};

    const canSchedule = SCHEDULE_CAPABLE_MAXXES.includes(maxxId);

    const maxxQuery = useMaxxQuery(maxxId);
    const scheduleQuery = useMaxxScheduleQuery(maxxId, canSchedule);
    const activeSummaryQuery = useActiveSchedulesSummaryQuery(canSchedule);

    const maxx = maxxQuery.data ?? null;
    const activeSchedule = scheduleQuery.data ?? null;
    const activeCount = activeSummaryQuery.data?.count ?? 0;
    const activeLabels = activeSummaryQuery.data?.labels ?? [];

    const loading = !!maxxId && maxxQuery.isPending && !maxxQuery.data;
    const atLimit = !activeSchedule && activeCount >= 2;

    /** Refetch schedule/summary only when cache is stale — avoids hammering the API on every tab switch. */
    useFocusEffect(
        useCallback(() => {
            if (!maxxId) return;
            const now = Date.now();
            if (now - maxxQuery.dataUpdatedAt > STALE_FOCUS_MS) void maxxQuery.refetch();
            if (canSchedule) {
                if (now - scheduleQuery.dataUpdatedAt > STALE_FOCUS_MS) void scheduleQuery.refetch();
                if (now - activeSummaryQuery.dataUpdatedAt > STALE_FOCUS_MS) void activeSummaryQuery.refetch();
            }
        }, [
            maxxId,
            canSchedule,
            maxxQuery.dataUpdatedAt,
            maxxQuery.refetch,
            scheduleQuery.dataUpdatedAt,
            scheduleQuery.refetch,
            activeSummaryQuery.dataUpdatedAt,
            activeSummaryQuery.refetch,
        ]),
    );

    const refetchMaxx = useCallback(() => void maxxQuery.refetch(), [maxxQuery]);

    const doStopSchedule = async () => {
        if (!activeSchedule) return;
        try {
            await api.stopSchedule(activeSchedule.id);
            await queryClient.invalidateQueries({ queryKey: queryKeys.maxxSchedule(maxxId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.activeSchedulesSummary });
            await queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull });
        } catch (e) {
            if (Platform.OS === 'web') {
                window.alert('Could not stop schedule. Try again.');
            } else {
                Alert.alert('Error', 'Could not stop schedule. Try again.');
            }
        }
    };

    const handleStopSchedule = () => {
        if (!activeSchedule) return;
        if (Platform.OS === 'web') {
            const ok = window.confirm(`Stop your ${maxxId} schedule? You can restart it anytime.`);
            if (ok) doStopSchedule();
        } else {
            Alert.alert(
                'Stop schedule?',
                `This will deactivate your ${maxxId} schedule. You can restart it anytime.`,
                [
                    { text: 'Cancel', style: 'cancel' },
                    { text: 'Stop', style: 'destructive', onPress: () => doStopSchedule() },
                ]
            );
        }
    };

    if (loading) {
        return (
            <View style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color={colors.foreground} />
            </View>
        );
    }

    if (!maxx && maxxQuery.isError) {
        return (
            <View style={[styles.container, styles.center]}>
                <Text style={styles.errorText}>Failed to load maxx</Text>
                <TouchableOpacity onPress={refetchMaxx} style={styles.retryButton}>
                    <Text style={styles.retryText}>Retry</Text>
                </TouchableOpacity>
            </View>
        );
    }

    if (!maxx) {
        return (
            <View style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color={colors.foreground} />
            </View>
        );
    }

    if (maxxId === 'fitmax') {
        return <FitmaxScreen />;
    }

    const modules = maxx.modules || [];
    const tagLabels = getMaxxTagLabels(maxx);
    const MAX_PILLS = 8;
    const previewPills = tagLabels.slice(0, MAX_PILLS);
    const morePillCount = tagLabels.length - previewPills.length;

    return (
        <View style={styles.container}>
            <View style={[styles.headerBanner, maxx.color && { backgroundColor: maxx.color + '18' }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                    <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                </TouchableOpacity>
                <View style={[styles.headerIcon, maxx.color && { backgroundColor: maxx.color + '30' }]}>
                    <Ionicons name={(maxx.icon || 'book-outline') as any} size={28} color={maxx.color || colors.foreground} />
                </View>
                <Text style={styles.headerTitle}>{maxx.label}</Text>
            </View>

            <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
                <Text style={styles.description}>{maxx.description}</Text>

                {canSchedule && (
                    <View style={styles.scheduleActions}>
                        {atLimit ? (
                            <View style={styles.limitBanner}>
                                <Ionicons name="alert-circle-outline" size={18} color={colors.warning || '#f59e0b'} />
                                <Text style={styles.limitBannerText}>
                                    You have 2 active modules ({activeLabels.join(', ')}). Stop one to start this.
                                </Text>
                            </View>
                        ) : (
                            <TouchableOpacity
                                style={styles.scheduleButton}
                                activeOpacity={0.7}
                                onPress={() => {
                                    (navigation as any).navigate('Main', {
                                        screen: 'Chat',
                                        params: { initSchedule: maxxId },
                                    });
                                }}
                            >
                                <Ionicons name="calendar-outline" size={20} color={colors.buttonText} />
                                <Text style={styles.scheduleButtonText}>
                                    {activeSchedule ? 'Update Schedule' : 'Start Schedule'}
                                </Text>
                            </TouchableOpacity>
                        )}
                        {activeSchedule && (
                            <>
                                <TouchableOpacity
                                    style={styles.viewScheduleButton}
                                    activeOpacity={0.7}
                                    onPress={() => (navigation as any).navigate('Schedule', { scheduleId: activeSchedule.id })}
                                >
                                    <Ionicons name="eye-outline" size={20} color={colors.foreground} />
                                    <Text style={styles.viewScheduleText}>View Schedule</Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                    style={styles.stopButton}
                                    activeOpacity={0.7}
                                    onPress={handleStopSchedule}
                                >
                                    <Ionicons name="stop-circle-outline" size={20} color="#ef4444" />
                                    <Text style={styles.stopButtonText}>Stop Schedule</Text>
                                </TouchableOpacity>
                            </>
                        )}
                    </View>
                )}

                <Text style={styles.sectionLabel}>MODULES</Text>

                {modules.length === 0 && previewPills.length > 0 && (
                    <View style={styles.pillWrap}>
                        {previewPills.map((label, i) => (
                            <View key={`pill-${maxx.id}-${i}`} style={styles.pillSmall}>
                                <Text style={styles.pillSmallText} numberOfLines={2}>
                                    {label}
                                </Text>
                            </View>
                        ))}
                        {morePillCount > 0 && (
                            <Text style={styles.pillMoreText}>+{morePillCount} more…</Text>
                        )}
                    </View>
                )}

                {modules.map((mod: any, idx: number) => (
                    <View key={idx} style={styles.moduleCard}>
                        <View style={styles.moduleRow}>
                            <Text style={styles.moduleTitle}>{mod.title}</Text>
                            <Text style={styles.moduleStatus}>
                                {getModuleStatusLine(maxxId, mod.title, activeSchedule)}
                            </Text>
                        </View>
                    </View>
                ))}
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    center: { justifyContent: 'center', alignItems: 'center' },
    errorText: { color: colors.textSecondary, marginBottom: 12 },
    retryButton: { paddingHorizontal: 20, paddingVertical: 10, backgroundColor: colors.surface, borderRadius: borderRadius.md },
    retryText: { color: colors.foreground, fontWeight: '600' },
    headerBanner: {
        paddingTop: 56,
        paddingBottom: spacing.xl,
        paddingHorizontal: spacing.lg,
    },
    backButton: { marginBottom: spacing.md },
    headerIcon: {
        width: 56,
        height: 56,
        borderRadius: 28,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: spacing.sm,
    },
    headerTitle: { fontSize: 28, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
    scroll: { flex: 1 },
    scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxxl },
    description: { fontSize: 15, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
    sectionLabel: { ...typography.label, marginBottom: spacing.md },
    pillWrap: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 6,
        marginBottom: spacing.lg,
    },
    pillSmall: {
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 999,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.borderLight,
        maxWidth: 200,
    },
    pillSmallText: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textSecondary,
        lineHeight: 13,
    },
    pillMoreText: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textMuted,
    },
    moduleCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        marginBottom: spacing.md,
        overflow: 'hidden',
        ...shadows.md,
    },
    moduleRow: {
        padding: spacing.lg,
        gap: 6,
    },
    moduleTitle: { fontSize: 17, fontWeight: '600', color: colors.foreground },
    moduleStatus: { fontSize: 14, color: colors.textMuted, lineHeight: 20 },
    scheduleActions: {
        marginBottom: spacing.xl,
        gap: spacing.md,
    },
    scheduleButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        borderRadius: borderRadius.xl,
        ...shadows.md,
    },
    scheduleButtonText: {
        fontSize: 16,
        fontWeight: '600',
        color: colors.buttonText,
    },
    viewScheduleButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.card,
        paddingVertical: 14,
        borderRadius: borderRadius.xl,
        borderWidth: 1,
        borderColor: colors.border,
    },
    viewScheduleText: {
        fontSize: 16,
        fontWeight: '600',
        color: colors.foreground,
    },
    stopButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        paddingVertical: 14,
        borderRadius: borderRadius.xl,
        borderWidth: 1,
        borderColor: '#ef444440',
        backgroundColor: '#ef444410',
    },
    stopButtonText: {
        fontSize: 16,
        fontWeight: '600',
        color: '#ef4444',
    },
    limitBanner: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        backgroundColor: '#f59e0b15',
        borderRadius: borderRadius.xl,
        borderWidth: 1,
        borderColor: '#f59e0b40',
        paddingVertical: 14,
        paddingHorizontal: spacing.lg,
    },
    limitBannerText: {
        flex: 1,
        fontSize: 14,
        color: colors.textSecondary,
        lineHeight: 20,
    },
});
