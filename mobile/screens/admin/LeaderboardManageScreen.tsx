import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function LeaderboardManageScreen() {
    const [rankings, setRankings] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadRankings();
    }, []);

    const loadRankings = async () => {
        try {
            const data = await api.getLeaderboard();
            setRankings(data || []);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const renderEntry = ({ item }: { item: any }) => (
        <View style={styles.card}>
            <Text style={styles.rank}>#{item.rank}</Text>
            <View style={styles.info}>
                <Text style={styles.email}>{item.user_email || 'User'}</Text>
                <Text style={styles.score}>{item.score.toFixed(0)} Points</Text>
            </View>
            <View style={styles.stats}>
                <Text style={styles.statText}>{item.streak_days}d Streak</Text>
                <Text style={styles.statText}>Lvl {item.level}</Text>
            </View>
        </View>
    );

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Leaderboard Monitor</Text>
            </View>

            {loading ? (
                <View style={styles.center}><ActivityIndicator color={colors.primaryLight} /></View>
            ) : (
                <FlatList
                    data={rankings}
                    renderItem={renderEntry}
                    keyExtractor={(item) => item.user_id}
                    contentContainerStyle={styles.list}
                />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.md, backgroundColor: colors.surface },
    title: { ...typography.h2, color: '#FFFFFF' },
    list: { padding: spacing.md },
    card: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.sm },
    rank: { ...typography.h2, color: colors.primaryLight, width: 40 },
    info: { flex: 1 },
    email: { ...typography.body, fontWeight: 'bold', color: '#FFFFFF' },
    score: { fontSize: 12, color: colors.textMuted },
    stats: { alignItems: 'flex-end' },
    statText: { fontSize: 10, color: colors.textSecondary },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});
