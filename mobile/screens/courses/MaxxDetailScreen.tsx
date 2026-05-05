import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Alert, Platform } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { useMaxxQuery, useMaxxScheduleQuery, useActiveSchedulesSummaryQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { getMaxxDisplayDescription, getMaxxDisplayLabel } from '../../utils/maxxDisplay';
import { useAuth } from '../../context/AuthContext';
import { defaultFitmaxMacroSummary, deriveCalorieLogFromMessages } from '../../features/fitmax/fitmax';
import { buildModuleReaderContent, modulePreviewFromContent, isFitmaxCourseShape } from '../../utils/maxxModuleReader';
import CourseTOC from '../../components/CourseTOC';
import CourseReader from '../../components/CourseReader';
import { getCourseForMaxx } from '../../data/courseContent';
import ModuleHero from '../../components/ModuleHero';
import SectionLabel from '../../components/SectionLabel';

const SCHEDULE_CAPABLE_MAXXES = ['skinmax', 'heightmax', 'hairmax', 'fitmax', 'bonemax'];

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
    const maxActiveModules = isPremium ? 3 : 1;
    const atLimit = !activeSchedule && activeCount >= maxActiveModules;

    /* Course reader (full-screen modal pager). null = closed. */
    const [readerOpenSection, setReaderOpenSection] = useState<string | null>(null);
    const openReaderAt = useCallback((sectionId: string) => setReaderOpenSection(sectionId), []);
    const closeReader = useCallback(() => setReaderOpenSection(null), []);

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

    const courseDef = getCourseForMaxx(maxxId);
    const useAccentTheme = !!courseDef; // currently only skinmax has a course → accent treatment
    const accent = courseDef?.accent ?? colors.foreground;
    const accentSoft = courseDef?.accentSoft ?? colors.surface;

    return (
        <View style={styles.container}>
            {useAccentTheme ? (
                <ModuleHero
                    title={getMaxxDisplayLabel(maxx)}
                    accent={accent}
                    accentSoft={accentSoft}
                    iconName={maxx.icon || 'sparkles-outline'}
                    description={getMaxxDisplayDescription(maxx) ?? maxx.description}
                    onBack={() => navigation.goBack()}
                    stats={
                        courseDef
                            ? [
                                  { number: courseDef.chapters.length, label: 'chapters' },
                                  {
                                      number: courseDef.chapters.reduce(
                                          (n, c) => n + c.sections.length,
                                          0
                                      ),
                                      label: 'lessons',
                                  },
                              ]
                            : undefined
                    }
                />
            ) : isFitmax ? (
                <View style={styles.headerWrapFitmax}>
                    <TouchableOpacity
                        onPress={() => navigation.goBack()}
                        style={styles.backButton}
                        hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    >
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <View style={[styles.headerIcon, styles.headerIconElevated, styles.headerIconNeutral]}>
                        <Ionicons name="barbell-outline" size={28} color={colors.foreground} />
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
                <View style={styles.headerBanner}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <View style={[styles.headerIcon, styles.headerIconElevated, styles.headerIconNeutral]}>
                        <Ionicons name={(maxx.icon || 'book-outline') as any} size={28} color={colors.foreground} />
                    </View>
                    <Text style={styles.headerTitle}>{getMaxxDisplayLabel(maxx)}</Text>
                </View>
            )}

            <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
                {!useAccentTheme && (
                    <Text style={styles.description}>{getMaxxDisplayDescription(maxx) ?? maxx.description}</Text>
                )}

                {canSchedule && useAccentTheme && (
                    <View style={styles.actionGroup}>
                        {atLimit ? (
                            <View style={styles.limitBanner}>
                                <Ionicons name="alert-circle-outline" size={16} color={colors.textSecondary} />
                                <Text style={styles.limitBannerText}>
                                    You have {maxActiveModules} active modules ({activeLabels.join(', ')}). Stop one to start this.
                                </Text>
                            </View>
                        ) : (
                            // Ghost button — hairline border, no fill,
                            // accent text + arrow. Sits quietly under the
                            // hero gradient without competing.
                            <TouchableOpacity
                                style={[styles.ghostBtn, { borderColor: accent }]}
                                activeOpacity={0.7}
                                onPress={() => {
                                    navigation.navigate('Main', {
                                        screen: 'Chat',
                                        params: { initSchedule: maxxId },
                                    });
                                }}
                            >
                                <Text style={[styles.ghostBtnText, { color: accent }]}>
                                    {activeSchedule ? 'Update schedule' : 'Start schedule'}
                                </Text>
                                <Ionicons name="arrow-forward" size={15} color={accent} />
                            </TouchableOpacity>
                        )}
                        {activeSchedule && (
                            <View style={styles.linkRow}>
                                <TouchableOpacity
                                    activeOpacity={0.6}
                                    onPress={() => navigation.navigate('Schedule', { scheduleId: activeSchedule.id })}
                                >
                                    <Text style={[styles.linkText, { color: accent }]}>View schedule</Text>
                                </TouchableOpacity>
                                <View style={styles.linkSep} />
                                <TouchableOpacity activeOpacity={0.6} onPress={handleStopSchedule}>
                                    <Text style={styles.linkTextMuted}>Stop schedule</Text>
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>
                )}

                {canSchedule && !useAccentTheme && (
                    <View style={styles.scheduleActions}>
                        {atLimit ? (
                            <View style={styles.limitBanner}>
                                <Ionicons name="alert-circle-outline" size={18} color={colors.textSecondary} />
                                <Text style={styles.limitBannerText}>
                                    You have {maxActiveModules} active modules ({activeLabels.join(', ')}). Stop one to start this.
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
                                    <Ionicons name="stop-circle-outline" size={20} color={colors.textSecondary} />
                                    <Text style={styles.stopButtonText}>Stop Schedule</Text>
                                </TouchableOpacity>
                            </>
                        )}
                    </View>
                )}

                {courseDef ? (
                    isPremium ? (
                        <CourseTOC course={courseDef} onOpenSection={openReaderAt} />
                    ) : (
                        <CourseLockedCard
                            accent={accent}
                            onUpgrade={() => navigation.navigate('Payment')}
                        />
                    )
                ) : null}

                {/* Legacy MODULES list — only render for maxxes that
                    don't yet have a curated `courseDef`. Once a course is
                    authored (skinmax today; rest soon), the TOC + Reader
                    fully replace this section. */}
                {!courseDef && (useAccentTheme ? (
                    <SectionLabel label="Modules" accent={accent} />
                ) : (
                    <Text style={styles.sectionLabel}>MODULES</Text>
                ))}

                {!courseDef && modules.length === 0 && previewPills.length > 0 && (
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

                {!courseDef && modules.map((mod: any, idx: number) => {
                    const premium = isModulePremium(maxxId, mod);
                    const lockedPremium = premium && !isPremium;
                    const fitShape = isFitmaxCourseShape(mod);
                    const phaseAccent = premium ? colors.foreground : colors.textMuted;
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
                                <View style={styles.moduleHeaderLeft}>
                                    <View style={[styles.phaseDot, { backgroundColor: phaseAccent }]} />
                                    <Text style={styles.moduleNumberLabel} numberOfLines={1}>
                                        {fitShape && typeof mod.id === 'number' ? `Module ${mod.id}` : `Part ${idx + 1}`}
                                    </Text>
                                </View>
                                <View style={styles.moduleHeaderRight}>
                                    {premium ? (
                                        <View style={styles.premiumBadge}>
                                            <Ionicons name={lockedPremium ? 'lock-closed' : 'star'} size={10} color={colors.buttonText} />
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
                                    <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                                </View>
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
                            <View style={styles.modulePreviewWrap}>
                                <Text style={styles.modulePreviewRich} numberOfLines={lockedPremium ? 2 : 3}>
                                    {preview}
                                </Text>
                            </View>
                            {lockedPremium ? (
                                <Text style={styles.moduleScheduleHint}>Upgrade to unlock</Text>
                            ) : !fitShape ? (
                                <Text style={styles.moduleScheduleHint}>{statusLine}</Text>
                            ) : null}
                        </TouchableOpacity>
                    );
                })}
            </ScrollView>

            {/* Full-screen reader. One slide per section across the entire
                course; swipe / arrow controls flow across chapter boundaries.
                Mounted at root so it overlays everything in the screen. */}
            {courseDef ? (
                <CourseReader
                    visible={readerOpenSection !== null}
                    course={courseDef}
                    initialSectionId={readerOpenSection}
                    onClose={closeReader}
                />
            ) : null}
        </View>
    );
}

/* ── Locked-course card for Chadlite users ──────────────────────────── */

function CourseLockedCard({
    accent, onUpgrade,
}: {
    accent: string;
    onUpgrade: () => void;
}) {
    return (
        <View style={styles.lockedCard}>
            <View style={[styles.lockedIcon, { backgroundColor: `${accent}1F` }]}>
                <Ionicons name="lock-closed-outline" size={20} color={accent} />
            </View>
            <Text style={styles.lockedTitle}>Course library is Chad-only</Text>
            <Text style={styles.lockedSubtitle}>
                Chadlite gives you the chatbot, 1 active program, and weekly
                face scans. Upgrade to Chad to unlock all chapters across every
                module + daily face scans.
            </Text>
            <TouchableOpacity
                style={[styles.lockedCta, { backgroundColor: accent }]}
                onPress={onUpgrade}
                activeOpacity={0.85}
            >
                <Text style={styles.lockedCtaText}>Upgrade to Chad</Text>
                <Ionicons name="arrow-forward" size={15} color={colors.buttonText} />
            </TouchableOpacity>
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
        position: 'relative',
        overflow: 'hidden',
        paddingTop: 56,
        paddingBottom: spacing.xl,
        paddingHorizontal: spacing.lg,
        backgroundColor: colors.surface,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
    },
    headerWrapFitmax: {
        position: 'relative',
        overflow: 'hidden',
        paddingTop: 56,
        paddingBottom: spacing.lg,
        paddingHorizontal: spacing.lg,
        backgroundColor: colors.surface,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
    },
    backButton: { marginBottom: spacing.md, zIndex: 1 },
    headerIcon: {
        width: 56,
        height: 56,
        borderRadius: 28,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: spacing.sm,
        zIndex: 1,
    },
    headerIconElevated: {
        borderWidth: 1,
    },
    headerIconNeutral: {
        backgroundColor: colors.card,
        borderColor: colors.border,
    },
    headerTitle: { ...typography.h1, fontSize: 28, lineHeight: 34, letterSpacing: -0.4, zIndex: 1 },
    headerTitleFitmax: {
        ...typography.h1,
        fontSize: 28,
        lineHeight: 34,
        letterSpacing: -0.4,
        paddingRight: 160,
        zIndex: 1,
    },
    macroChip: {
        position: 'absolute',
        right: spacing.lg,
        top: 64,
        zIndex: 2,
        backgroundColor: colors.card,
        borderRadius: borderRadius.sm,
        borderWidth: 1,
        borderColor: colors.border,
        paddingHorizontal: 12,
        paddingVertical: 10,
    },
    macroChipTitle: { ...typography.caption, color: colors.textMuted },
    macroChipCalories: { fontSize: 12, fontWeight: '700', color: colors.foreground, marginTop: 2 },
    macroChipMacros: { fontSize: 11, color: colors.textSecondary, marginTop: 2 },
    scroll: { flex: 1 },
    scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxxl },
    description: { fontSize: 15, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
    sectionLabel: { ...typography.label, marginBottom: spacing.md },

    /* Locked course (Chadlite) */
    lockedCard: {
        marginTop: spacing.md,
        marginBottom: spacing.xl,
        padding: spacing.xl,
        borderRadius: borderRadius.xl,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        backgroundColor: colors.card,
        alignItems: 'flex-start',
    },
    lockedIcon: {
        width: 44,
        height: 44,
        borderRadius: 22,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: spacing.md,
    },
    lockedTitle: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        letterSpacing: -0.4,
        color: colors.foreground,
        marginBottom: 6,
    },
    lockedSubtitle: {
        ...typography.bodySmall,
        color: colors.textSecondary,
        lineHeight: 19,
        marginBottom: spacing.lg,
    },
    lockedCta: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        paddingHorizontal: 22,
        paddingVertical: 11,
        borderRadius: borderRadius.full,
        alignSelf: 'flex-start',
    },
    lockedCtaText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.3,
        color: colors.buttonText,
    },
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
        position: 'relative',
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        paddingHorizontal: spacing.lg + 2,
        paddingVertical: spacing.lg,
        marginBottom: spacing.lg,
        borderWidth: 1,
        borderColor: colors.border,
        overflow: 'hidden',
    },
    moduleCardLocked: { opacity: 0.72 },
    moduleCardPremium: {
        borderWidth: 1,
        borderColor: colors.foreground,
        backgroundColor: colors.card,
    },
    moduleCardPremiumLocked: { opacity: 0.8 },
    moduleHeaderRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 10,
        marginBottom: 12,
        zIndex: 1,
    },
    moduleHeaderLeft: { flexDirection: 'row', alignItems: 'center', flex: 1, minWidth: 0, gap: 8 },
    moduleHeaderRight: { flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 0 },
    phaseDot: { width: 8, height: 8, borderRadius: 4 },
    moduleNumberLabel: { ...typography.caption, flex: 1, textTransform: 'uppercase', letterSpacing: 0.45, color: colors.textMuted },
    moduleStatusChip: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textSecondary,
        textTransform: 'uppercase',
        letterSpacing: 0.35,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.sm,
        paddingHorizontal: 8,
        paddingVertical: 4,
    },
    moduleStatusChipMuted: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textMuted,
        maxWidth: '45%',
        textAlign: 'right',
        textTransform: 'uppercase',
        letterSpacing: 0.35,
    },
    moduleStatusComplete: { color: colors.foreground },
    moduleTitleRich: { ...typography.h3, fontSize: 17, lineHeight: 24, zIndex: 1 },
    moduleTitleLocked: { color: colors.textMuted },
    moduleMetaRich: { ...typography.caption, marginTop: 4, color: colors.textSecondary, zIndex: 1 },
    modulePreviewWrap: {
        marginTop: spacing.md,
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        paddingHorizontal: spacing.md + 2,
        paddingVertical: 12,
        zIndex: 1,
    },
    modulePreviewRich: { ...typography.bodySmall, color: colors.textSecondary, lineHeight: 19 },
    moduleScheduleHint: { ...typography.caption, marginTop: 10, color: colors.textMuted, zIndex: 1 },
    premiumBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 3,
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.sm,
        paddingHorizontal: 8,
        paddingVertical: 4,
    },
    premiumBadgeText: { color: colors.buttonText, fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
    scheduleActions: {
        marginBottom: spacing.xl,
        gap: spacing.md,
    },
    scheduleActionsGlass: {
        marginTop: spacing.lg,
        marginBottom: spacing.xl,
    },
    /* ── Editorial schedule actions (accent path) ─────────────────── */
    actionGroup: {
        marginTop: spacing.xs,
        marginBottom: spacing.lg,
        gap: 14,
    },
    /* Ghost button — hairline accent border, no fill, accent text + arrow. */
    ghostBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 18,
        paddingVertical: 12,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        gap: 10,
    },
    ghostBtnText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.4,
    },

    /* Legacy primaryPill styles kept for non-accent path (currently unused). */
    primaryPill: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: 22,
        paddingVertical: 14,
        borderRadius: borderRadius.full,
    },
    primaryPillText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.4,
        color: colors.buttonText,
    },
    linkRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 4,
    },
    linkText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 12.5,
        letterSpacing: 0.3,
    },
    linkTextMuted: {
        fontFamily: fonts.sansMedium,
        fontSize: 12.5,
        letterSpacing: 0.3,
        color: colors.textMuted,
    },
    linkSep: {
        width: 3,
        height: 3,
        borderRadius: 2,
        backgroundColor: colors.textMuted,
        marginHorizontal: 12,
        opacity: 0.6,
    },

    /* ── Legacy schedule buttons (non-accent path) ────────────────── */
    scheduleButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.foreground,
        paddingVertical: 11,
        borderRadius: borderRadius.md,
    },
    scheduleButtonText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.buttonText,
    },
    viewScheduleButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.card,
        paddingVertical: 11,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    viewScheduleText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
    },
    stopButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        paddingVertical: 11,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
    },
    stopButtonText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.textSecondary,
    },
    limitBanner: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        paddingVertical: 12,
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
