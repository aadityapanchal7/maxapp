import React, { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import {
    View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator,
    RefreshControl, LayoutAnimation, Platform, UIManager,
} from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useForumV2ThreadsQuery } from '../../hooks/useAppQueries';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
    UIManager.setLayoutAnimationEnabledExperimental(true);
}

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
    const [searchActive, setSearchActive] = useState(false);
    const searchInputRef = useRef<TextInput>(null);
    const [q, setQ] = useState('');
    const [debouncedQ, setDebouncedQ] = useState('');
    useEffect(() => {
        const t = setTimeout(() => setDebouncedQ(q.trim()), 350);
        return () => clearTimeout(t);
    }, [q]);

    const openSearch = () => {
        LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
        setSearchActive(true);
        setTimeout(() => searchInputRef.current?.focus(), 100);
    };
    const closeSearch = () => {
        LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
        setQ('');
        setSearchActive(false);
        searchInputRef.current?.blur();
    };

    const threadsQ = useForumV2ThreadsQuery({ subforumId, sort, q: debouncedQ, tag: '' });
    const threads: Thread[] = useMemo(() => (threadsQ.data?.threads ?? []) as Thread[], [threadsQ.data]);
    const loading = threadsQ.isPending && threads.length === 0;

    const openThread = (t: Thread) => navigation.navigate('ThreadV2', { threadId: t.id, threadTitle: t.title });

    const onRefresh = useCallback(() => void threadsQ.refetch(), [threadsQ]);
    const listRefreshing = threadsQ.isRefetching && !threadsQ.isPending;

    return (
        <View style={styles.container}>
            <View style={styles.screenFill} pointerEvents="none" />
            <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
                {searchActive ? (
                    <View style={styles.searchBarActive}>
                        <Ionicons name="search-outline" size={17} color={colors.textMuted} />
                        <TextInput
                            ref={searchInputRef}
                            style={styles.searchInput}
                            placeholder="Search threads…"
                            placeholderTextColor={colors.textMuted}
                            value={q}
                            onChangeText={setQ}
                            autoCapitalize="none"
                            autoCorrect={false}
                        />
                        <TouchableOpacity
                            onPress={closeSearch}
                            style={styles.searchCancelHit}
                            accessibilityRole="button"
                            accessibilityLabel="Close search"
                        >
                            <Text style={styles.searchCancelText}>Cancel</Text>
                        </TouchableOpacity>
                    </View>
                ) : (
                    <View style={styles.headerTop}>
                        <TouchableOpacity
                            onPress={() => navigation.goBack()}
                            style={styles.iconBtn}
                            activeOpacity={0.8}
                            accessibilityRole="button"
                            accessibilityLabel="Go back"
                        >
                            <Ionicons name="arrow-back" size={20} color={colors.textSecondary} />
                        </TouchableOpacity>
                        <View style={{ flex: 1 }}>
                            <Text style={styles.title} numberOfLines={1}>
                                {subforumName}
                            </Text>
                            <Text style={styles.subtitle}>{isReadOnly ? 'read-only board' : 'threads'}</Text>
                        </View>
                        <TouchableOpacity
                            onPress={openSearch}
                            style={styles.iconBtn}
                            activeOpacity={0.7}
                            accessibilityRole="button"
                            accessibilityLabel="Search threads"
                        >
                            <Ionicons name="search-outline" size={18} color={colors.textMuted} />
                        </TouchableOpacity>
                        {!isReadOnly && (
                            <TouchableOpacity
                                onPress={() => navigation.navigate('NewThreadV2', { subforumId, subforumName })}
                                style={styles.newBtn}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityLabel="Create new thread"
                            >
                                <Ionicons name="add" size={16} color={colors.foreground} />
                                <Text style={styles.newBtnText}>New</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                )}

                <View style={styles.sortRow}>
                    {(['new', 'hot', 'top'] as const).map((k) => (
                        <TouchableOpacity
                            key={k}
                            style={[styles.sortPill, sort === k && styles.sortPillActive]}
                            onPress={() => setSort(k)}
                            activeOpacity={0.8}
                            accessibilityRole="button"
                            accessibilityState={{ selected: sort === k }}
                            accessibilityLabel={`Sort by ${k}`}
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
                    keyboardShouldPersistTaps="handled"
                    refreshControl={
                        <RefreshControl refreshing={listRefreshing} onRefresh={onRefresh} tintColor={colors.foreground} />
                    }
                    renderItem={({ item }) => (
                        <TouchableOpacity
                            style={styles.threadCard}
                            onPress={() => openThread(item)}
                            activeOpacity={0.85}
                            accessibilityRole="button"
                            accessibilityLabel={`Thread: ${item.title}`}
                        >
                            <View style={styles.threadTopRow}>
                                <Text style={styles.threadTitle} numberOfLines={2}>
                                    {item.is_sticky ? (
                                        <Text style={styles.pinnedPrefix}>Pinned · </Text>
                                    ) : null}
                                    {item.title}
                                </Text>
                                {item.is_locked ? (
                                    <View style={styles.lockedPill}>
                                        <Ionicons name="lock-closed" size={11} color={colors.textMuted} />
                                        <Text style={styles.locked}>Locked</Text>
                                    </View>
                                ) : null}
                            </View>
                            <View style={styles.metaRow}>
                                <Text style={styles.metaText}>
                                    {(item.reply_count ?? 0).toString()} replies · {(item.view_count ?? 0).toString()} views
                                </Text>
                                {item.created_by_username ? (
                                    <Text style={styles.metaText}> · @{item.created_by_username}</Text>
                                ) : null}
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
                            <View style={styles.emptyCard}>
                                <Ionicons name="chatbubbles-outline" size={32} color={colors.textMuted} style={{ marginBottom: spacing.md }} />
                                <Text style={styles.emptyTitle}>No threads yet</Text>
                                <Text style={styles.emptyText}>
                                    {debouncedQ ? 'Nothing matches that search. Try other words.' : 'Be the first to post something useful.'}
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
    screenFill: { ...StyleSheet.absoluteFillObject, backgroundColor: colors.background },
    header: {
        paddingHorizontal: spacing.xl,
        paddingBottom: spacing.lg,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
        backgroundColor: colors.background,
        zIndex: 1,
    },
    headerTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    iconBtn: {
        width: 40,
        height: 40,
        alignItems: 'center',
        justifyContent: 'center',
    },
    title: { ...typography.h3, fontSize: 18 },
    subtitle: { ...typography.caption, marginTop: 4, color: colors.textMuted, fontWeight: '400' },
    newBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingHorizontal: spacing.md,
        height: 34,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.foreground,
        backgroundColor: 'transparent',
    },
    newBtnText: { color: colors.foreground, fontSize: 12, fontWeight: '500', letterSpacing: 0.2 },
    searchBarActive: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingVertical: 10,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
    },
    searchInput: { flex: 1, color: colors.foreground, fontSize: 15, paddingVertical: 4, fontFamily: fonts.sans },
    searchCancelHit: {
        paddingVertical: 6,
        paddingHorizontal: 4,
    },
    searchCancelText: {
        fontSize: 14,
        fontWeight: '500',
        color: colors.textSecondary,
    },
    sortRow: { flexDirection: 'row', gap: spacing.lg, marginTop: spacing.md },
    sortPill: {
        paddingBottom: 8,
        borderBottomWidth: 2,
        borderBottomColor: 'transparent',
        backgroundColor: 'transparent',
    },
    sortPillActive: { borderBottomColor: colors.foreground, backgroundColor: 'transparent' },
    sortText: { color: colors.textMuted, fontSize: 12, fontWeight: '600', letterSpacing: 0.4, textTransform: 'uppercase' },
    sortTextActive: { color: colors.foreground },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    list: { padding: spacing.xl, paddingBottom: spacing.xxxl },
    threadCard: {
        paddingVertical: 20,
        paddingHorizontal: 0,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
    },
    threadTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.md },
    threadTitle: { color: colors.foreground, fontSize: 16, fontWeight: '500', lineHeight: 23, flex: 1, letterSpacing: -0.1 },
    pinnedPrefix: { color: colors.textMuted, fontWeight: '500' },
    lockedPill: { flexDirection: 'row', alignItems: 'center', gap: 4 },
    locked: { color: colors.textMuted, fontSize: 11, fontWeight: '500' },
    metaRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: spacing.md },
    metaText: { color: colors.textMuted, fontSize: 12 },
    tags: { marginTop: spacing.sm, color: colors.textSecondary, fontSize: 11, fontWeight: '500', letterSpacing: 0.2 },
    empty: { padding: spacing.xl, alignItems: 'center', paddingTop: spacing.xxl },
    emptyCard: {
        padding: spacing.xl,
        alignItems: 'center',
        maxWidth: 320,
    },
    emptyTitle: { ...typography.h3, fontSize: 17 },
    emptyText: { color: colors.textMuted, fontSize: 13, marginTop: spacing.sm, textAlign: 'center', lineHeight: 18 },
});

