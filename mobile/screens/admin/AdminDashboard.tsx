import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, RefreshControl } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function AdminDashboard() {
    const [stats, setStats] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    useEffect(() => { loadStats(); }, []);

    const loadStats = async () => {
        try { const data = await api.getAdminStats(); setStats(data); }
        catch (error) { console.error(error); }
        finally { setLoading(false); setRefreshing(false); }
    };

    const onRefresh = () => {
        setRefreshing(true);
        void loadStats();
    };

    if (loading) return <View style={styles.center}><ActivityIndicator color={colors.foreground} /></View>;

    const cards = [
        { title: 'Total Users', value: stats?.total_users || 0, icon: 'people' },
        { title: 'Paid Users', value: stats?.paid_users || 0, icon: 'card' },
        { title: 'Premium (tier)', value: stats?.premium_users ?? 0, icon: 'star' },
        { title: 'Channels', value: stats?.total_channels || 0, icon: 'chatbubbles' },
        { title: 'Messages', value: stats?.total_messages || 0, icon: 'mail' },
        { title: 'Forum categories', value: stats?.forum_v2_categories ?? 0, icon: 'folder-outline' },
        { title: 'Forum boards', value: stats?.forum_v2_boards ?? 0, icon: 'grid-outline' },
        { title: 'Forum threads', value: stats?.forum_v2_threads ?? 0, icon: 'reader-outline' },
        { title: 'Forum posts', value: stats?.forum_v2_posts ?? 0, icon: 'document-text-outline' },
        { title: 'UGC Reports', value: stats?.channel_reports_total || 0, icon: 'flag-outline' },
    ];

    return (
        <ScrollView
            style={styles.container}
            refreshControl={
                <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.foreground} />
            }
        >
            <View style={styles.header}>
                <Text style={styles.title}>Admin Dashboard</Text>
                <Text style={styles.subtitle}>Platform overview</Text>
            </View>

            <View style={styles.grid}>
                {cards.map((card, idx) => (
                    <View key={idx} style={styles.card}>
                        <View style={styles.iconContainer}>
                            <Ionicons name={card.icon as any} size={22} color={colors.foreground} />
                        </View>
                        <Text style={styles.cardValue}>{card.value}</Text>
                        <Text style={styles.cardTitle}>{card.title}</Text>
                    </View>
                ))}
            </View>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.lg, paddingTop: spacing.xxl },
    title: { ...typography.h1 },
    subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 2 },
    grid: { flexDirection: 'row', flexWrap: 'wrap', padding: spacing.md },
    card: {
        width: '45%',
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.lg,
        margin: '2.5%',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
    },
    iconContainer: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center', marginBottom: spacing.md },
    cardValue: { fontSize: 24, fontWeight: '700', color: colors.foreground },
    cardTitle: { fontSize: 11, color: colors.textMuted, marginTop: 4, fontWeight: '500' },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
});
