import React, { useCallback, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    FlatList,
    TouchableOpacity,
    ActivityIndicator,
    RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

type Report = {
    id: string;
    created_at: string;
    reason: string;
    channel_id: string;
    channel_name: string | null;
    message_id: string;
    message_preview: string | null;
    message_has_attachment: boolean;
    reporter_email: string | null;
    reported_email: string | null;
};

export default function AdminChannelReportsScreen({ navigation }: any) {
    const [reports, setReports] = useState<Report[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    const load = async () => {
        try {
            const data = await api.getAdminChannelReports(0, 100);
            setReports(data.reports || []);
            setTotal(data.total ?? 0);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    useFocusEffect(
        useCallback(() => {
            setLoading(true);
            load();
        }, [])
    );

    const onRefresh = () => {
        setRefreshing(true);
        load();
    };

    const renderItem = ({ item }: { item: Report }) => (
        <TouchableOpacity
            style={styles.card}
            activeOpacity={0.7}
            onPress={() =>
                navigation.navigate('ChannelChat', {
                    channelId: item.channel_id,
                    channelName: item.channel_name || 'Channel',
                })
            }
        >
            <View style={styles.cardTop}>
                <Text style={styles.reason} numberOfLines={2}>
                    {item.reason || 'No reason given'}
                </Text>
                <Text style={styles.date}>{new Date(item.created_at).toLocaleString()}</Text>
            </View>
            <Text style={styles.channel} numberOfLines={1}>
                #{item.channel_name || item.channel_id.slice(0, 8)}
            </Text>
            <Text style={styles.meta}>
                Reporter: {item.reporter_email || '—'} → Reported: {item.reported_email || '—'}
            </Text>
            {item.message_preview ? (
                <Text style={styles.preview} numberOfLines={3}>
                    {item.message_preview}
                </Text>
            ) : item.message_has_attachment ? (
                <Text style={styles.previewMuted}>[Image attachment]</Text>
            ) : null}
            <View style={styles.openRow}>
                <Text style={styles.openHint}>Open channel</Text>
                <Ionicons name="chevron-forward" size={18} color={colors.info} />
            </View>
        </TouchableOpacity>
    );

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Channel reports</Text>
                <Text style={styles.subtitle}>
                    {total} total — triage under App Review Guideline 1.2
                </Text>
            </View>
            {loading ? (
                <View style={styles.center}>
                    <ActivityIndicator color={colors.foreground} />
                </View>
            ) : (
                <FlatList
                    data={reports}
                    keyExtractor={(item) => item.id}
                    renderItem={renderItem}
                    contentContainerStyle={styles.list}
                    refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
                    ListEmptyComponent={<Text style={styles.empty}>No reports yet</Text>}
                />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.lg, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
    title: { ...typography.h2 },
    subtitle: { fontSize: 13, color: colors.textMuted, marginTop: 4 },
    list: { padding: spacing.lg, paddingBottom: spacing.xxl },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        marginBottom: spacing.md,
        ...shadows.sm,
    },
    cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.sm },
    reason: { flex: 1, fontSize: 14, fontWeight: '600', color: colors.foreground },
    date: { fontSize: 11, color: colors.textMuted },
    channel: { fontSize: 13, color: colors.info, marginTop: spacing.sm, fontWeight: '600' },
    meta: { fontSize: 12, color: colors.textSecondary, marginTop: 4 },
    preview: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.sm, lineHeight: 18 },
    previewMuted: { fontSize: 12, color: colors.textMuted, marginTop: spacing.sm, fontStyle: 'italic' },
    openRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', marginTop: spacing.sm },
    openHint: { fontSize: 12, color: colors.info, fontWeight: '600', marginRight: 4 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    empty: { textAlign: 'center', color: colors.textMuted, marginTop: 48, fontSize: 14 },
});
