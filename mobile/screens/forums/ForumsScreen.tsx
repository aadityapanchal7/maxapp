import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Modal } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { useNavigation } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useChannelsQuery } from '../../hooks/useAppQueries';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

type ForumChannel = {
    id: string;
    name: string;
    description?: string;
    category?: string;
    tags?: string[];
    message_count?: number;
    is_admin_only?: boolean;
    created_by?: string;
    created_at?: string;
};

export default function ForumsScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const { user } = useAuth() as any;
    const [searchQuery, setSearchQuery] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [activeChannelId, setActiveChannelId] = useState<string | null>(null);
    const [page, setPage] = useState<'official' | 'community'>('community');
    const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [onlyWithPosts, setOnlyWithPosts] = useState(false);
    const [onlyMine, setOnlyMine] = useState(false);
    const [sortMode, setSortMode] = useState<'new' | 'top'>('new');
    const [createVisible, setCreateVisible] = useState(false);
    const [filtersVisible, setFiltersVisible] = useState(false);
    const [newName, setNewName] = useState('');
    const [newDescription, setNewDescription] = useState('');
    const [newCategory, setNewCategory] = useState('general');
    const [newTags, setNewTags] = useState('');

    useEffect(() => {
        const q = searchQuery.trim();
        const delayMs = q.length > 0 ? 450 : 0;
        const t = setTimeout(() => setDebouncedSearch(q), delayMs);
        return () => clearTimeout(t);
    }, [searchQuery]);

    const channelsQuery = useChannelsQuery(debouncedSearch);
    const forums = useMemo(() => channelsQuery.data ?? [], [channelsQuery.data]);
    const loading = channelsQuery.isPending && forums.length === 0;

    useEffect(() => {
        if (forums.length === 0 || !channelsQuery.isSuccess) return;
        setActiveChannelId((prev) => prev ?? forums[0].id);
    }, [channelsQuery.isSuccess, forums]);

    const handleChannelPress = useCallback(
        (item: { id: string; name: string; is_admin_only?: boolean }) => {
            setActiveChannelId(item.id);
            navigation.navigate('ChannelChat', {
                channelId: item.id,
                channelName: item.name,
                isAdminOnly: item.is_admin_only,
            });
        },
        [navigation],
    );

    const renderChannel = useCallback(
        ({ item: channel }: { item: any }) => {
            const isOfficial = channel.is_admin_only;
            const count = channel.message_count || 0;
            const tags = (channel.tags || []).slice(0, 2);
            return (
                <View style={styles.contentWrap}>
                    <TouchableOpacity
                        style={[styles.channelRow, activeChannelId === channel.id && styles.channelRowActive]}
                        onPress={() => handleChannelPress(channel)}
                        activeOpacity={0.72}
                    >
                        <View style={[styles.channelIconWrap, isOfficial ? styles.channelIconOfficial : styles.channelIconCommunity]}>
                            <Ionicons
                                name={isOfficial ? 'megaphone-outline' : 'chatbubbles-outline'}
                                size={22}
                                color={isOfficial ? colors.info : colors.textSecondary}
                            />
                        </View>
                        <View style={styles.channelMain}>
                            <Text style={styles.channelName} numberOfLines={2}>
                                {channel.name}
                            </Text>
                            {channel.description ? (
                                <Text style={styles.channelTopic} numberOfLines={2}>
                                    {channel.description}
                                </Text>
                            ) : null}
                            <View style={styles.channelMetaRow}>
                                {channel.category ? (
                                    <View style={styles.metaPill}>
                                        <Text style={styles.metaPillText}>{channel.category}</Text>
                                    </View>
                                ) : null}
                                {isOfficial ? (
                                    <View style={styles.officialPill}>
                                        <Text style={styles.officialPillText}>Official</Text>
                                    </View>
                                ) : null}
                                {tags.map((t: string) => (
                                    <View key={t} style={styles.tagPill}>
                                        <Text style={styles.tagPillText}>#{t}</Text>
                                    </View>
                                ))}
                            </View>
                        </View>
                        <View style={styles.channelRight}>
                            <View style={styles.statBlock}>
                                <Text style={styles.statNumber}>{count > 999 ? '999+' : count}</Text>
                                <Text style={styles.statLabel}>{count === 1 ? 'post' : 'posts'}</Text>
                            </View>
                            <Ionicons name="chevron-forward" size={18} color={colors.border} />
                        </View>
                    </TouchableOpacity>
                </View>
            );
        },
        [activeChannelId, handleChannelPress],
    );

    const categoryOptions = useMemo(() => {
        const set = new Set<string>();
        forums.forEach((f: ForumChannel) => { if (f.category) set.add(f.category.toLowerCase()); });
        return Array.from(set);
    }, [forums]);

    const tagOptions = useMemo(() => {
        const set = new Set<string>();
        forums.forEach((f: ForumChannel) => { (f.tags || []).forEach((t: string) => set.add(t)); });
        return Array.from(set);
    }, [forums]);

    const toggleItem = (list: string[], value: string) => {
        if (list.includes(value)) return list.filter((v) => v !== value);
        return [...list, value];
    };

    const filteredForums = useMemo(() => {
        const official = forums.filter((f: ForumChannel) => f.is_admin_only || f.name.toLowerCase().includes('announce') || f.name.toLowerCase().includes('welcome'));
        const community = forums.filter((f: ForumChannel) => !official.some((o: ForumChannel) => o.id === f.id));
        const base = page === 'official' ? official : community;
        let filtered = base;
        if (selectedCategories.length > 0) {
            filtered = filtered.filter((f: ForumChannel) => selectedCategories.includes((f.category || '').toLowerCase()));
        }
        if (selectedTags.length > 0) {
            filtered = filtered.filter((f: ForumChannel) => (f.tags || []).some((t: string) => selectedTags.includes(t)));
        }
        if (onlyWithPosts) {
            filtered = filtered.filter((f: ForumChannel) => (f.message_count || 0) > 0);
        }
        if (onlyMine && user?.id) {
            filtered = filtered.filter((f: ForumChannel) => f.created_by === user.id);
        }
        if (sortMode === 'top') {
            return [...filtered].sort((a, b) => (b.message_count || 0) - (a.message_count || 0));
        }
        return [...filtered].sort((a, b) => {
            const at = a.created_at ? new Date(a.created_at).getTime() : 0;
            const bt = b.created_at ? new Date(b.created_at).getTime() : 0;
            if (at !== bt) return bt - at;
            return (a.name || '').localeCompare(b.name || '');
        });
    }, [forums, page, selectedCategories, selectedTags, onlyWithPosts, onlyMine, sortMode, user?.id]);

    const clearFilters = () => {
        setSelectedCategories([]);
        setSelectedTags([]);
        setOnlyWithPosts(false);
        setOnlyMine(false);
    };

    const handleCreateForum = async () => {
        const tags = newTags.split(',').map(t => t.trim()).filter(Boolean);
        if (!newName.trim()) return;
        try {
            await api.createForum({
                name: newName.trim(),
                description: newDescription.trim(),
                category: newCategory.trim() || 'general',
                tags,
                is_admin_only: false,
            });
            setCreateVisible(false);
            setNewName('');
            setNewDescription('');
            setNewTags('');
            setNewCategory('general');
            await queryClient.invalidateQueries({ queryKey: ['channels'] });
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <View style={styles.contentWrap}>
                <View style={styles.headerTopRow}>
                    <Text style={styles.headerTitle}>Forums</Text>
                    {page === 'community' && (
                        <TouchableOpacity style={styles.createButton} onPress={() => setCreateVisible(true)} activeOpacity={0.7}>
                            <Ionicons name="add" size={16} color={colors.background} />
                            <Text style={styles.createButtonText}>Create</Text>
                        </TouchableOpacity>
                    )}
                </View>
                <View style={styles.filterRow}>
                    <View style={styles.segmentRow}>
                        {(['community', 'official'] as const).map((key) => (
                            <TouchableOpacity
                                key={key}
                                style={[styles.filterPill, page === key && styles.filterPillActive]}
                                onPress={() => setPage(key)}
                                activeOpacity={0.7}
                            >
                                <Text style={[styles.filterText, page === key && styles.filterTextActive]}>
                                    {key === 'community' ? 'Community' : 'Official'}
                                </Text>
                            </TouchableOpacity>
                        ))}
                    </View>
                    <TouchableOpacity style={styles.filtersButton} onPress={() => setFiltersVisible(true)} activeOpacity={0.7}>
                        <Ionicons name="options-outline" size={16} color={colors.textSecondary} />
                        <Text style={styles.filtersButtonText}>Filters</Text>
                    </TouchableOpacity>
                </View>
                <View style={styles.searchContainer}>
                    <Ionicons name="search" size={18} color={colors.textMuted} style={styles.searchIcon} />
                    <TextInput
                        style={styles.searchInput}
                        placeholder="Search forums..."
                        placeholderTextColor={colors.textMuted}
                        value={searchQuery}
                        onChangeText={setSearchQuery}
                    />
                    {searchQuery !== '' && (
                        <TouchableOpacity onPress={() => setSearchQuery('')} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                            <Ionicons name="close-circle" size={18} color={colors.textMuted} />
                        </TouchableOpacity>
                    )}
                </View>
                {(selectedCategories.length > 0 || selectedTags.length > 0 || onlyWithPosts || (onlyMine && user?.id)) && (
                    <View style={styles.activeFiltersRow}>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                            {selectedCategories.map((cat) => (
                                <View key={`cat-${cat}`} style={styles.activeFilterChip}>
                                    <Text style={styles.activeFilterText}>{cat}</Text>
                                    <TouchableOpacity onPress={() => setSelectedCategories(prev => prev.filter((c) => c !== cat))}>
                                        <Ionicons name="close" size={14} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                            ))}
                            {selectedTags.map((tag) => (
                                <View key={`tag-${tag}`} style={styles.activeFilterChip}>
                                    <Text style={styles.activeFilterText}>#{tag}</Text>
                                    <TouchableOpacity onPress={() => setSelectedTags(prev => prev.filter((t) => t !== tag))}>
                                        <Ionicons name="close" size={14} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                            ))}
                            {onlyWithPosts && (
                                <View style={styles.activeFilterChip}>
                                    <Text style={styles.activeFilterText}>With posts</Text>
                                    <TouchableOpacity onPress={() => setOnlyWithPosts(false)}>
                                        <Ionicons name="close" size={14} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                            )}
                            {onlyMine && user?.id && (
                                <View style={styles.activeFilterChip}>
                                    <Text style={styles.activeFilterText}>Created by me</Text>
                                    <TouchableOpacity onPress={() => setOnlyMine(false)}>
                                        <Ionicons name="close" size={14} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                            )}
                        </ScrollView>
                        <TouchableOpacity onPress={clearFilters} style={styles.clearFiltersBtn}>
                            <Text style={styles.clearFiltersText}>Clear</Text>
                        </TouchableOpacity>
                    </View>
                )}
                </View>
            </View>

            {loading && forums.length === 0 ? (
                <View style={styles.center}><ActivityIndicator size="large" color={colors.foreground} /></View>
            ) : (
                <FlashList
                    style={styles.list}
                    data={filteredForums}
                    keyExtractor={(item) => item.id}
                    showsVerticalScrollIndicator={false}
                    contentContainerStyle={[
                        styles.listContent,
                        { paddingBottom: insets.bottom + 24 },
                        filteredForums.length === 0 && styles.listContentEmpty,
                    ]}
                    renderItem={renderChannel}
                    ListEmptyComponent={
                        <View style={[styles.contentWrap, styles.empty]}>
                            <View style={styles.emptyIconWrap}>
                                <Ionicons name="chatbubbles-outline" size={48} color={colors.textMuted} />
                            </View>
                            <Text style={styles.emptyTitle}>No channels found</Text>
                            <Text style={styles.emptySubtitle}>
                                {searchQuery ? 'Try a different search' : 'Channels will appear here'}
                            </Text>
                        </View>
                    }
                />
            )}

            <Modal animationType="fade" transparent visible={createVisible} onRequestClose={() => setCreateVisible(false)}>
                <View style={styles.modalOverlay}>
                    <View style={styles.modalCard}>
                        <Text style={styles.modalTitle}>Create Community Forum</Text>
                        <Text style={styles.modalSubtitle}>Start a new discussion for the community.</Text>
                        <TextInput style={styles.modalInput} placeholder="Forum name" placeholderTextColor={colors.textMuted} value={newName} onChangeText={setNewName} />
                        <TextInput style={styles.modalInput} placeholder="Description" placeholderTextColor={colors.textMuted} value={newDescription} onChangeText={setNewDescription} />
                        <TextInput style={styles.modalInput} placeholder="Category (skinmax, heightmax, etc.)" placeholderTextColor={colors.textMuted} value={newCategory} onChangeText={setNewCategory} />
                        <TextInput style={styles.modalInput} placeholder="Tags (comma separated)" placeholderTextColor={colors.textMuted} value={newTags} onChangeText={setNewTags} />
                        <View style={styles.modalActions}>
                            <TouchableOpacity onPress={() => setCreateVisible(false)} style={styles.modalBtn}><Text style={styles.modalBtnText}>Cancel</Text></TouchableOpacity>
                            <TouchableOpacity onPress={handleCreateForum} style={styles.modalPrimary}><Text style={styles.modalPrimaryText}>Create</Text></TouchableOpacity>
                        </View>
                    </View>
                </View>
            </Modal>
            <Modal animationType="fade" transparent visible={filtersVisible} onRequestClose={() => setFiltersVisible(false)}>
                <View style={styles.modalOverlay}>
                    <View style={styles.modalCard}>
                        <Text style={styles.modalTitle}>Filters</Text>
                        <Text style={styles.modalSubtitle}>Refine what you see.</Text>
                        <View style={styles.modalSection}>
                            <Text style={styles.modalSectionTitle}>Sort</Text>
                            <View style={styles.modalChipRow}>
                                {(['new', 'top'] as const).map((key) => (
                                    <TouchableOpacity
                                        key={key}
                                        style={[styles.modalChip, sortMode === key && styles.modalChipActive]}
                                        onPress={() => setSortMode(key)}
                                        activeOpacity={0.7}
                                    >
                                        <Text style={[styles.modalChipText, sortMode === key && styles.modalChipTextActive]}>
                                            {key === 'new' ? 'New' : 'Top'}
                                        </Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        </View>
                        <View style={styles.modalSection}>
                            <Text style={styles.modalSectionTitle}>Categories</Text>
                            <View style={styles.modalChipRow}>
                                {categoryOptions.map((cat) => (
                                    <TouchableOpacity
                                        key={cat}
                                        style={[styles.modalChip, selectedCategories.includes(cat.toLowerCase()) && styles.modalChipActive]}
                                        onPress={() => setSelectedCategories((prev) => toggleItem(prev, cat.toLowerCase()))}
                                        activeOpacity={0.7}
                                    >
                                        <Text style={[styles.modalChipText, selectedCategories.includes(cat.toLowerCase()) && styles.modalChipTextActive]}>
                                            {cat}
                                        </Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        </View>
                        <View style={styles.modalSection}>
                            <Text style={styles.modalSectionTitle}>Tags</Text>
                            <View style={styles.modalChipRow}>
                                {tagOptions.map((tag) => (
                                    <TouchableOpacity
                                        key={tag}
                                        style={[styles.modalChip, selectedTags.includes(tag) && styles.modalChipActive]}
                                        onPress={() => setSelectedTags((prev) => toggleItem(prev, tag))}
                                        activeOpacity={0.7}
                                    >
                                        <Text style={[styles.modalChipText, selectedTags.includes(tag) && styles.modalChipTextActive]}>
                                            #{tag}
                                        </Text>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        </View>
                        <View style={styles.modalSection}>
                            <Text style={styles.modalSectionTitle}>Extras</Text>
                            <View style={styles.modalChipRow}>
                                <TouchableOpacity
                                    style={[styles.modalChip, onlyWithPosts && styles.modalChipActive]}
                                    onPress={() => setOnlyWithPosts((prev) => !prev)}
                                    activeOpacity={0.7}
                                >
                                    <Text style={[styles.modalChipText, onlyWithPosts && styles.modalChipTextActive]}>
                                        With posts
                                    </Text>
                                </TouchableOpacity>
                                {user?.id && (
                                    <TouchableOpacity
                                        style={[styles.modalChip, onlyMine && styles.modalChipActive]}
                                        onPress={() => setOnlyMine((prev) => !prev)}
                                        activeOpacity={0.7}
                                    >
                                        <Text style={[styles.modalChipText, onlyMine && styles.modalChipTextActive]}>
                                            Created by me
                                        </Text>
                                    </TouchableOpacity>
                                )}
                            </View>
                        </View>
                        <View style={styles.modalActions}>
                            <TouchableOpacity onPress={clearFilters} style={styles.modalBtn}><Text style={styles.modalBtnText}>Clear all</Text></TouchableOpacity>
                            <TouchableOpacity onPress={() => setFiltersVisible(false)} style={styles.modalPrimary}><Text style={styles.modalPrimaryText}>Done</Text></TouchableOpacity>
                        </View>
                    </View>
                </View>
            </Modal>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { paddingBottom: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderLight },
    contentWrap: { width: '100%', maxWidth: 720, alignSelf: 'center', paddingHorizontal: spacing.lg },
    headerTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md },
    headerTitle: { fontSize: 28, fontWeight: '700', color: colors.foreground, letterSpacing: -0.8 },
    filterRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.md, flexWrap: 'wrap' },
    segmentRow: { flexDirection: 'row', gap: 4, alignItems: 'center', backgroundColor: colors.surface, padding: 3, borderRadius: borderRadius.full },
    filterPill: {
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderRadius: borderRadius.full,
        backgroundColor: 'transparent',
    },
    filterPillActive: { backgroundColor: colors.card, ...shadows.sm },
    filterText: { fontSize: 13, fontWeight: '600', color: colors.textMuted },
    filterTextActive: { color: colors.foreground },
    createButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        backgroundColor: colors.foreground,
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderRadius: borderRadius.lg,
    },
    createButtonText: { color: colors.background, fontSize: 13, fontWeight: '700' },
    filtersButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        backgroundColor: colors.surface,
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderRadius: borderRadius.full,
    },
    filtersButtonText: { fontSize: 13, fontWeight: '600', color: colors.textSecondary },
    searchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: 14,
        paddingHorizontal: spacing.md,
        height: 46,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
    },
    searchIcon: { marginRight: spacing.sm },
    searchInput: { flex: 1, color: colors.textPrimary, fontSize: 15 },
    activeFiltersRow: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.sm, gap: spacing.sm },
    activeFilterChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: borderRadius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, marginRight: spacing.sm },
    activeFilterText: { fontSize: 11, color: colors.textSecondary, fontWeight: '600' },
    clearFiltersBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: borderRadius.full, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    clearFiltersText: { fontSize: 11, fontWeight: '600', color: colors.textMuted },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    list: { flex: 1 },
    listContent: { paddingTop: spacing.md, paddingHorizontal: 0 },
    listContentEmpty: { flexGrow: 1 },
    section: { marginBottom: spacing.xl },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md },
    sectionAccent: { width: 4, height: 18, borderRadius: 2, backgroundColor: colors.foreground, marginRight: spacing.sm },
    sectionAccentOfficial: { backgroundColor: colors.info },
    sectionTitle: { fontSize: 13, fontWeight: '600', color: colors.textMuted, letterSpacing: 0.5 },
    channelRow: {
        flexDirection: 'row',
        alignItems: 'stretch',
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        marginBottom: 12,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: 'transparent',
        ...shadows.sm,
    },
    channelRowActive: {
        borderColor: colors.foreground,
        backgroundColor: colors.card,
    },
    channelIconWrap: {
        width: 48,
        height: 48,
        borderRadius: borderRadius.lg,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: spacing.md,
        alignSelf: 'center',
    },
    channelIconOfficial: {
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
    },
    channelIconCommunity: {
        backgroundColor: colors.surface,
    },
    channelMain: { flex: 1, minWidth: 0, justifyContent: 'center' },
    channelName: {
        fontSize: 17,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: -0.35,
        lineHeight: 22,
    },
    channelMetaRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 6,
        marginTop: 8,
    },
    metaPill: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
    },
    metaPillText: {
        fontSize: 11,
        fontWeight: '600',
        color: colors.textSecondary,
        textTransform: 'capitalize',
    },
    officialPill: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: borderRadius.full,
        backgroundColor: 'rgba(59, 130, 246, 0.12)',
    },
    officialPillText: {
        fontSize: 11,
        fontWeight: '700',
        color: colors.info,
    },
    tagPill: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: borderRadius.full,
        backgroundColor: colors.accentMuted,
    },
    tagPillText: {
        fontSize: 11,
        fontWeight: '600',
        color: colors.textSecondary,
    },
    channelTopic: {
        fontSize: 13,
        color: colors.textSecondary,
        marginTop: 4,
        lineHeight: 18,
        fontWeight: '400',
    },
    channelRight: {
        flexDirection: 'row',
        alignItems: 'center',
        marginLeft: spacing.sm,
        gap: 4,
    },
    statBlock: {
        alignItems: 'flex-end',
        minWidth: 40,
    },
    statNumber: {
        fontSize: 16,
        fontWeight: '700',
        color: colors.foreground,
        letterSpacing: -0.4,
    },
    statLabel: {
        fontSize: 10,
        fontWeight: '600',
        color: colors.textMuted,
        marginTop: 1,
        textTransform: 'uppercase',
        letterSpacing: 0.4,
    },
    empty: { alignItems: 'center', marginTop: 48 },
    emptyIconWrap: {
        width: 80,
        height: 80,
        borderRadius: 40,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: spacing.lg,
    },
    emptyTitle: { fontSize: 18, fontWeight: '600', color: colors.foreground, marginBottom: 4 },
    emptySubtitle: { fontSize: 14, color: colors.textMuted },
    modalOverlay: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', padding: spacing.lg },
    modalCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        width: '100%',
        maxWidth: 420,
        alignSelf: 'center',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
        ...shadows.lg,
    },
    modalTitle: { ...typography.h3, marginBottom: spacing.xs, letterSpacing: -0.4 },
    modalSubtitle: { ...typography.bodySmall, color: colors.textSecondary, marginBottom: spacing.lg, lineHeight: 20 },
    modalInput: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        paddingVertical: 14,
        paddingHorizontal: spacing.md,
        color: colors.foreground,
        marginBottom: spacing.sm,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
        fontSize: 15,
    },
    modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.md, marginTop: spacing.md },
    modalBtn: { padding: spacing.sm },
    modalBtnText: { color: colors.textMuted, fontWeight: '600' },
    modalPrimary: { backgroundColor: colors.foreground, paddingHorizontal: spacing.lg, paddingVertical: 12, borderRadius: borderRadius.full },
    modalPrimaryText: { color: colors.background, fontWeight: '600' },
    modalSection: { marginTop: spacing.md },
    modalSectionTitle: { fontSize: 11, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.sm, fontWeight: '700' },
    modalChipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    modalChip: {
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
    },
    modalChipActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    modalChipText: { fontSize: 12, color: colors.textSecondary, fontWeight: '600' },
    modalChipTextActive: { color: colors.background },
});
