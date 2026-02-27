import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function AdminDashboard() {
    const [stats, setStats] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadStats();
    }, []);

    const loadStats = async () => {
        try {
            const data = await api.getAdminStats();
            setStats(data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator color={colors.primaryLight} />
            </View>
        );
    }

    const cards = [
        { title: 'Total Users', value: stats?.total_users || 0, icon: 'people', color: '#4CAF50' },
        { title: 'Paid Users', value: stats?.paid_users || 0, icon: 'card', color: '#FFD700' },
        { title: 'Channels', value: stats?.total_channels || 0, icon: 'chatbubbles', color: colors.primaryLight },
        { title: 'Messages', value: stats?.total_messages || 0, icon: 'mail', color: '#2196F3' },
    ];

    return (
        <ScrollView style={styles.container}>
            <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.header}>
                <Text style={styles.title}>Admin Dashboard</Text>
                <Text style={styles.subtitle}>Platform Overview</Text>
            </LinearGradient>

            <View style={styles.grid}>
                {cards.map((card, idx) => (
                    <View key={idx} style={styles.card}>
                        <View style={[styles.iconContainer, { backgroundColor: card.color + '20' }]}>
                            <Ionicons name={card.icon as any} size={24} color={card.color} />
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
    header: { padding: spacing.xl, paddingBottom: spacing.xxl },
    title: { ...typography.h1, color: '#FFFFFF' },
    subtitle: { ...typography.body, color: colors.textSecondary },
    grid: { flexDirection: 'row', flexWrap: 'wrap', padding: spacing.md, marginTop: -spacing.xl },
    card: {
        width: '45%',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        padding: spacing.lg,
        margin: '2.5%',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.05)',
        alignItems: 'center',
    },
    iconContainer: { width: 48, height: 48, borderRadius: 24, justifyContent: 'center', alignItems: 'center', marginBottom: spacing.md },
    cardValue: { ...typography.h2, color: '#FFFFFF' },
    cardTitle: { ...typography.caption, color: colors.textMuted, marginTop: 4 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
});
