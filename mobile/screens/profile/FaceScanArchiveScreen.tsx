import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

function formatDate(dateStr: string): string {
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return '';
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

export default function FaceScanArchiveScreen() {
    const navigation = useNavigation<any>();
    const { isPremium } = useAuth();
    const [loading, setLoading] = useState(true);
    const [scans, setScans] = useState<any[]>([]);

    useEffect(() => {
        const load = async () => {
            setLoading(true);
            try {
                const res = await api.getScanHistory().catch(() => ({ scans: [] }));
                setScans(res.scans || []);
            } finally {
                setLoading(false);
            }
        };
        void load();
    }, []);

    const startNewScan = async () => {
        try {
            if (isPremium) {
                const latest = await api.getLatestScan().catch((err: any) => {
                    if (err?.response?.status === 404) return null;
                    return null;
                });
                if (latest?.created_at) {
                    const ts = new Date(latest.created_at);
                    if (!Number.isNaN(ts.getTime())) {
                        const now = new Date();
                        const sameDay =
                            ts.getFullYear() === now.getFullYear() &&
                            ts.getMonth() === now.getMonth() &&
                            ts.getDate() === now.getDate();
                        if (sameDay) {
                            alert('You already used today’s face scan. Come back tomorrow.');
                            return;
                        }
                    }
                }
            }
            navigation.navigate('FaceScan', { source: 'archive' });
        } catch {
            navigation.navigate('FaceScan', { source: 'archive' });
        }
    };

    if (loading) {
        return (
            <View style={styles.container}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>Face scans</Text>
                    <View style={{ width: 40 }} />
                </View>
                <View style={styles.loadingContainer}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>Face scans</Text>
                <TouchableOpacity onPress={() => void startNewScan()} style={styles.backButton} activeOpacity={0.7}>
                    <Ionicons name="add" size={24} color={colors.foreground} />
                </TouchableOpacity>
            </View>

            {scans.length === 0 ? (
                <View style={styles.emptyContainer}>
                    <Ionicons name="scan-outline" size={52} color={colors.textMuted} />
                    <Text style={styles.emptyText}>No face scans yet</Text>
                    <TouchableOpacity style={styles.primaryBtn} onPress={() => void startNewScan()} activeOpacity={0.8}>
                        <Text style={styles.primaryBtnText}>Do your first scan</Text>
                    </TouchableOpacity>
                </View>
            ) : (
                <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
                    <Text style={styles.hint}>
                        {isPremium
                            ? 'Premium: 1 three-photo scan per day.'
                            : 'Basic: one face scan included (signup) — no additional scans on this plan.'}
                    </Text>
                    {scans.map((s) => (
                        <TouchableOpacity
                            key={s.id}
                            style={styles.card}
                            onPress={() => navigation.navigate('FaceScanResults', { scanId: s.id })}
                            activeOpacity={0.85}
                        >
                            <View style={styles.cardTop}>
                                <Text style={styles.cardTitle}>{formatDate(s.created_at)}</Text>
                                <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                            </View>
                            <Text style={styles.cardSub}>overall {typeof s.overall_score === 'number' ? s.overall_score.toFixed(1) : '—'}</Text>
                        </TouchableOpacity>
                    ))}
                </ScrollView>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: 56,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.borderLight,
    },
    backButton: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: colors.card,
        alignItems: 'center',
        justifyContent: 'center',
        ...shadows.sm,
    },
    headerTitle: { fontSize: 17, fontWeight: '600', color: colors.foreground },
    loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.xl },
    emptyText: { marginTop: spacing.md, color: colors.foreground, fontSize: 15, fontWeight: '700' },
    primaryBtn: {
        marginTop: spacing.lg,
        backgroundColor: colors.foreground,
        paddingHorizontal: spacing.xl,
        paddingVertical: 14,
        borderRadius: borderRadius.full,
        ...shadows.md,
    },
    primaryBtnText: { color: colors.buttonText, fontSize: 14, fontWeight: '700' },
    list: { padding: spacing.lg, paddingBottom: spacing.xxl },
    hint: { color: colors.textMuted, fontSize: 12, marginBottom: spacing.md, textAlign: 'center' },
    card: {
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.lg,
        padding: spacing.lg,
        marginBottom: spacing.md,
        ...shadows.sm,
    },
    cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    cardTitle: { color: colors.foreground, fontSize: 14, fontWeight: '900' },
    cardSub: { marginTop: 8, color: colors.textMuted, fontSize: 12, fontWeight: '700' },
});

