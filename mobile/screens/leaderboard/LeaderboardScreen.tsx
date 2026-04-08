import React, { useEffect, useState, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, ActivityIndicator, Animated } from 'react-native';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function LeaderboardScreen() {
    const [entries, setEntries] = useState<any[]>([]);
    const [myRank, setMyRank] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const fadeAnim = useRef(new Animated.Value(0)).current;

    useEffect(() => { loadLeaderboard(); }, []);

    const loadLeaderboard = async () => {
        try {
            const [leaderboard, rank] = await Promise.all([api.getLeaderboard(), api.getMyRank()]);
            setEntries(leaderboard.entries || []);
            setMyRank(rank);
            Animated.timing(fadeAnim, { toValue: 1, duration: 400, useNativeDriver: true }).start();
        } catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const renderEntry = ({ item }: { item: any }) => {
        const isTop3 = item.rank <= 3;
        return (
            <View style={styles.entryRow}>
                <View style={styles.rankCol}>
                    {item.rank <= 3 ? (
                        <View style={[styles.rankBadge, item.rank === 1 && styles.rank1, item.rank === 2 && styles.rank2, item.rank === 3 && styles.rank3]}>
                            <Text style={styles.rankBadgeText}>{item.rank}</Text>
                        </View>
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

    if (loading) return <View style={[styles.container, styles.centerContent]}><ActivityIndicator size="large" color={colors.foreground} /></View>;

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Leaderboard</Text>
            </View>

            <Animated.View style={{ opacity: fadeAnim, flex: 1 }}>
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
            </Animated.View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    centerContent: { justifyContent: 'center', alignItems: 'center' },
    header: { paddingTop: 64, paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
    title: { ...typography.h2 },
    myRankCard: {
        marginHorizontal: spacing.lg,
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.lg,
        marginBottom: spacing.lg,
        borderWidth: 1,
        borderColor: colors.border,
    },
    myRankTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
    myRankLabel: { ...typography.label, marginBottom: 4 },
    myRankValue: { fontSize: 28, fontWeight: '700', color: colors.foreground },
    myRankTotal: { fontSize: 16, fontWeight: '400', color: colors.textMuted },
    myRankMessage: { ...typography.body, marginTop: spacing.xs, color: colors.textSecondary },
    myRankScoreBubble: {
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderWidth: 1,
        borderColor: colors.border,
    },
    myRankScoreValue: { fontSize: 18, fontWeight: '700', color: colors.foreground },
    myRankScoreUnit: { fontSize: 10, fontWeight: '500', color: colors.textMuted, marginTop: -2 },
    myStats: {
        flexDirection: 'row', marginTop: spacing.lg,
        paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.borderLight,
    },
    myStat: { flex: 1, alignItems: 'center' },
    myStatValue: { fontSize: 18, fontWeight: '600', color: colors.foreground },
    myStatLabel: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
    statDivider: { width: 1, backgroundColor: colors.borderLight, marginVertical: 2 },
    list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl },
    separator: { height: 1, backgroundColor: colors.borderLight, marginVertical: 2 },
    entryRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, paddingHorizontal: 4 },
    rankCol: { width: 36, alignItems: 'center' },
    rankBadge: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
    rank1: { backgroundColor: colors.foreground },
    rank2: { backgroundColor: colors.textSecondary },
    rank3: { backgroundColor: colors.textMuted },
    rankBadgeText: { fontSize: 11, fontWeight: '700', color: colors.buttonText },
    rankPlain: { fontSize: 13, fontWeight: '500', color: colors.textMuted },
    userCol: { flex: 1, marginLeft: spacing.sm },
    entryName: { fontSize: 14, fontWeight: '400', color: colors.foreground },
    entryNameBold: { fontWeight: '600' },
    entryLevel: { fontSize: 11, color: colors.textMuted, marginTop: 1 },
    entryScore: { fontSize: 14, fontWeight: '500', color: colors.textSecondary },
    entryScoreBold: { fontWeight: '700', color: colors.foreground },
});
