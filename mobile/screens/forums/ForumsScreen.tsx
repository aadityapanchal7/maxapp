import React, { useState, useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Modal } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function ForumsScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const [forums, setForums] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [activeChannelId, setActiveChannelId] = useState<string | null>(null);
    const [page, setPage] = useState<'official' | 'community'>('community');
    const [categoryFilter, setCategoryFilter] = useState<string>('all');
    const [sortMode, setSortMode] = useState<'new' | 'top'>('new');
    const [createVisible, setCreateVisible] = useState(false);
    const [newName, setNewName] = useState('');
    const [newDescription, setNewDescription] = useState('');
    const [newCategory, setNewCategory] = useState('general');
    const [newTags, setNewTags] = useState('');

    useFocusEffect(React.useCallback(() => { loadForums(); }, [searchQuery]));

    const loadForums = async () => {
        try { setLoading(true); const { forums: data } = await api.getChannels(searchQuery); setForums(data || []); if (data?.length > 0 && !activeChannelId) setActiveChannelId(data[0].id); }
        catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const handleChannelPress = (item: any) => {
        setActiveChannelId(item.id);
        navigation.navigate('ChannelChat', { channelId: item.id, channelName: item.name, isAdminOnly: item.is_admin_only });
    };

    const categoryOptions = useMemo(() => {
        const set = new Set<string>();
        forums.forEach((f) => { if (f.category) set.add(f.category); });
        return ['all', ...Array.from(set)];
    }, [forums]);

    const filteredForums = useMemo(() => {
        const official = forums.filter((f) => f.is_admin_only || f.name.toLowerCase().includes('announce') || f.name.toLowerCase().includes('welcome'));
        const community = forums.filter((f) => !official.some((o: any) => o.id === f.id));
        const base = page === 'official' ? official : community;
        const filtered = categoryFilter === 'all' ? base : base.filter((f) => (f.category || '').toLowerCase() === categoryFilter.toLowerCase());
        if (sortMode === 'top') {
            return [...filtered].sort((a, b) => (b.message_count || 0) - (a.message_count || 0));
        }
        return [...filtered].sort((a, b) => (a.name || '').localeCompare(b.name || ''));
    }, [forums, page, categoryFilter, sortMode]);

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
            loadForums();
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <View style={[styles.container, { paddingTop: insets.top }]}>
            <View style={styles.header}>
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
                    <View style={styles.sortRow}>
                    {(['new', 'top'] as const).map((key) => (
                        <TouchableOpacity
                            key={key}
                            style={[styles.sortPill, sortMode === key && styles.sortPillActive]}
                            onPress={() => setSortMode(key)}
                            activeOpacity={0.7}
                        >
                            <Ionicons name={key === 'new' ? 'time-outline' : 'flame-outline'} size={14} color={sortMode === key ? colors.background : colors.textSecondary} />
                            <Text style={[styles.sortText, sortMode === key && styles.sortTextActive]}>
                                {key === 'new' ? 'New' : 'Top'}
                            </Text>
                        </TouchableOpacity>
                    ))}
                    </View>
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
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.categoryRow}>
                    {categoryOptions.map((cat) => (
                        <TouchableOpacity
                            key={cat}
                            style={[styles.categoryPill, categoryFilter === cat && styles.categoryPillActive]}
                            onPress={() => setCategoryFilter(cat)}
                            activeOpacity={0.7}
                        >
                            <Text style={[styles.categoryText, categoryFilter === cat && styles.categoryTextActive]}>
                                {cat === 'all' ? 'All categories' : cat}
                            </Text>
                        </TouchableOpacity>
                    ))}
                </ScrollView>
            </View>

            {loading && forums.length === 0 ? (
                <View style={styles.center}><ActivityIndicator size="large" color={colors.foreground} /></View>
            ) : (
                <ScrollView style={styles.list} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}>
                    {filteredForums.map(channel => {
                        const isOfficial = channel.is_admin_only;
                        return (
                            <TouchableOpacity
                                key={channel.id}
                                style={[styles.card, activeChannelId === channel.id && styles.cardActive]}
                                onPress={() => handleChannelPress(channel)}
                                activeOpacity={0.7}
                            >
                                <View style={styles.voteCol}>
                                    <Ionicons name="arrow-up" size={18} color={colors.textMuted} />
                                    <Text style={styles.voteCount}>{channel.message_count || 0}</Text>
                                    <Ionicons name="arrow-down" size={18} color={colors.textMuted} />
                                </View>
                                <View style={[styles.iconWrap, isOfficial && styles.iconWrapOfficial]}>
                                    <Ionicons name="chatbubble-ellipses" size={20} color={isOfficial ? colors.info : colors.textSecondary} />
                                </View>
                                <View style={styles.info}>
                                    <View style={styles.titleRow}>
                                        <Text style={styles.channelName} numberOfLines={1}>r/{channel.slug || channel.name}</Text>
                                        {channel.category && <Text style={styles.categoryBadge}>{channel.category}</Text>}
                                    </View>
                                    <Text style={styles.channelDesc} numberOfLines={2}>{channel.description || 'No description'}</Text>
                                    {!!channel.tags?.length && (
                                        <View style={styles.tagRow}>
                                            {channel.tags.slice(0, 3).map((tag: string) => (
                                                <View key={tag} style={styles.tagPill}><Text style={styles.tagText}>{tag}</Text></View>
                                            ))}
                                        </View>
                                    )}
                                </View>
                                <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                            </TouchableOpacity>
                        );
                    })}
                    {filteredForums.length === 0 && (
                        <View style={styles.empty}>
                            <View style={styles.emptyIconWrap}>
                                <Ionicons name="chatbubbles-outline" size={48} color={colors.textMuted} />
                            </View>
                            <Text style={styles.emptyTitle}>No channels found</Text>
                            <Text style={styles.emptySubtitle}>{searchQuery ? 'Try a different search' : 'Channels will appear here'}</Text>
                        </View>
                    )}
                </ScrollView>
            )}

            <Modal animationType="fade" transparent visible={createVisible} onRequestClose={() => setCreateVisible(false)}>
                <View style={styles.modalOverlay}>
                    <View style={styles.modalCard}>
                        <Text style={styles.modalTitle}>Create Community Forum</Text>
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
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
    headerTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
    headerTitle: { fontSize: 26, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
    filterRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm, flexWrap: 'wrap' },
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
    createButton: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.foreground, paddingHorizontal: 10, paddingVertical: 6, borderRadius: borderRadius.full },
    createButtonText: { color: colors.background, fontSize: 12, fontWeight: '600' },
    sortRow: { flexDirection: 'row', gap: spacing.sm },
    sortPill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: borderRadius.full, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    sortPillActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    sortText: { fontSize: 12, color: colors.textSecondary, fontWeight: '600' },
    sortTextActive: { color: colors.background },
    categoryRow: { marginTop: spacing.sm, marginBottom: spacing.sm },
    categoryPill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: borderRadius.full, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, marginRight: spacing.sm },
    categoryPillActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    categoryText: { fontSize: 12, color: colors.textSecondary, fontWeight: '600' },
    categoryTextActive: { color: colors.background },
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
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    list: { flex: 1, paddingHorizontal: spacing.lg },
    section: { marginBottom: spacing.xl },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md },
    sectionAccent: { width: 4, height: 18, borderRadius: 2, backgroundColor: colors.foreground, marginRight: spacing.sm },
    sectionAccentOfficial: { backgroundColor: colors.info },
    sectionTitle: { fontSize: 13, fontWeight: '600', color: colors.textMuted, letterSpacing: 0.5 },
    card: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        borderRadius: 12,
        padding: spacing.md,
        marginBottom: spacing.sm,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
    },
    cardActive: {
        borderColor: colors.foreground,
        ...shadows.md,
    },
    voteCol: { alignItems: 'center', marginRight: spacing.sm },
    voteCount: { fontSize: 12, color: colors.textSecondary, marginVertical: 2, fontWeight: '600' },
    iconWrap: {
        width: 44,
        height: 44,
        borderRadius: 12,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
        marginRight: spacing.md,
    },
    iconWrapOfficial: { backgroundColor: colors.accentMuted },
    info: { flex: 1, minWidth: 0 },
    titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    channelName: { fontSize: 15, fontWeight: '700', color: colors.foreground },
    categoryBadge: { fontSize: 11, color: colors.textMuted, backgroundColor: colors.surface, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
    channelDesc: { fontSize: 13, color: colors.textMuted, marginTop: 2, lineHeight: 18 },
    tagRow: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.sm },
    tagPill: { backgroundColor: colors.surface, borderRadius: borderRadius.full, paddingHorizontal: 8, paddingVertical: 2, borderWidth: 1, borderColor: colors.border },
    tagText: { fontSize: 10, color: colors.textMuted, fontWeight: '600' },
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
    modalCard: { backgroundColor: colors.card, borderRadius: borderRadius['2xl'], padding: spacing.xl, ...shadows.lg },
    modalTitle: { ...typography.h3, marginBottom: spacing.md },
    modalInput: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, color: colors.foreground, marginBottom: spacing.sm },
    modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.md, marginTop: spacing.md },
    modalBtn: { padding: spacing.sm },
    modalBtnText: { color: colors.textMuted, fontWeight: '600' },
    modalPrimary: { backgroundColor: colors.foreground, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: borderRadius.full },
    modalPrimaryText: { color: colors.background, fontWeight: '600' },
});
