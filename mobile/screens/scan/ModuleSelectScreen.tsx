import React, { useCallback, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { CommonActions, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function ModuleSelectScreen() {
    const navigation = useNavigation<any>();
    const { refreshUser } = useAuth();
    const [maxes, setMaxes] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [finishing, setFinishing] = useState(false);

    const load = useCallback(async () => {
        try {
            const res = await api.getMaxxes();
            setMaxes(res.maxes || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        load();
    }, [load]);

    const finish = async () => {
        try {
            setFinishing(true);
            await api.dismissPostSubscriptionOnboarding();
            await refreshUser();
        } catch (e) {
            console.error(e);
        } finally {
            setFinishing(false);
            navigation.dispatch(
                CommonActions.reset({
                    index: 0,
                    routes: [{ name: 'Main' }],
                }),
            );
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

                <Text style={styles.lead}>Pick a Maxx track to start. You can open others anytime from Home.</Text>

                {maxes.map((m) => (
                    <TouchableOpacity
                        key={m.id}
                        style={styles.card}
                        activeOpacity={0.85}
                        onPress={() => navigation.navigate('MaxxDetail', { maxxId: m.id })}
                    >
                        <View style={[styles.dot, m.color ? { backgroundColor: m.color } : { backgroundColor: colors.foreground }]} />
                        <View style={styles.cardText}>
                            <Text style={styles.cardTitle}>{m.label || m.id}</Text>
                            {m.description ? (
                                <Text style={styles.cardDesc} numberOfLines={2}>
                                    {m.description}
                                </Text>
                            ) : null}
                        </View>
                        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                    </TouchableOpacity>
                ))}

                <TouchableOpacity style={styles.cta} onPress={finish} disabled={finishing} activeOpacity={0.88}>
                    {finishing ? (
                        <ActivityIndicator color={colors.background} />
                    ) : (
                        <>
                            <Text style={styles.ctaText}>Enter Max</Text>
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
    scroll: { padding: spacing.lg, paddingTop: 56, paddingBottom: 40 },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.md },
    iconHit: { width: 40, height: 40, justifyContent: 'center' },
    title: { ...typography.h2 },
    lead: { fontSize: 15, color: colors.textSecondary, lineHeight: 22, marginBottom: spacing.xl },
    card: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        backgroundColor: colors.surface,
        borderRadius: borderRadius.xl,
        padding: spacing.md,
        marginBottom: spacing.sm,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
    },
    dot: { width: 10, height: 10, borderRadius: 5 },
    cardText: { flex: 1 },
    cardTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground },
    cardDesc: { fontSize: 13, color: colors.textSecondary, marginTop: 4, lineHeight: 18 },
    cta: {
        marginTop: spacing.xl,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: 16,
        borderRadius: borderRadius.full,
        ...shadows.md,
    },
    ctaText: { ...typography.button, color: colors.background, fontSize: 16 },
});
