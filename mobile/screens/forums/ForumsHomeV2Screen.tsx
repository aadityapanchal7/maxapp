import React, { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    TextInput,
    FlatList,
    RefreshControl,
    LayoutAnimation,
    Platform,
    UIManager,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { useForumV2CategoriesQuery, useForumV2SubforumsQuery, useForumV2SearchQuery } from '../../hooks/useAppQueries';
import { colors, spacing, typography, fonts } from '../../theme/dark';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
    UIManager.setLayoutAnimationEnabledExperimental(true);
}
type Category = { id: string; name: string; slug: string; description?: string; order?: number };
type Subforum = {
    id: string;
    category_id: string;
    name: string;
    slug: string;
    description?: string;
    access_tier?: 'public' | 'premium';
    is_read_only?: boolean;
    thread_count?: number;
    last_activity?: string;
};

type SearchHit = {
    id: string;
    title: string;
    subforum?: { id: string; name: string; slug?: string };
};

export default function ForumsHomeV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { isPremium } = useAuth() as any;
    const catsQ = useForumV2CategoriesQuery();
    const subsQ = useForumV2SubforumsQuery(null);

    const [searchActive, setSearchActive] = useState(false);
    const searchInputRef = useRef<TextInput>(null);
    const [searchInput, setSearchInput] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    useEffect(() => {
        const t = setTimeout(() => setDebouncedSearch(searchInput.trim()), 400);
        return () => clearTimeout(t);
    }, [searchInput]);

    const openSearch = () => {
        LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
        setSearchActive(true);
        setTimeout(() => searchInputRef.current?.focus(), 100);
    };
    const closeSearch = () => {
        LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
        setSearchInput('');
        setSearchActive(false);
        searchInputRef.current?.blur();
    };

    const searchQ = useForumV2SearchQuery(debouncedSearch);
    const searchHits: SearchHit[] = useMemo(() => (searchQ.data ?? []) as SearchHit[], [searchQ.data]);

    const categories: Category[] = useMemo(() => catsQ.data ?? [], [catsQ.data]);
    const subforums: Subforum[] = useMemo(() => subsQ.data ?? [], [subsQ.data]);
    const loading = (catsQ.isPending && categories.length === 0) || (subsQ.isPending && subforums.length === 0);

    const canAccessPremium = isPremium;
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

    const subsByCategory = useMemo(() => {
        const m = new Map<string, Subforum[]>();
        for (const s of subforums) {
            const arr = m.get(s.category_id) ?? [];
            arr.push(s);
            m.set(s.category_id, arr);
        }
        for (const [k, arr] of m.entries()) {
            arr.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
            m.set(k, arr);
        }
        return m;
    }, [subforums]);

    const openSubforum = (s: Subforum) => {
        const tier = (s.access_tier ?? 'public').toLowerCase();
        if (tier === 'premium' && !canAccessPremium) {
            navigation.navigate('Payment');
            return;
        }
        navigation.navigate('SubforumThreadsV2', { subforumId: s.id, subforumName: s.name, accessTier: tier, isReadOnly: !!s.is_read_only });
    };
    const toggleCollapsed = (categoryId: string) => {
        setCollapsed((prev) => ({ ...prev, [categoryId]: !prev[categoryId] }));
    };

    const openThread = (hit: SearchHit) => {
        navigation.navigate('ThreadV2', { threadId: hit.id, threadTitle: hit.title });
    };

    const showSearchResults = debouncedSearch.length >= 2;

    const refreshing =
        (catsQ.isRefetching && !catsQ.isPending) || (subsQ.isRefetching && !subsQ.isPending) || (searchQ.isRefetching && showSearchResults);
    const onRefresh = useCallback(() => {
        void Promise.all([
            catsQ.refetch(),
            subsQ.refetch(),
            ...(showSearchResults && debouncedSearch.length >= 2 ? [searchQ.refetch()] : []),
        ]);
    }, [catsQ, subsQ, searchQ, showSearchResults, debouncedSearch]);

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
                {searchActive ? (
                    <View style={styles.searchBarActive}>
                        <Ionicons name="search-outline" size={17} color={colors.textMuted} />
                        <TextInput
                            ref={searchInputRef}
                            style={styles.searchInput}
                            placeholder="Search all threads…"
                            placeholderTextColor={colors.textMuted}
                            value={searchInput}
                            onChangeText={setSearchInput}
                            autoCapitalize="none"
                            autoCorrect={false}
                        />
                        <TouchableOpacity
                            onPress={closeSearch}
                            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                            style={styles.searchCancelHit}
                            accessibilityRole="button"
                            accessibilityLabel="Close search"
                        >
                            <Text style={styles.searchCancelText}>Cancel</Text>
                        </TouchableOpacity>
                    </View>
                ) : (
                    <View style={styles.headerRow}>
                        <Text style={styles.title}>Forums</Text>
                        <View style={styles.headerActions}>
                            <TouchableOpacity
                                style={styles.iconBtn}
                                onPress={openSearch}
                                activeOpacity={0.7}
                                accessibilityRole="button"
                                accessibilityLabel="Search forums"
                            >
                                <Ionicons name="search-outline" size={20} color={colors.textMuted} />
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={styles.iconBtn}
                                onPress={() => navigation.navigate('ForumNotificationsV2')}
                                activeOpacity={0.7}
                                accessibilityRole="button"
                                accessibilityLabel="Forum notifications"
                            >
                                <Ionicons name="notifications-outline" size={20} color={colors.textMuted} />
                            </TouchableOpacity>
                        </View>
                    </View>
                )}
            </View>

            {showSearchResults ? (
                <View style={styles.searchBody}>
                    {searchQ.isPending ? (
                        <View style={styles.loadingWrap}>
                            <ActivityIndicator size="large" color={colors.foreground} />
                        </View>
                    ) : searchHits.length === 0 ? (
                        <View style={styles.emptySearch}>
                            <Ionicons name="search-outline" size={24} color={colors.textMuted} style={{ marginBottom: spacing.md }} />
                            <Text style={styles.emptySearchText}>No threads match “{debouncedSearch}”</Text>
                            <Text style={styles.emptySearchHint}>Try different words or check spelling.</Text>
                        </View>
                    ) : (
                        <FlatList
                            data={searchHits}
                            keyExtractor={(item) => item.id}
                            contentContainerStyle={styles.searchList}
                            keyboardShouldPersistTaps="handled"
                            refreshControl={
                                <RefreshControl refreshing={!!refreshing && showSearchResults} onRefresh={onRefresh} tintColor={colors.foreground} />
                            }
                            ItemSeparatorComponent={() => <View style={styles.divider} />}
                            renderItem={({ item }) => (
                                <TouchableOpacity
                                    style={styles.searchHitRow}
                                    onPress={() => openThread(item)}
                                    activeOpacity={0.7}
                                    accessibilityRole="button"
                                    accessibilityLabel={`Thread: ${item.title}`}
                                >
                                    <View style={{ flex: 1 }}>
                                        <Text style={styles.searchHitTitle} numberOfLines={2}>
                                            {item.title}
                                        </Text>
                                        {item.subforum?.name ? (
                                            <Text style={styles.searchHitMeta} numberOfLines={1}>
                                                {item.subforum.name}
                                            </Text>
                                        ) : null}
                                    </View>
                                    <Ionicons name="chevron-forward" size={14} color={colors.textMuted} style={{ opacity: 0.5 }} />
                                </TouchableOpacity>
                            )}
                        />
                    )}
                </View>
            ) : loading ? (
                <View style={styles.loadingWrap}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            ) : (
                <ScrollView
                    contentContainerStyle={styles.scroll}
                    keyboardShouldPersistTaps="handled"
                    refreshControl={
                        <RefreshControl refreshing={!!refreshing && !showSearchResults} onRefresh={onRefresh} tintColor={colors.foreground} />
                    }
                >
                    {categories.map((c) => {
                        const boards = subsByCategory.get(c.id) ?? [];
                        if (boards.length === 0) return null;
                        return (
                            <View key={c.id} style={styles.section}>
                                <TouchableOpacity
                                    style={styles.sectionHeader}
                                    onPress={() => toggleCollapsed(c.id)}
                                    activeOpacity={0.7}
                                    accessibilityRole="button"
                                    accessibilityLabel={`${collapsed[c.id] ? 'Expand' : 'Collapse'} ${c.name}`}
                                    accessibilityState={{ expanded: !collapsed[c.id] }}
                                >
                                    <View style={{ flex: 1 }}>
                                        <Text style={styles.sectionTitle}>{c.name}</Text>
                                        {c.description ? <Text style={styles.sectionDesc}>{c.description}</Text> : null}
                                    </View>
                                    <Ionicons
                                        name={collapsed[c.id] ? 'chevron-down' : 'chevron-up'}
                                        size={12}
                                        color={colors.textMuted}
                                        style={{ opacity: 0.35 }}
                                    />
                                </TouchableOpacity>
                                {!collapsed[c.id] ? (
                                    <>
                                        {boards.map((s, idx) => {
                                            const isPremiumBoard = (s.access_tier ?? 'public').toLowerCase() === 'premium';
                                            const isLocked = isPremiumBoard && !canAccessPremium;
                                            return (
                                                <View key={s.id}>
                                                    {idx > 0 && <View style={styles.boardDivider} />}
                                                    <TouchableOpacity
                                                        style={[
                                                        styles.boardRow,
                                                        isLocked && styles.boardRowLocked,
                                                        ]}
                                                        onPress={() => openSubforum(s)}
                                                        activeOpacity={0.7}
                                                    >
                                                        <View style={[styles.boardAccent, isPremiumBoard && styles.boardAccentPremium]} />
                                                        <View style={styles.boardMain}>
                                                            <View style={styles.boardTitleRow}>
                                                                <Text style={[styles.boardName, isLocked && styles.boardNameLocked]} numberOfLines={1}>
                                                                    {s.name}
                                                                </Text>
                                                                {isPremiumBoard ? (
                                                                    <Text style={styles.premiumBadgeText}>PREMIUM</Text>
                                                                ) : null}
                                                                {s.is_read_only ? <Text style={styles.readOnly}>read-only</Text> : null}
                                                            </View>
                                                            {s.description ? (
                                                                <Text style={styles.boardDesc} numberOfLines={2}>
                                                                    {s.description}
                                                                </Text>
                                                            ) : null}
                                                            <Text style={styles.meta}>{(s.thread_count ?? 0).toString()} threads</Text>
                                                        </View>
                                                        <Ionicons
                                                            name={isLocked ? 'lock-closed' : 'chevron-forward'}
                                                            size={14}
                                                            color={colors.textMuted}
                                                            style={{ opacity: isLocked ? 0.6 : 0.4 }}
                                                        />
                                                    </TouchableOpacity>
                                                </View>
                                            );
                                        })}
                                    </>
                                ) : null}
                            </View>
                        );
                    })}
                </ScrollView>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: {
        paddingHorizontal: spacing.xl,
        paddingBottom: spacing.lg,
        backgroundColor: colors.background,
    },
    headerRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
    },
    headerActions: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 2,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 34,
        fontWeight: '400',
        color: colors.textPrimary,
        letterSpacing: -0.5,
        lineHeight: 42,
    },
    subTitle: {
        marginTop: spacing.sm,
        color: colors.textMuted,
        fontSize: 13,
        lineHeight: 20,
        fontWeight: '400',
        letterSpacing: 0.1,
    },
    searchBarActive: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingVertical: 10,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
    },
    searchInput: {
        flex: 1,
        color: colors.foreground,
        fontSize: 15,
        paddingVertical: 4,
        fontFamily: fonts.sans,
    },
    searchCancelHit: {
        paddingVertical: 6,
        paddingHorizontal: 4,
    },
    searchCancelText: {
        fontSize: 14,
        fontWeight: '500',
        color: colors.textSecondary,
    },
    iconBtn: {
        width: 44,
        height: 44,
        alignItems: 'center',
        justifyContent: 'center',
    },
    searchBody: { flex: 1 },
    searchList: {
        paddingHorizontal: spacing.xl,
        paddingTop: spacing.lg,
        paddingBottom: spacing.xxxl,
    },
    searchHitRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 20,
    },
    searchHitTitle: {
        ...typography.body,
        fontSize: 15,
        fontWeight: '500',
        fontFamily: fonts.sansMedium,
    },
    searchHitMeta: {
        color: colors.textMuted,
        fontSize: 12,
        marginTop: 4,
        letterSpacing: 0.2,
    },
    divider: {
        height: StyleSheet.hairlineWidth,
        backgroundColor: colors.border,
    },
    emptySearch: {
        flex: 1,
        paddingHorizontal: spacing.xl,
        alignItems: 'center',
        justifyContent: 'center',
    },
    emptySearchText: {
        fontFamily: fonts.serif,
        fontSize: 17,
        color: colors.textPrimary,
        textAlign: 'center',
        lineHeight: 24,
    },
    emptySearchHint: {
        color: colors.textMuted,
        fontSize: 13,
        marginTop: spacing.sm,
        textAlign: 'center',
        lineHeight: 18,
    },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    scroll: {
        paddingHorizontal: spacing.xl,
        paddingTop: spacing.md,
        paddingBottom: spacing.xxxl,
    },
    section: {
        marginBottom: 40,
    },
    sectionHeader: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        paddingBottom: spacing.md,
    },
    sectionTitle: {
        fontFamily: fonts.serif,
        fontSize: 20,
        fontWeight: '400',
        color: colors.textPrimary,
        letterSpacing: -0.2,
        lineHeight: 28,
    },
    sectionDesc: {
        color: colors.textMuted,
        fontSize: 13,
        marginTop: 6,
        lineHeight: 18,
    },
    boardDivider: {
        height: StyleSheet.hairlineWidth,
        backgroundColor: colors.border,
    },
    boardRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 18,
        gap: spacing.md,
    },
    boardAccent: {
        width: 3,
        height: 28,
        borderRadius: 1.5,
        backgroundColor: colors.foreground,
        opacity: 0.15,
    },
    boardAccentPremium: {
        backgroundColor: colors.premium,
        opacity: 0.5,
    },
    boardMain: { flex: 1, paddingRight: spacing.md },
    boardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
    boardRowLocked: { opacity: 0.5 },
    boardName: {
        color: colors.foreground,
        fontSize: 16,
        fontWeight: '500',
        fontFamily: fonts.sansMedium,
        letterSpacing: -0.1,
    },
    boardNameLocked: { color: colors.textMuted },
    premiumBadgeText: {
        color: colors.textMuted,
        fontSize: 9,
        fontWeight: '600',
        letterSpacing: 1.2,
    },
    boardDesc: {
        color: colors.textMuted,
        fontSize: 13,
        marginTop: 4,
        lineHeight: 19,
    },
    meta: {
        color: colors.textMuted,
        fontSize: 9,
        marginTop: 6,
        letterSpacing: 1,
        textTransform: 'uppercase',
        fontWeight: '500',
    },
    readOnly: {
        color: colors.textMuted,
        fontSize: 9,
        fontWeight: '600',
        letterSpacing: 1.0,
        textTransform: 'uppercase',
    },
});
