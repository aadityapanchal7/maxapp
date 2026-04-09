import React, { useMemo, useState, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, RefreshControl } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { useForumV2NotificationsQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { elevatedCardSurface } from '../../theme/screenAesthetic';

type Notif = {
    id: string;
    type: string;
    entity_id: string;
    actor_user_id?: string | null;
    payload?: any;
    is_read?: boolean;
    created_at?: string;
};

function formatRelativeTime(iso?: string | null): string {
    if (!iso) return '';
    const d = new Date(iso);
    const t = d.getTime();
    if (Number.isNaN(t)) return '';
    const sec = Math.floor((Date.now() - t) / 1000);
    if (sec < 45) return 'Just now';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h}h ago`;
    const days = Math.floor(h / 24);
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function notificationSummary(n: Notif): string {
    const u = n.payload?.username ? `@${n.payload.username} ` : '';
    if (n.type === 'reply') return `${u}replied to your thread`;
    if (n.type === 'mention') return `${u}mentioned you`;
    if (n.type === 'watch') return 'New post in a watched thread';
    if (n.type === 'quote') return `${u}quoted your post`;
    return 'Forum activity';
}

export default function ForumNotificationsV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const [unreadOnly, setUnreadOnly] = useState(false);
    const q = useForumV2NotificationsQuery(unreadOnly);
    const items: Notif[] = useMemo(() => (q.data ?? []) as Notif[], [q.data]);

    const onRefresh = useCallback(() => void q.refetch(), [q]);
    const listRefreshing = q.isRefetching && !q.isPending;

    const open = async (n: Notif) => {
        try {
            await api.markForumV2NotificationRead(n.id);
            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Notifications(unreadOnly) });
        } catch {
            /* still navigate */
        }
        const threadId =
            n.payload?.thread_id ||
            n.payload?.threadId ||
            (n.type === 'reply' || n.type === 'watch' ? n.entity_id : null);
        if (threadId) navigation.navigate('ThreadV2', { threadId, threadTitle: 'thread' });
    };

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={styles.iconBtn}
                    activeOpacity={0.8}
                    accessibilityRole="button"
                    accessibilityLabel="Go back"
                >
                    <Ionicons name="arrow-back" size={20} color={colors.textSecondary} />
                </TouchableOpacity>
                <Text style={styles.title}>Notifications</Text>
                <View style={{ flex: 1 }} />
                <TouchableOpacity
                    style={[styles.pill, unreadOnly && styles.pillActive]}
                    onPress={() => setUnreadOnly((v) => !v)}
                    activeOpacity={0.85}
                    accessibilityRole="button"
                    accessibilityLabel={unreadOnly ? 'Show all notifications' : 'Show unread only'}
                    accessibilityState={{ selected: unreadOnly }}
                >
                    <Text style={[styles.pillText, unreadOnly && styles.pillTextActive]}>{unreadOnly ? 'Unread' : 'All'}</Text>
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
                    keyboardShouldPersistTaps="handled"
                    refreshControl={
                        <RefreshControl refreshing={listRefreshing} onRefresh={onRefresh} tintColor={colors.foreground} />
                    }
                    renderItem={({ item }) => {
                        const unread = !item.is_read;
                        const rel = formatRelativeTime(item.created_at);
                        return (
                            <TouchableOpacity
                                style={[styles.row, unread && styles.rowUnread]}
                                onPress={() => void open(item)}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityLabel={`${notificationSummary(item)}${unread ? ', unread' : ''}`}
                            >
                                {unread ? <View style={styles.unreadStripe} accessibilityElementsHidden /> : null}
                                <View style={styles.rowInner}>
                                    <View style={styles.rowTop}>
                                        <Text style={[styles.typeLabel, unread && styles.typeLabelUnread]} numberOfLines={1}>
                                            {item.type === 'reply'
                                                ? 'Reply'
                                                : item.type === 'mention'
                                                  ? 'Mention'
                                                  : item.type === 'watch'
                                                    ? 'Watched thread'
                                                    : item.type}
                                        </Text>
                                        {rel ? <Text style={styles.timeMeta}>{rel}</Text> : null}
                                    </View>
                                    <Text style={[styles.summary, unread && styles.summaryUnread]} numberOfLines={2}>
                                        {notificationSummary(item)}
                                    </Text>
                                </View>
                                <Ionicons name="chevron-forward" size={18} color={colors.textMuted} style={styles.chevron} />
                            </TouchableOpacity>
                        );
                    }}
                    ListEmptyComponent={
                        <View style={styles.empty}>
                            <View style={styles.emptyCard}>
                                <Ionicons name="notifications-off-outline" size={36} color={colors.textMuted} style={{ marginBottom: spacing.md }} />
                                <Text style={styles.emptyTitle}>No notifications</Text>
                                <Text style={styles.emptySub}>
                                    {unreadOnly ? 'You’re all caught up.' : 'Replies and mentions will show up here.'}
                                </Text>
                            </View>
                        </View>
                    }
                />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background, overflow: 'hidden' },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.borderLight,
        backgroundColor: colors.card,
        zIndex: 1,
    },
    iconBtn: {
        width: 40,
        height: 40,
        borderRadius: 20,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    title: { fontFamily: fonts.serif, color: colors.foreground, fontSize: 20, fontWeight: '400' },
    pill: {
        minHeight: 36,
        paddingHorizontal: 14,
        borderRadius: 18,
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
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        minHeight: 56,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        marginBottom: spacing.sm,
        ...elevatedCardSurface,
        borderRadius: borderRadius.lg,
        overflow: 'hidden',
    },
    rowUnread: {
        backgroundColor: colors.accentMuted,
        borderColor: colors.foreground,
    },
    unreadStripe: {
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: 4,
        backgroundColor: colors.foreground,
        borderTopLeftRadius: borderRadius.lg,
        borderBottomLeftRadius: borderRadius.lg,
    },
    rowInner: { flex: 1, paddingLeft: spacing.sm, minWidth: 0 },
    rowTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
    typeLabel: {
        ...typography.caption,
        fontSize: 10,
        textTransform: 'uppercase',
        letterSpacing: 0.6,
        color: colors.textMuted,
        flex: 1,
    },
    typeLabelUnread: { color: colors.foreground, fontWeight: '800' },
    timeMeta: { ...typography.caption, fontSize: 11, color: colors.textMuted },
    summary: { ...typography.bodySmall, marginTop: 6, color: colors.textSecondary },
    summaryUnread: { color: colors.foreground, fontWeight: '600' },
    chevron: { marginLeft: spacing.sm },
    empty: { padding: spacing.xl, alignItems: 'center', paddingTop: spacing.xxl },
    emptyCard: {
        ...elevatedCardSurface,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        alignItems: 'center',
        maxWidth: 320,
    },
    emptyTitle: { color: colors.foreground, fontSize: 16, fontWeight: '800' },
    emptySub: { color: colors.textMuted, fontSize: 13, marginTop: spacing.sm, textAlign: 'center', lineHeight: 18 },
});
