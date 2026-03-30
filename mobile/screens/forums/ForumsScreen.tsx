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
            return (
                <View style={styles.contentWrap}>
                    <TouchableOpacity
                        style={[styles.channelRow, activeChannelId === channel.id && styles.channelRowActive]}
                        onPress={() => handleChannelPress(channel)}
                        activeOpacity={0.7}
                    >
                        <Text style={styles.channelHash} accessibilityLabel="Channel">
                            #
                        </Text>
                        <View style={styles.channelMain}>
                            <View style={styles.channelTitleLine}>
                                <Text style={styles.channelName} numberOfLines={1}>
                                    {channel.name}
                                </Text>
                                {channel.category ? (
                                    <Text style={styles.categoryInline} numberOfLines={1}>
                                        {' '}
                                        · {channel.category}
                                    </Text>
                                ) : null}
                                {isOfficial ? <Text style={styles.officialMark}> Official</Text> : null}
                            </View>
                            {channel.description ? (
                                <Text style={styles.channelTopic} numberOfLines={1}>
                                    {channel.description}
                                </Text>
                            ) : null}
                        </View>
                        <Text style={styles.channelStat}>{count}</Text>
                        <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
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
    header: { paddingBottom: spacing.sm },
    contentWrap: { width: '100%', maxWidth: 720, alignSelf: 'center', paddingHorizontal: spacing.lg },
    headerTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
    headerTitle: { fontSize: 26, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
    filterRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm, flexWrap: 'wrap' },
    segmentRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center' },
    filterPill: {
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: borderRadius.full,
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
    },
    filterPillActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    filterText: { fontSize: 12, fontWeight: '600', color: colors.textSecondary },
    filterTextActive: { color: colors.background },
    createButton: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.foreground, paddingHorizontal: 14, paddingVertical: 9, borderRadius: borderRadius.full, ...shadows.sm },
    createButtonText: { color: colors.background, fontSize: 13, fontWeight: '700' },
    filtersButton: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.card, paddingHorizontal: 12, paddingVertical: 8, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border },
    filtersButtonText: { fontSize: 12, fontWeight: '600', color: colors.textSecondary },
    searchContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        borderRadius: 12,
        paddingHorizontal: spacing.md,
        height: 44,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
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
    listContent: { paddingTop: spacing.sm },
    listContentEmpty: { flexGrow: 1 },
    section: { marginBottom: spacing.xl },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md },
    sectionAccent: { width: 4, height: 18, borderRadius: 2, backgroundColor: colors.foreground, marginRight: spacing.sm },
    sectionAccentOfficial: { backgroundColor: colors.info },
    sectionTitle: { fontSize: 13, fontWeight: '600', color: colors.textMuted, letterSpacing: 0.5 },
    channelRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        borderRadius: 8,
        paddingVertical: 10,
        paddingHorizontal: spacing.sm,
        marginBottom: 4,
        borderWidth: 1,
        borderColor: colors.border,
    },
    channelRowActive: {
        borderColor: colors.foreground,
        backgroundColor: colors.surface,
    },
    channelHash: { fontSize: 18, fontWeight: '700', color: colors.textMuted, width: 16, marginRight: 4 },
    channelMain: { flex: 1, minWidth: 0 },
    channelTitleLine: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' },
    channelName: { fontSize: 15, fontWeight: '700', color: colors.foreground },
    categoryInline: { fontSize: 11, color: colors.textMuted, fontWeight: '500' },
    officialMark: { fontSize: 10, fontWeight: '700', color: colors.info },
    channelTopic: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
    channelStat: { fontSize: 11, fontWeight: '600', color: colors.textMuted, marginRight: 4, minWidth: 28, textAlign: 'right' },
    empty: { alignItems: 'center', marginTop: 48 },
    emptyIconWrap: {
        width: 88,
        height: 88,
        borderRadius: 44,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: spacing.lg,
    },
    emptyTitle: { fontSize: 18, fontWeight: '600', color: colors.foreground, marginBottom: 4 },
    emptySubtitle: { fontSize: 14, color: colors.textMuted },
    modalOverlay: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', padding: spacing.lg },
    modalCard: { backgroundColor: colors.card, borderRadius: borderRadius['2xl'], padding: spacing.xl, ...shadows.lg, width: '100%', maxWidth: 420, alignSelf: 'center' },
    modalTitle: { ...typography.h3, marginBottom: spacing.xs },
    modalSubtitle: { ...typography.bodySmall, color: colors.textMuted, marginBottom: spacing.md },
    modalInput: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, color: colors.foreground, marginBottom: spacing.sm },
    modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.md, marginTop: spacing.md },
    modalBtn: { padding: spacing.sm },
    modalBtnText: { color: colors.textMuted, fontWeight: '600' },
    modalPrimary: { backgroundColor: colors.foreground, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: borderRadius.full },
    modalPrimaryText: { color: colors.background, fontWeight: '600' },
    modalSection: { marginTop: spacing.md },
    modalSectionTitle: { fontSize: 12, color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: spacing.sm, fontWeight: '600' },
    modalChipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    modalChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: borderRadius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
    modalChipActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    modalChipText: { fontSize: 12, color: colors.textSecondary, fontWeight: '600' },
    modalChipTextActive: { color: colors.background },
});
