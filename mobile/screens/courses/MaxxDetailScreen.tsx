import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import FitmaxScreen from './FitmaxScreen';

const SCHEDULE_CAPABLE_MAXXES = ['skinmax', 'heightmax', 'hairmax', 'fitmax'];

export default function MaxxDetailScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { maxxId } = route.params || {};
    const [maxx, setMaxx] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [expandedModule, setExpandedModule] = useState<number | null>(0);
    const [activeSchedule, setActiveSchedule] = useState<any>(null);
    const [scheduleLoading, setScheduleLoading] = useState(false);

    const canSchedule = SCHEDULE_CAPABLE_MAXXES.includes(maxxId);

    useEffect(() => { loadData(); }, [maxxId]);

    const loadData = async () => {
        if (!maxxId) { setLoading(false); return; }
        try {
            const data = await api.getMaxx(maxxId);
            setMaxx(data);
            setExpandedModule(0);
            if (SCHEDULE_CAPABLE_MAXXES.includes(maxxId)) {
                const schedRes = await api.getMaxxSchedule(maxxId);
                if (schedRes?.schedule) setActiveSchedule(schedRes.schedule);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <View style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color={colors.foreground} />
            </View>
        );
    }

    if (!maxx) {
        return (
            <View style={[styles.container, styles.center]}>
                <Text style={styles.errorText}>Failed to load maxx</Text>
                <TouchableOpacity onPress={loadData} style={styles.retryButton}>
                    <Text style={styles.retryText}>Retry</Text>
                </TouchableOpacity>
            </View>
        );
    }

    if (maxxId === 'fitmax') {
        return <FitmaxScreen />;
    }

    const modules = maxx.modules || [];

    return (
        <View style={styles.container}>
            <View style={[styles.header, maxx.color && { backgroundColor: maxx.color + '18' }]}>
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
                        {activeSchedule && (
                            <TouchableOpacity
                                style={styles.viewScheduleButton}
                                activeOpacity={0.7}
                                onPress={() => (navigation as any).navigate('Schedule', { scheduleId: activeSchedule.id })}
                            >
                                <Ionicons name="eye-outline" size={20} color={colors.foreground} />
                                <Text style={styles.viewScheduleText}>View Schedule</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                )}

                <Text style={styles.sectionLabel}>MODULES</Text>

                {modules.map((mod: any, idx: number) => {
                    const isExpanded = expandedModule === idx;
                    const steps = mod.steps || [];
                    return (
                        <View key={idx} style={styles.moduleCard}>
                            <TouchableOpacity
                                style={styles.moduleHeader}
                                onPress={() => setExpandedModule(isExpanded ? null : idx)}
                                activeOpacity={0.7}
                            >
                                <View style={styles.moduleTitleRow}>
                                    <Text style={styles.moduleTitle}>{mod.title}</Text>
                                    <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={20} color={colors.textMuted} />
                                </View>
                                {mod.description ? <Text style={styles.moduleDesc} numberOfLines={2}>{mod.description}</Text> : null}
                            </TouchableOpacity>

                            {isExpanded && steps.length > 0 && (
                                <View style={styles.stepsContainer}>
                                    {steps.map((step: any, stepIdx: number) => (
                                        <View key={stepIdx} style={styles.stepBlock}>
                                            <Text style={styles.stepTitle}>{step.title}</Text>
                                            <Text style={styles.stepContent}>{step.content}</Text>
                                        </View>
                                    ))}
                                </View>
                            )}
                        </View>
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
    header: {
        paddingTop: 56,
        paddingBottom: spacing.xl,
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
    scroll: { flex: 1 },
    scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxxl },
    description: { fontSize: 15, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
    sectionLabel: { ...typography.label, marginBottom: spacing.md },
    moduleCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        marginBottom: spacing.md,
        overflow: 'hidden',
        ...shadows.md,
    },
    moduleHeader: { padding: spacing.lg },
    moduleTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    moduleTitle: { fontSize: 17, fontWeight: '600', color: colors.foreground, flex: 1 },
    moduleDesc: { fontSize: 13, color: colors.textMuted, marginTop: 4, lineHeight: 20 },
    stepsContainer: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg, borderTopWidth: 1, borderTopColor: colors.border },
    stepBlock: { paddingTop: spacing.lg },
    stepTitle: { fontSize: 15, fontWeight: '600', color: colors.foreground, marginBottom: 6 },
    stepContent: { fontSize: 14, color: colors.textSecondary, lineHeight: 22 },
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
});
