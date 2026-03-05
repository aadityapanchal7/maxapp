import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function LeaderboardManageScreen() {
    const [rankings, setRankings] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadRankings(); }, []);

    const loadRankings = async () => {
        try { const data = await api.getLeaderboard(); setRankings(data || []); }
        catch (error) { console.error(error); }
        finally { setLoading(false); }
    };

    const renderEntry = ({ item }: { item: any }) => (
        <View style={styles.card}>
            <Text style={styles.rank}>#{item.rank}</Text>
            <View style={styles.info}>
                <Text style={styles.email}>{item.user_email || 'User'}</Text>
                <Text style={styles.score}>{item.score.toFixed(0)} pts</Text>
            </View>
            <View style={styles.stats}>
                <Text style={styles.statText}>{item.streak_days}d streak</Text>
                <Text style={styles.statText}>Lv {item.level}</Text>
            </View>
        </View>
    );

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Leaderboard Monitor</Text>
            </View>
            {loading ? (
                <View style={styles.center}><ActivityIndicator color={colors.foreground} /></View>
            ) : (
                <FlatList data={rankings} renderItem={renderEntry} keyExtractor={(item) => item.user_id} contentContainerStyle={styles.list} />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.lg },
    title: { ...typography.h2 },
    list: { paddingHorizontal: spacing.lg },
    card: {
        flexDirection: 'row', alignItems: 'center',
        backgroundColor: colors.card, borderRadius: borderRadius.lg,
        padding: spacing.md, marginBottom: spacing.sm,
        ...shadows.sm,
    },
    rank: { fontSize: 18, fontWeight: '700', color: colors.foreground, width: 40 },
    info: { flex: 1 },
    email: { fontSize: 14, fontWeight: '600', color: colors.foreground },
    score: { fontSize: 12, color: colors.textMuted, marginTop: 1 },
    stats: { alignItems: 'flex-end' },
    statText: { fontSize: 11, color: colors.textSecondary },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});
