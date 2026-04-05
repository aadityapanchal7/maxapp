import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Alert, Platform } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { useMaxxQuery, useMaxxScheduleQuery, useActiveSchedulesSummaryQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { getMaxxDisplayDescription, getMaxxDisplayLabel } from '../../utils/maxxDisplay';
import { useAuth } from '../../context/AuthContext';
import { defaultFitmaxMacroSummary, deriveCalorieLogFromMessages, fitmaxAccent } from '../../features/fitmax/fitmax';
import { buildModuleReaderContent, modulePreviewFromContent, isFitmaxCourseShape } from '../../utils/maxxModuleReader';

const SCHEDULE_CAPABLE_MAXXES = ['skinmax', 'heightmax', 'hairmax', 'fitmax', 'bonemax'];

const MODULE_PHASE_ACCENTS: Record<string, string> = {
    Foundation: '#0ea5e9',
    Execution: '#22c55e',
    Optimization: '#f59e0b',
    'Identity & Mastery': '#a855f7',
};

/**
 * Modules at the tail end of each maxx are premium-only.
 * Backend can override via `mod.access_tier === 'premium'` or `mod.is_premium` / `mod.isPremium`.
 */
const PREMIUM_MODULE_TITLES: Record<string, Set<string>> = {
    skinmax: new Set(['Aging / Skin Quality', 'Redness / Sensitivity']),
    hairmax: new Set(['Minoxidil Protocol', 'Dermastamp / Dermaroller']),
    heightmax: new Set(['Hormones to Max', 'Height Fuel', 'Look Taller Instantly']),
    bonemax: new Set([]),
    fitmax: new Set(),
};

function isModulePremium(maxxId: string, mod: any): boolean {
    if (mod.access_tier === 'premium' || mod.is_premium || mod.isPremium) return true;
    const titleSet = PREMIUM_MODULE_TITLES[maxxId];
    if (titleSet?.has(mod.title)) return true;
    return false;
}

function fitmaxStatusLabel(status: string | undefined): string {
    if (status === 'complete') return 'Complete';
    if (status === 'in_progress') return 'In Progress';
    if (status === 'available') return 'Available';
    if (status === 'locked') return 'Locked';
    return '';
}

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

function getModuleStatusLine(maxxId: string, moduleTitle: string, activeSchedule: any | null): string {
    if (!activeSchedule) return 'Not started';

    const ctx = activeSchedule.schedule_context || {};
    const dateStr = formatStartedDate(activeSchedule.created_at);

    if (maxxId === 'fitmax') {
        return dateStr ? `Started ${dateStr}` : 'Started';
    }

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


export default function MaxxDetailScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const queryClient = useQueryClient();
    const { isPremium } = useAuth() as any;
    const { maxxId } = route.params || {};

    const isFitmax = maxxId === 'fitmax';

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

    const [loadingFitmaxExtras, setLoadingFitmaxExtras] = useState(isFitmax);
    const [macroSnapshot, setMacroSnapshot] = useState({
        caloriesTarget: defaultFitmaxMacroSummary().calories,
        caloriesConsumed: 0,
        proteinTarget: defaultFitmaxMacroSummary().protein,
        proteinConsumed: 0,
        carbsTarget: defaultFitmaxMacroSummary().carbs,
        carbsConsumed: 0,
        fatTarget: defaultFitmaxMacroSummary().fat,
        fatConsumed: 0,
    });

    useEffect(() => {
        if (!isFitmax) return;
        let mounted = true;
        const load = async () => {
            try {
                const [scheduleRes, chatRes] = await Promise.all([api.getMaxxSchedule('fitmax'), api.getChatHistory()]);
                const context = scheduleRes?.schedule?.schedule_context || {};
                const targetCalories = Number(
                    context.calories ?? context.calorie_target ?? context.target_calories ?? defaultFitmaxMacroSummary().calories,
                );
                const targetProtein = Number(context.protein_g ?? context.protein ?? defaultFitmaxMacroSummary().protein);
                const targetCarbs = Number(context.carbs_g ?? context.carbs ?? defaultFitmaxMacroSummary().carbs);
                const targetFat = Number(context.fat_g ?? context.fat ?? defaultFitmaxMacroSummary().fat);
                const derived = deriveCalorieLogFromMessages(chatRes?.messages || []);
                if (mounted) {
                    setMacroSnapshot({
                        caloriesTarget: Number.isFinite(targetCalories) ? targetCalories : defaultFitmaxMacroSummary().calories,
                        caloriesConsumed: derived.consumedCalories,
                        proteinTarget: Number.isFinite(targetProtein) ? targetProtein : defaultFitmaxMacroSummary().protein,
                        proteinConsumed: derived.protein,
                        carbsTarget: Number.isFinite(targetCarbs) ? targetCarbs : defaultFitmaxMacroSummary().carbs,
                        carbsConsumed: derived.carbs,
                        fatTarget: Number.isFinite(targetFat) ? targetFat : defaultFitmaxMacroSummary().fat,
                        fatConsumed: derived.fat,
                    });
                }
            } catch (e) {
                console.warn('Fitmax macro snapshot failed', e);
            } finally {
                if (mounted) setLoadingFitmaxExtras(false);
            }
        };
        void load();
        return () => {
            mounted = false;
        };
    }, [isFitmax]);

    // Rely on React Query's staleTime for refresh. Focus-refetch caused 3 simultaneous
    // API calls every time the user tabbed back, which was a major perf hit.

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
                ],
            );
        }
    };

    const remainingCalories = Math.max(0, macroSnapshot.caloriesTarget - macroSnapshot.caloriesConsumed);
    const proteinLeft = Math.max(0, macroSnapshot.proteinTarget - macroSnapshot.proteinConsumed);
    const carbsLeft = Math.max(0, macroSnapshot.carbsTarget - macroSnapshot.carbsConsumed);
    const fatLeft = Math.max(0, macroSnapshot.fatTarget - macroSnapshot.fatConsumed);

    const modules = useMemo(() => (maxx?.modules || []) as any[], [maxx]);

    const openModuleReader = useCallback(
        (mod: any, idx: number) => {
            const body = buildModuleReaderContent(mod);
            const fitShape = isFitmaxCourseShape(mod);
            const screenTitle = fitShape && typeof mod.id === 'number' ? `Module ${mod.id} - ${mod.title}` : mod.title || `Module ${idx + 1}`;
            navigation.navigate('FitmaxModule', { title: screenTitle, content: body });
        },
        [navigation],
    );

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

    const tagLabels = getMaxxTagLabels(maxx);
    const MAX_PILLS = 8;
    const previewPills = tagLabels.slice(0, MAX_PILLS);
    const morePillCount = tagLabels.length - previewPills.length;

    const headerColor = maxx.color || colors.foreground;
    const fitmaxHeaderBg = '#16a34a14';
    const fitmaxIconBg = '#16a34a1f';

    return (
        <View style={styles.container}>
            {isFitmax ? (
                <View style={[styles.headerWrapFitmax, { backgroundColor: fitmaxHeaderBg }]}>
                    <TouchableOpacity
                        onPress={() => navigation.goBack()}
                        style={styles.backButton}
                        hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    >
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <View style={[styles.headerIcon, { backgroundColor: fitmaxIconBg }]}>
                        <Ionicons name="barbell-outline" size={28} color={fitmaxAccent} />
                    </View>
                    <View style={styles.macroChip}>
                        <Text style={styles.macroChipTitle}>Today</Text>
                        <Text style={styles.macroChipCalories}>{remainingCalories} cal left</Text>
                        <Text style={styles.macroChipMacros}>
                            P {proteinLeft}g · C {carbsLeft}g · F {fatLeft}g
                        </Text>
                    </View>
                    <Text style={styles.headerTitleFitmax}>{getMaxxDisplayLabel(maxx)}</Text>
                </View>
            ) : (
                <View style={[styles.headerBanner, maxx.color && { backgroundColor: maxx.color + '18' }]}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <View style={[styles.headerIcon, maxx.color && { backgroundColor: maxx.color + '30' }]}>
                        <Ionicons name={(maxx.icon || 'book-outline') as any} size={28} color={headerColor} />
                    </View>
                    <Text style={styles.headerTitle}>{getMaxxDisplayLabel(maxx)}</Text>
                </View>
            )}

            <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
                <Text style={styles.description}>{getMaxxDisplayDescription(maxx) ?? maxx.description}</Text>

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
                                    navigation.navigate('Main', {
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
                        {isFitmax && loadingFitmaxExtras ? (
                            <View style={styles.scheduleLoadingRow}>
                                <ActivityIndicator size="small" color={colors.textMuted} />
                                <Text style={styles.scheduleLoadingText}>Syncing macros…</Text>
                            </View>
                        ) : null}
                        {activeSchedule && (
                            <>
                                <TouchableOpacity
                                    style={styles.viewScheduleButton}
                                    activeOpacity={0.7}
                                    onPress={() => navigation.navigate('Schedule', { scheduleId: activeSchedule.id })}
                                >
                                    <Ionicons name="eye-outline" size={20} color={colors.foreground} />
                                    <Text style={styles.viewScheduleText}>View Schedule</Text>
                                </TouchableOpacity>
                                <TouchableOpacity style={styles.stopButton} activeOpacity={0.7} onPress={handleStopSchedule}>
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
                        {morePillCount > 0 ? <Text style={styles.pillMoreText}>+{morePillCount} more…</Text> : null}
                    </View>
                )}

                {modules.map((mod: any, idx: number) => {
                    const premium = isModulePremium(maxxId, mod);
                    const lockedPremium = premium && !isPremium;
                    const fitShape = isFitmaxCourseShape(mod);
                    const phaseAccent = fitShape
                        ? MODULE_PHASE_ACCENTS[mod.phase as string] || fitmaxAccent
                        : headerColor;
                    const statusLine = getModuleStatusLine(maxxId, mod.title, activeSchedule);
                    const readerBody = buildModuleReaderContent(mod);
                    const preview = modulePreviewFromContent(readerBody);
                    const fitStatus = fitmaxStatusLabel(mod.status);

                    return (
                        <TouchableOpacity
                            key={mod.id != null ? String(mod.id) : `${mod.title}-${idx}`}
                            style={[
                                styles.moduleCardRich,
                                mod.status === 'locked' && fitShape && !premium && styles.moduleCardLocked,
                                premium && styles.moduleCardPremium,
                                lockedPremium && styles.moduleCardPremiumLocked,
                            ]}
                            activeOpacity={0.85}
                            onPress={() => {
                                if (lockedPremium) {
                                    navigation.navigate('Payment');
                                    return;
                                }
                                openModuleReader(mod, idx);
                            }}
                        >
                            <View style={styles.moduleHeaderRow}>
                                <View style={[styles.phaseDot, { backgroundColor: premium ? colors.premium : phaseAccent }]} />
                                <Text style={styles.moduleNumberLabel}>
                                    {fitShape && typeof mod.id === 'number' ? `Module ${mod.id}` : `Part ${idx + 1}`}
                                </Text>
                                {premium ? (
                                    <View style={styles.premiumBadge}>
                                        <Ionicons name={lockedPremium ? 'lock-closed' : 'star'} size={10} color="#fff" />
                                        <Text style={styles.premiumBadgeText}>PREMIUM</Text>
                                    </View>
                                ) : fitShape && fitStatus ? (
                                    <Text style={[styles.moduleStatusChip, mod.status === 'complete' && styles.moduleStatusComplete]}>
                                        {fitStatus}
                                    </Text>
                                ) : (
                                    <Text style={styles.moduleStatusChipMuted} numberOfLines={1}>
                                        {statusLine}
                                    </Text>
                                )}
                            </View>
                            <Text style={[styles.moduleTitleRich, lockedPremium && styles.moduleTitleLocked]}>{mod.title}</Text>
                            <Text style={styles.moduleMetaRich}>
                                {fitShape
                                    ? `${mod.phase} · ${mod.duration} · ${mod.level}`
                                    : mod.description
                                      ? String(mod.description).slice(0, 120) + (String(mod.description).length > 120 ? '…' : '')
                                      : Array.isArray(mod.steps)
                                        ? `${mod.steps.length} sections`
                                        : 'Open to read'}
                            </Text>
                            <Text style={styles.modulePreviewRich} numberOfLines={lockedPremium ? 2 : undefined}>
                                {preview}
                            </Text>
                            {lockedPremium ? (
                                <Text style={styles.moduleScheduleHint}>Upgrade to unlock</Text>
                            ) : !fitShape ? (
                                <Text style={styles.moduleScheduleHint}>{statusLine}</Text>
                            ) : null}
                        </TouchableOpacity>
                    );
                })}
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
    headerWrapFitmax: {
        paddingTop: 56,
        paddingBottom: spacing.lg,
        paddingHorizontal: spacing.lg,
        borderBottomLeftRadius: 24,
        borderBottomRightRadius: 24,
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
    headerTitleFitmax: {
        fontSize: 28,
        fontWeight: '700',
        color: colors.foreground,
        letterSpacing: -0.5,
        paddingRight: 160,
    },
    macroChip: {
        position: 'absolute',
        right: spacing.lg,
        top: 64,
        backgroundColor: colors.card,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        paddingHorizontal: 10,
        paddingVertical: 8,
        ...shadows.sm,
    },
    macroChipTitle: { ...typography.caption, color: colors.textMuted },
    macroChipCalories: { fontSize: 12, fontWeight: '700', color: colors.foreground, marginTop: 2 },
    macroChipMacros: { fontSize: 11, color: colors.textSecondary, marginTop: 2 },
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
    moduleCardRich: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.lg,
        marginBottom: spacing.md,
        ...shadows.md,
    },
    moduleCardLocked: { opacity: 0.72 },
    moduleCardPremium: {
        borderWidth: 1,
        borderColor: colors.premiumBorder,
        backgroundColor: colors.premiumLight,
    },
    moduleCardPremiumLocked: { opacity: 0.8 },
    moduleHeaderRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.sm },
    phaseDot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
    moduleNumberLabel: { ...typography.caption, flex: 1 },
    moduleStatusChip: { fontSize: 11, fontWeight: '700', color: fitmaxAccent },
    moduleStatusChipMuted: { fontSize: 11, fontWeight: '600', color: colors.textMuted, maxWidth: '42%', textAlign: 'right' },
    moduleStatusComplete: { color: colors.success },
    moduleTitleRich: { fontSize: 17, lineHeight: 24, fontWeight: '700', color: colors.foreground },
    moduleTitleLocked: { color: colors.textMuted },
    moduleMetaRich: { ...typography.caption, marginTop: 6 },
    modulePreviewRich: { ...typography.bodySmall, marginTop: spacing.sm, lineHeight: 20 },
    moduleScheduleHint: { ...typography.caption, marginTop: 8, color: colors.textMuted },
    premiumBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 3,
        backgroundColor: colors.premium,
        borderRadius: 6,
        paddingHorizontal: 6,
        paddingVertical: 2,
    },
    premiumBadgeText: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
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
    scheduleLoadingRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    scheduleLoadingText: { ...typography.bodySmall },
});
