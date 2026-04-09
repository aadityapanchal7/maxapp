import React, { useCallback, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator, Alert } from 'react-native';
import { CommonActions, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useMaxxesQuery } from '../../hooks/useAppQueries';
import { maxHomeMaxxesForUser } from '../../utils/maxxLimits';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';
import { resolveMaxxBrand, MAXX_ICON_FALLBACK } from '../../utils/maxxBrand';
import { getMaxxDisplayDescription, getMaxxDisplayLabel } from '../../utils/maxxDisplay';
import { MaxxProgramRow } from '../../components/MaxxProgramRow';

type MaxxCard = {
    id: string;
    label?: string;
    color?: string;
    icon?: string;
    description?: string;
};

export default function ModuleSelectScreen() {
    const navigation = useNavigation<any>();
    const { user, refreshUser } = useAuth();
    const maxxesQuery = useMaxxesQuery();
    const maxes = (maxxesQuery.data?.maxes ?? []) as MaxxCard[];
    const loading = maxxesQuery.isPending && !maxxesQuery.data;
    const [finishing, setFinishing] = useState(false);
    /** Lowercase maxx ids to show on Home (same as onboarding.goals). */
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

    const maxSlots = maxHomeMaxxesForUser(user);

    const toggleMaxx = (id: string) => {
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
                        ? 'Premium includes up to 3 programs on your home. Deselect one to add another.'
                        : 'Basic includes up to 2 programs on your home. Upgrade to Premium for 3, or deselect one to add another.',
                );
                return prev;
            }
            next.add(key);
            return next;
        });
    };

    const finish = async () => {
        if (selectedIds.size === 0) {
            Alert.alert('Choose programs', 'Select at least one Maxx to show on your home. You can change this later in your profile.');
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
                <ActivityIndicator size="large" color={colors.foreground} />
            </View>
        );
    }

    return (
        <View style={styles.root}>
            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconHit} hitSlop={12}>
                        <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.title}>Your programs</Text>
                    <View style={styles.iconHit} />
                </View>

                <Text style={styles.lead}>
                    Tap to select up to {maxSlots} program{maxSlots === 1 ? '' : 's'} for your home (
                    {maxSlots >= 3 ? 'Premium' : 'Basic'}). Starting a schedule is separate — open any track from Home when you are
                    ready.
                </Text>

                {maxes.map((m) => {
                    const idKey = String(m.id || '').toLowerCase();
                    const on = !!idKey && selectedIds.has(idKey);
                    const brand = resolveMaxxBrand(m.id, m.color);
                    const merged = { id: m.id, label: m.label, description: m.description };
                    const label = getMaxxDisplayLabel(merged);
                    const desc = getMaxxDisplayDescription(merged) ?? m.description;
                    const iconName = (m.icon || MAXX_ICON_FALLBACK[idKey] || 'book-outline') as any;
                    return (
                        <MaxxProgramRow
                            key={m.id}
                            tintHex={brand}
                            iconName={iconName}
                            title={label}
                            description={desc}
                            onPress={() => toggleMaxx(m.id)}
                            trailing={
                                <View style={[styles.checkCircle, on && styles.checkCircleOn]}>
                                    <Ionicons
                                        name={on ? 'checkmark-circle' : 'ellipse-outline'}
                                        size={22}
                                        color={on ? colors.foreground : colors.textMuted}
                                    />
                                </View>
                            }
                            selected={on}
                            selectedVariant="uniform"
                            accent="none"
                            activeOpacity={0.9}
                            accessibilityRole="checkbox"
                            accessibilityState={{ checked: on }}
                            style={styles.programRow}
                        />
                    );
                })}

                <TouchableOpacity style={styles.cta} onPress={finish} disabled={finishing} activeOpacity={0.88}>
                    {finishing ? (
                        <ActivityIndicator color={colors.background} />
                    ) : (
                        <>
                            <Text style={styles.ctaText}>Add to home & continue</Text>
                            <Ionicons name="arrow-forward" size={20} color={colors.background} />
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
    scroll: { padding: spacing.xl, paddingTop: 56, paddingBottom: spacing.xxl },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.lg },
    iconHit: { width: 40, height: 40, justifyContent: 'center' },
    title: { ...typography.h2 },
    lead: { fontSize: 15, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl + spacing.sm },
    programRow: { marginBottom: spacing.sm },
    checkCircle: {
        width: 36,
        height: 36,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.card,
    },
    checkCircleOn: {
        borderColor: colors.foreground,
        backgroundColor: colors.surface,
    },
    cta: {
        marginTop: spacing.xl + spacing.sm,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: 12,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    ctaText: { ...typography.button, color: colors.background, fontSize: 16 },
});
