import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { useForumV2NotificationsQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

type Notif = {
    id: string;
    type: string;
    entity_id: string;
    actor_user_id?: string | null;
    payload?: any;
    is_read?: boolean;
    created_at?: string;
};

export default function ForumNotificationsV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const [unreadOnly, setUnreadOnly] = useState(false);
    const q = useForumV2NotificationsQuery(unreadOnly);
    const items: Notif[] = useMemo(() => (q.data ?? []) as Notif[], [q.data]);

    const open = async (n: Notif) => {
        try {
            await api.markForumV2NotificationRead(n.id);
            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Notifications(unreadOnly) });
        } catch {}
        const threadId = n.payload?.thread_id || n.payload?.threadId || (n.type === 'reply' || n.type === 'watch' ? n.entity_id : null);
        if (threadId) navigation.navigate('ThreadV2', { threadId, threadTitle: 'thread' });
    };

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn} activeOpacity={0.8}>
                    <Ionicons name="arrow-back" size={20} color={colors.textSecondary} />
                </TouchableOpacity>
                <Text style={styles.title}>notifications</Text>
                <View style={{ flex: 1 }} />
                <TouchableOpacity
                    style={[styles.pill, unreadOnly && styles.pillActive]}
                    onPress={() => setUnreadOnly((v) => !v)}
                    activeOpacity={0.85}
                >
                    <Text style={[styles.pillText, unreadOnly && styles.pillTextActive]}>{unreadOnly ? 'unread' : 'all'}</Text>
                </TouchableOpacity>
            </View>

            {q.isPending && items.length === 0 ? (
                <View style={styles.loadingWrap}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            ) : (
                <FlashList
                    data={items}
                    keyExtractor={(it) => it.id}
                    contentContainerStyle={styles.list}
                    renderItem={({ item }) => (
                        <TouchableOpacity style={[styles.card, !item.is_read && styles.cardUnread]} onPress={() => void open(item)} activeOpacity={0.85}>
                            <Text style={styles.cardTitle} numberOfLines={1}>
                                {item.type}
                                {!item.is_read ? ' · new' : ''}
                            </Text>
                            <Text style={styles.cardBody} numberOfLines={2}>
                                {item.payload?.username ? `@${item.payload.username} ` : ''}
                                {item.type === 'reply' ? 'replied to your thread' : item.type === 'mention' ? 'mentioned you' : item.type === 'watch' ? 'new post in a watched thread' : 'activity'}
                            </Text>
                        </TouchableOpacity>
                    )}
                    ListEmptyComponent={
                        <View style={styles.empty}>
                            <Text style={styles.emptyTitle}>no notifications</Text>
                        </View>
                    }
                />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: colors.card,
    },
    iconBtn: {
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    title: { color: colors.foreground, fontSize: 18, fontWeight: '900' },
    pill: {
        height: 32,
        paddingHorizontal: 12,
        borderRadius: 16,
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
        alignItems: 'center',
        justifyContent: 'center',
    },
    pillActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    pillText: { color: colors.textSecondary, fontSize: 12, fontWeight: '800' },
    pillTextActive: { color: colors.background },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    list: { padding: spacing.lg, paddingBottom: spacing.xxl },
    card: {
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.lg,
        padding: spacing.lg,
        marginBottom: spacing.md,
        ...shadows.sm,
    },
    cardUnread: { borderColor: colors.foreground },
    cardTitle: { color: colors.foreground, fontSize: 13, fontWeight: '900' },
    cardBody: { color: colors.textMuted, fontSize: 12, marginTop: 8, lineHeight: 16 },
    empty: { padding: spacing.xxl, alignItems: 'center' },
    emptyTitle: { color: colors.foreground, fontSize: 14, fontWeight: '800' },
    emptyText: { color: colors.textMuted, fontSize: 12, marginTop: 6, textAlign: 'center' },
});

