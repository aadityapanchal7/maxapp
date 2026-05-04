/**
 * Pick programs for the home dashboard.
 *
 * Editorial list — same vocabulary as the Course TOC:
 *   - Tracked accent number for each row (01, 02, …)
 *   - Playfair serif title
 *   - Terse looksmaxx-coded description
 *   - Hairline divider between rows
 *   - Selected state: accent fill on the number badge + a thin accent dot
 *
 * No card chrome per row. The accent comes from the per-maxx brand color
 * via resolveMaxxBrand(). Rest of the page uses neutral type + hairlines.
 */

import React, { useCallback, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    Alert,
} from 'react-native';
import { CommonActions, useFocusEffect, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useMaxxesQuery } from '../../hooks/useAppQueries';
import { maxHomeMaxxesForUser } from '../../utils/maxxLimits';
import { borderRadius, colors, fonts, spacing, typography } from '../../theme/dark';
import { resolveMaxxBrand } from '../../utils/maxxBrand';
import { getMaxxDisplayDescription, getMaxxDisplayLabel } from '../../utils/maxxDisplay';

type MaxxCard = {
    id: string;
    label?: string;
    color?: string;
    icon?: string;
    description?: string;
};

export default function ModuleSelectScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { user, refreshUser } = useAuth();
    const maxxesQuery = useMaxxesQuery();
    const maxes = (maxxesQuery.data?.maxes ?? []) as MaxxCard[];
    const loading = (maxxesQuery.isPending || maxxesQuery.isFetching) && !maxxesQuery.data;
    const [finishing, setFinishing] = useState(false);
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

    const maxSlots = maxHomeMaxxesForUser(user);
    const needsReload = maxxesQuery.isError || (!maxxesQuery.isFetching && maxes.length === 0);

    useFocusEffect(
        useCallback(() => {
            if (!needsReload) return;
            void maxxesQuery.refetch();
        }, [needsReload, maxxesQuery]),
    );

    const toggle = (id: string) => {
        const key = String(id || '').toLowerCase();
        if (!key) return;
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (next.has(key)) {
                next.delete(key);
                return next;
            }
            if (next.size >= maxSlots) {
                Alert.alert(
                    'Program limit',
                    maxSlots >= 3
                        ? 'Premium fits 3 programs on home. Deselect one to swap.'
                        : 'Basic fits 2 programs on home. Upgrade to Premium for 3, or swap one out.',
                );
                return prev;
            }
            next.add(key);
            return next;
        });
    };

    const finish = async () => {
        if (selectedIds.size === 0) {
            Alert.alert('Pick at least one', 'Select a program to show on your home. You can change this later in profile.');
            return;
        }
        try {
            setFinishing(true);
            const onboardingData = {
                ...(user?.onboarding || {}),
                goals: Array.from(selectedIds),
                timezone:
                    user?.onboarding?.timezone ||
                    (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC'),
                completed: true,
            };
            await api.saveOnboarding(onboardingData as any);
            await api.dismissPostSubscriptionOnboarding();
            await refreshUser();
            navigation.dispatch(
                CommonActions.reset({
                    index: 0,
                    routes: [{ name: 'Main' }],
                }),
            );
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not save your programs. Try again.');
        } finally {
            setFinishing(false);
        }
    };

    if (loading) {
        return (
            <View style={[styles.root, styles.center]}>
                <ActivityIndicator size="small" color={colors.textMuted} />
            </View>
        );
    }

    if (maxxesQuery.isError || maxes.length === 0) {
        return (
            <View style={styles.root}>
                <View style={[styles.center, { flex: 1, paddingHorizontal: spacing.xl }]}>
                    <Text style={styles.emptyTitle}>Programs are loading</Text>
                    <Text style={styles.emptySubtitle}>
                        {maxxesQuery.isError
                            ? 'Could not load your programs. Pull them in again and this should populate.'
                            : 'Programs still loading after payment. Try again and they should appear.'}
                    </Text>
                    <TouchableOpacity
                        style={styles.retryBtn}
                        onPress={() => void maxxesQuery.refetch()}
                        activeOpacity={0.85}
                    >
                        {maxxesQuery.isFetching ? (
                            <ActivityIndicator size="small" color={colors.foreground} />
                        ) : (
                            <Text style={styles.retryBtnText}>Reload</Text>
                        )}
                    </TouchableOpacity>
                </View>
            </View>
        );
    }

    return (
        <View style={styles.root}>
            <ScrollView
                contentContainerStyle={[styles.scroll, { paddingTop: Math.max(insets.top, 12) + 18 }]}
                showsVerticalScrollIndicator={false}
            >
                {/* ── Hero ─────────────────────────────────────────── */}
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={styles.backBtn}
                    hitSlop={12}
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>

                <Text style={styles.title}>Programs</Text>
                <View style={styles.titleRule} />

                <Text style={styles.lead}>
                    Pick up to {maxSlots} for your home.
                </Text>

                {/* ── Editorial list ───────────────────────────────── */}
                <View style={styles.list}>
                    {maxes.map((m, i) => {
                        const idKey = String(m.id || '').toLowerCase();
                        const on = !!idKey && selectedIds.has(idKey);
                        const accent = resolveMaxxBrand(m.id, m.color);
                        const merged = { id: m.id, label: m.label, description: m.description };
                        const label = getMaxxDisplayLabel(merged);
                        const desc = getMaxxDisplayDescription(merged) ?? m.description ?? '';
                        const num = String(i + 1).padStart(2, '0');
                        return (
                            <TouchableOpacity
                                key={m.id}
                                onPress={() => toggle(m.id)}
                                activeOpacity={0.6}
                                style={[
                                    styles.row,
                                    i !== 0 && styles.rowDivider,
                                ]}
                                accessibilityRole="checkbox"
                                accessibilityState={{ checked: on }}
                            >
                                <Text style={[styles.numLabel, { color: accent }]}>{num}</Text>
                                <View style={styles.rowCopy}>
                                    <Text style={styles.rowTitle}>{label}</Text>
                                    {!!desc && (
                                        <Text style={styles.rowDesc} numberOfLines={1}>
                                            {desc}
                                        </Text>
                                    )}
                                </View>
                                <View
                                    style={[
                                        styles.dot,
                                        on
                                            ? { backgroundColor: accent, borderColor: accent }
                                            : { borderColor: colors.border },
                                    ]}
                                />
                            </TouchableOpacity>
                        );
                    })}
                </View>

                {/* ── CTA ──────────────────────────────────────────── */}
                <TouchableOpacity
                    style={[styles.cta, selectedIds.size === 0 && styles.ctaDisabled]}
                    onPress={finish}
                    disabled={finishing || selectedIds.size === 0}
                    activeOpacity={0.85}
                >
                    {finishing ? (
                        <ActivityIndicator size="small" color={colors.buttonText} />
                    ) : (
                        <>
                            <Text style={styles.ctaText}>Continue</Text>
                            <Ionicons name="arrow-forward" size={15} color={colors.buttonText} />
                        </>
                    )}
                </TouchableOpacity>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    center: { justifyContent: 'center', alignItems: 'center' },
    scroll: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.xxl,
    },

    backBtn: {
        width: 32,
        height: 32,
        alignItems: 'flex-start',
        justifyContent: 'center',
        marginLeft: -4,
        marginBottom: spacing.lg,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 36,
        fontWeight: '400',
        letterSpacing: -0.8,
        color: colors.foreground,
    },
    titleRule: {
        width: 28,
        height: 2,
        borderRadius: 1,
        backgroundColor: colors.foreground,
        marginTop: 12,
        marginBottom: spacing.md,
    },
    lead: {
        fontFamily: fonts.sans,
        fontSize: 14.5,
        lineHeight: 21,
        color: colors.textSecondary,
        marginBottom: spacing.xl,
    },

    list: {
        marginTop: spacing.sm,
    },
    row: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        paddingVertical: spacing.lg,
    },
    rowDivider: {
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.border,
    },
    numLabel: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 1.6,
        marginRight: 18,
        marginTop: 5,
        width: 26,
    },
    rowCopy: {
        flex: 1,
        paddingRight: spacing.sm,
    },
    rowTitle: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        letterSpacing: -0.4,
        lineHeight: 28,
        color: colors.foreground,
    },
    rowDesc: {
        ...typography.bodySmall,
        color: colors.textSecondary,
        marginTop: 4,
        lineHeight: 19,
    },
    dot: {
        width: 16,
        height: 16,
        borderRadius: 8,
        borderWidth: 1.5,
        marginTop: 8,
        marginLeft: spacing.sm,
    },

    cta: {
        marginTop: spacing.xl,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        borderRadius: borderRadius.full,
    },
    ctaDisabled: {
        backgroundColor: colors.border,
    },
    ctaText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.4,
        color: colors.buttonText,
    },

    /* empty / retry */
    emptyTitle: {
        fontFamily: fonts.serif,
        fontSize: 26,
        fontWeight: '400',
        letterSpacing: -0.4,
        color: colors.foreground,
        textAlign: 'center',
        marginBottom: spacing.sm,
    },
    emptySubtitle: {
        ...typography.bodySmall,
        color: colors.textSecondary,
        textAlign: 'center',
        marginBottom: spacing.lg,
        maxWidth: 320,
    },
    retryBtn: {
        paddingVertical: 10,
        paddingHorizontal: spacing.lg,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    retryBtnText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.4,
        color: colors.foreground,
    },
});
