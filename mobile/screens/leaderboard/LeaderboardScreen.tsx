import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function LeaderboardScreen() {
    const [entries, setEntries] = useState<any[]>([]);
    const [myRank, setMyRank] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadLeaderboard(); }, []);

    const loadLeaderboard = async () => {
        try { const [leaderboard, rank] = await Promise.all([api.getLeaderboard(), api.getMyRank()]); setEntries(leaderboard.entries || []); setMyRank(rank); }
        catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const renderEntry = ({ item, index }: { item: any; index: number }) => {
        const isTop3 = item.rank <= 3;
        return (
            <View style={styles.entryRow}>
                <View style={styles.rankCol}>
                    {item.rank === 1 ? (
                        <View style={styles.rankBadgeGold}><Text style={styles.rankBadgeText}>1</Text></View>
                    ) : item.rank === 2 ? (
                        <View style={styles.rankBadgeSilver}><Text style={styles.rankBadgeText}>2</Text></View>
                    ) : item.rank === 3 ? (
                        <View style={styles.rankBadgeBronze}><Text style={styles.rankBadgeText}>3</Text></View>
                    ) : (
                        <Text style={styles.rankPlain}>{item.rank}</Text>
                    )}
                </View>
                <View style={styles.userCol}>
                    <Text style={[styles.entryName, isTop3 && styles.entryNameBold]} numberOfLines={1}>{item.user_email}</Text>
                    <Text style={styles.entryLevel}>Lv {item.level?.toFixed(1)}</Text>
                </View>
                <Text style={[styles.entryScore, isTop3 && styles.entryScoreBold]}>{Math.round(item.score)}</Text>
            </View>
        );
    };

    if (loading) return <View style={[styles.container, styles.centerContent]}><ActivityIndicator size="large" color={colors.accent} /></View>;

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Leaderboard</Text>
            </View>

            {myRank && (
                <View style={styles.myRankCard}>
                    <View style={styles.myRankTop}>
                        <View>
                            <Text style={styles.myRankLabel}>YOUR RANK</Text>
                            {myRank.rank !== null ? (
                                <Text style={styles.myRankValue}>#{myRank.rank}<Text style={styles.myRankTotal}> / {myRank.total_users}</Text></Text>
                            ) : (
                                <Text style={styles.myRankMessage}>{myRank.message || 'Complete a scan to join'}</Text>
                            )}
                        </View>
                        {myRank.rank !== null && (
                            <View style={styles.myRankScoreBubble}>
                                <Text style={styles.myRankScoreValue}>{Math.round(myRank.score || 0)}</Text>
                                <Text style={styles.myRankScoreUnit}>pts</Text>
                            </View>
                        )}
                    </View>
                    {myRank.rank !== null && (
                        <View style={styles.myStats}>
                            <View style={styles.myStat}>
                                <Text style={styles.myStatValue}>{myRank.level?.toFixed(1) || '0'}</Text>
                                <Text style={styles.myStatLabel}>Level</Text>
                            </View>
                            <View style={styles.statDivider} />
                            <View style={styles.myStat}>
                                <Text style={styles.myStatValue}>{myRank.streak_days || 0}</Text>
                                <Text style={styles.myStatLabel}>Streak</Text>
                            </View>
                            <View style={styles.statDivider} />
                            <View style={styles.myStat}>
                                <Text style={styles.myStatValue}>{myRank.improvement_percentage?.toFixed(0) || 0}%</Text>
                                <Text style={styles.myStatLabel}>Improve</Text>
                            </View>
                        </View>
                    )}
                </View>
            )}

            <FlatList
                data={entries}
                renderItem={renderEntry}
                keyExtractor={(item) => item.user_id}
                contentContainerStyle={styles.list}
                showsVerticalScrollIndicator={false}
                ItemSeparatorComponent={() => <View style={styles.separator} />}
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    centerContent: { justifyContent: 'center', alignItems: 'center' },
    header: { paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
    title: { ...typography.h2 },

    myRankCard: {
        marginHorizontal: spacing.lg,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.lg,
        marginBottom: spacing.lg,
        ...shadows.sm,
    },
    myRankTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
    myRankLabel: {
        fontSize: 10, fontWeight: '600', letterSpacing: 1.5,
        color: colors.textMuted, marginBottom: 4,
    },
    myRankValue: { fontSize: 28, fontWeight: '700', color: colors.textPrimary },
    myRankTotal: { fontSize: 16, fontWeight: '400', color: colors.textMuted },
    myRankMessage: { ...typography.body, marginTop: spacing.xs, color: colors.textSecondary },
    myRankScoreBubble: {
        alignItems: 'center', justifyContent: 'center',
        backgroundColor: colors.accentMuted,
        borderRadius: borderRadius.md,
        paddingHorizontal: 14, paddingVertical: 8,
    },
    myRankScoreValue: { fontSize: 18, fontWeight: '700', color: colors.accent },
    myRankScoreUnit: { fontSize: 10, fontWeight: '500', color: colors.textMuted, marginTop: -2 },

    myStats: {
        flexDirection: 'row', marginTop: spacing.lg,
        paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.border,
    },
    myStat: { flex: 1, alignItems: 'center' },
    myStatValue: { fontSize: 18, fontWeight: '600', color: colors.textPrimary },
    myStatLabel: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
    statDivider: { width: 1, backgroundColor: colors.border, marginVertical: 2 },

    list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl },
    separator: { height: 1, backgroundColor: colors.borderLight, marginVertical: 2 },

    entryRow: {
        flexDirection: 'row', alignItems: 'center',
        paddingVertical: 12, paddingHorizontal: 4,
    },
    rankCol: { width: 36, alignItems: 'center' },
    rankBadgeGold: {
        width: 26, height: 26, borderRadius: 13,
        backgroundColor: colors.accent,
        alignItems: 'center', justifyContent: 'center',
    },
    rankBadgeSilver: {
        width: 26, height: 26, borderRadius: 13,
        backgroundColor: colors.textMuted,
        alignItems: 'center', justifyContent: 'center',
    },
    rankBadgeBronze: {
        width: 26, height: 26, borderRadius: 13,
        backgroundColor: colors.accentLight,
        alignItems: 'center', justifyContent: 'center',
    },
    rankBadgeText: { fontSize: 12, fontWeight: '700', color: colors.buttonText },
    rankPlain: { fontSize: 14, fontWeight: '500', color: colors.textMuted },

    userCol: { flex: 1, marginLeft: spacing.sm },
    entryName: { fontSize: 14, fontWeight: '400', color: colors.textPrimary },
    entryNameBold: { fontWeight: '600' },
    entryLevel: { fontSize: 11, color: colors.textMuted, marginTop: 1 },

    entryScore: { fontSize: 15, fontWeight: '500', color: colors.textSecondary },
    entryScoreBold: { fontWeight: '700', color: colors.textPrimary },
});
