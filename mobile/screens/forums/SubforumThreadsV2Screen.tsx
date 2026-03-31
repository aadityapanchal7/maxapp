import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useForumV2ThreadsQuery } from '../../hooks/useAppQueries';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

type Thread = {
    id: string;
    title: string;
    tags?: string[];
    reply_count?: number;
    view_count?: number;
    is_sticky?: boolean;
    is_locked?: boolean;
    last_post_at?: string;
    created_by_username?: string | null;
};

export default function SubforumThreadsV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const route = useRoute<any>();
    const params = route.params ?? {};
    const subforumId = params.subforumId as string;
    const subforumName = (params.subforumName as string) ?? 'board';
    const isReadOnly = !!params.isReadOnly;

    const [sort, setSort] = useState<'new' | 'hot' | 'top'>('new');
    const [q, setQ] = useState('');

    const threadsQ = useForumV2ThreadsQuery({ subforumId, sort, q: q.trim(), tag: '' });
    const threads: Thread[] = useMemo(() => (threadsQ.data?.threads ?? []) as Thread[], [threadsQ.data]);
    const loading = threadsQ.isPending && threads.length === 0;

    const openThread = (t: Thread) => navigation.navigate('ThreadV2', { threadId: t.id, threadTitle: t.title });

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <View style={styles.headerTop}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn} activeOpacity={0.8}>
                        <Ionicons name="arrow-back" size={20} color={colors.textSecondary} />
                    </TouchableOpacity>
                    <View style={{ flex: 1 }}>
                        <Text style={styles.title} numberOfLines={1}>
                            {subforumName}
                        </Text>
                        <Text style={styles.subtitle}>{isReadOnly ? 'read-only board' : 'threads'}</Text>
                    </View>
                    {!isReadOnly && (
                        <TouchableOpacity
                            onPress={() => navigation.navigate('NewThreadV2', { subforumId, subforumName })}
                            style={styles.newBtn}
                            activeOpacity={0.85}
                        >
                            <Ionicons name="add" size={16} color={colors.background} />
                            <Text style={styles.newBtnText}>new</Text>
                        </TouchableOpacity>
                    )}
                </View>

                <View style={styles.searchRow}>
                    <Ionicons name="search" size={18} color={colors.textMuted} />
                    <TextInput
                        style={styles.searchInput}
                        placeholder="search threads..."
                        placeholderTextColor={colors.textMuted}
                        value={q}
                        onChangeText={setQ}
                    />
                    {q.trim().length > 0 ? (
                        <TouchableOpacity onPress={() => setQ('')} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                            <Ionicons name="close-circle" size={18} color={colors.textMuted} />
                        </TouchableOpacity>
                    ) : null}
                </View>

                <View style={styles.sortRow}>
                    {(['new', 'hot', 'top'] as const).map((k) => (
                        <TouchableOpacity
                            key={k}
                            style={[styles.sortPill, sort === k && styles.sortPillActive]}
                            onPress={() => setSort(k)}
                            activeOpacity={0.8}
                        >
                            <Text style={[styles.sortText, sort === k && styles.sortTextActive]}>{k}</Text>
                        </TouchableOpacity>
                    ))}
                </View>
            </View>

            {loading ? (
                <View style={styles.loadingWrap}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            ) : (
                <FlashList
                    data={threads}
                    keyExtractor={(it) => it.id}
                    contentContainerStyle={styles.list}
                    renderItem={({ item }) => (
                        <TouchableOpacity style={styles.threadCard} onPress={() => openThread(item)} activeOpacity={0.85}>
                            <View style={styles.threadTopRow}>
                                <Text style={styles.threadTitle} numberOfLines={2}>
                                    {item.is_sticky ? 'pinned · ' : ''}
                                    {item.title}
                                </Text>
                                {item.is_locked ? <Text style={styles.locked}>locked</Text> : null}
                            </View>
                            <View style={styles.metaRow}>
                                <Text style={styles.metaText}>
                                    {(item.reply_count ?? 0).toString()} replies · {(item.view_count ?? 0).toString()} views
                                </Text>
                                {item.created_by_username ? <Text style={styles.metaText}> · @{item.created_by_username}</Text> : null}
                            </View>
                            {item.tags && item.tags.length > 0 ? (
                                <Text style={styles.tags} numberOfLines={1}>
                                    {item.tags.slice(0, 4).map((t) => `#${t}`).join(' ')}
                                </Text>
                            ) : null}
                        </TouchableOpacity>
                    )}
                    ListEmptyComponent={
                        <View style={styles.empty}>
                            <Text style={styles.emptyTitle}>no threads yet</Text>
                            <Text style={styles.emptyText}>be the first to post something useful.</Text>
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
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: colors.card,
    },
    headerTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
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
    title: { color: colors.foreground, fontSize: 18, fontWeight: '800' },
    subtitle: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
    newBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        backgroundColor: colors.foreground,
        paddingHorizontal: 12,
        height: 36,
        borderRadius: 18,
    },
    newBtnText: { color: colors.background, fontSize: 12, fontWeight: '800' },
    searchRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: 18,
        paddingHorizontal: 12,
        height: 40,
        marginTop: spacing.md,
    },
    searchInput: { flex: 1, color: colors.foreground, fontSize: 13 },
    sortRow: { flexDirection: 'row', gap: 8, marginTop: spacing.md },
    sortPill: {
        paddingHorizontal: 12,
        height: 32,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: colors.border,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
    },
    sortPillActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    sortText: { color: colors.textSecondary, fontSize: 12, fontWeight: '700' },
    sortTextActive: { color: colors.background },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    list: { padding: spacing.lg, paddingBottom: spacing.xxl },
    threadCard: {
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.lg,
        padding: spacing.lg,
        marginBottom: spacing.md,
        ...shadows.sm,
    },
    threadTopRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
    threadTitle: { color: colors.foreground, fontSize: 14, fontWeight: '800', flex: 1 },
    locked: { color: colors.textMuted, fontSize: 11, fontWeight: '800' },
    metaRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 8 },
    metaText: { color: colors.textMuted, fontSize: 11 },
    tags: { marginTop: 8, color: colors.textSecondary, fontSize: 11, fontWeight: '700' },
    empty: { padding: spacing.xxl, alignItems: 'center' },
    emptyTitle: { color: colors.foreground, fontSize: 14, fontWeight: '800' },
    emptyText: { color: colors.textMuted, fontSize: 12, marginTop: 6, textAlign: 'center' },
});

