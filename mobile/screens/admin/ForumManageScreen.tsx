import React, { useCallback, useEffect, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    TouchableOpacity,
    ActivityIndicator,
    Alert,
    Modal,
    TextInput,
    Switch,
    RefreshControl,
    KeyboardAvoidingView,
    Platform,
    Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import api from '../../services/api';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

type SubforumRow = {
    id: string;
    category_id: string;
    name: string;
    slug: string;
    description?: string | null;
    order: number;
    access_tier: string;
    is_read_only: boolean;
    thread_count: number;
};

type CategoryRow = {
    id: string;
    name: string;
    slug: string;
    description?: string | null;
    order: number;
    subforums: SubforumRow[];
};

function formatApiDetail(e: any): string {
    const d = e?.response?.data?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
        return d
            .map((x: any) => {
                if (typeof x?.msg === 'string') return x.msg;
                if (typeof x?.message === 'string') return x.message;
                return JSON.stringify(x);
            })
            .join('\n');
    }
    if (d && typeof d === 'object' && typeof (d as any).msg === 'string') return (d as any).msg;
    return e?.message || 'Save failed';
}

const MODAL_BODY_MAX_H = Math.min(440, Math.round(Dimensions.get('window').height * 0.52));

export default function ForumManageScreen() {
    const navigation = useNavigation<any>();
    const [v2Categories, setV2Categories] = useState<CategoryRow[]>([]);
    const [legacyChannels, setLegacyChannels] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [expanded, setExpanded] = useState<Record<string, boolean>>({});

    const [modal, setModal] = useState<
        'none' | 'cat_new' | 'cat_edit' | 'sub_new' | 'sub_edit'
    >('none');
    const [catName, setCatName] = useState('');
    const [catDesc, setCatDesc] = useState('');
    const [catOrder, setCatOrder] = useState('0');
    const [editCatId, setEditCatId] = useState<string | null>(null);

    const [subCatId, setSubCatId] = useState<string | null>(null);
    const [subName, setSubName] = useState('');
    const [subDesc, setSubDesc] = useState('');
    const [subOrder, setSubOrder] = useState('');
    const [subPremium, setSubPremium] = useState(false);
    const [subReadOnly, setSubReadOnly] = useState(false);
    const [editSubId, setEditSubId] = useState<string | null>(null);

    const loadAll = useCallback(async () => {
        try {
            const [ov, ch] = await Promise.all([api.getAdminForumsV2Overview(), api.getChannels()]);
            setV2Categories(ov.categories || []);
            setLegacyChannels(ch.forums || []);
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not load forums.');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useEffect(() => {
        void loadAll();
    }, [loadAll]);

    const onRefresh = () => {
        setRefreshing(true);
        void loadAll();
    };

    const toggleExpand = (id: string) => {
        setExpanded((p) => ({ ...p, [id]: !p[id] }));
    };

    const openNewCategory = () => {
        setCatName('');
        setCatDesc('');
        setCatOrder('0');
        setEditCatId(null);
        setModal('cat_new');
    };

    const openEditCategory = (c: CategoryRow) => {
        setEditCatId(c.id);
        setCatName(c.name);
        setCatDesc(c.description || '');
        setCatOrder(String(c.order ?? 0));
        setModal('cat_edit');
    };

    const saveCategory = async () => {
        const name = catName.trim();
        if (!name) {
            Alert.alert('Name required');
            return;
        }
        const order = parseInt(catOrder, 10);
        try {
            if (modal === 'cat_new') {
                await api.createAdminForumCategory({
                    name,
                    description: catDesc.trim(),
                    order: Number.isNaN(order) ? 0 : order,
                });
            } else if (editCatId) {
                await api.updateAdminForumCategory(editCatId, {
                    name,
                    description: catDesc.trim(),
                    order: Number.isNaN(order) ? 0 : order,
                });
            }
            setModal('none');
            await loadAll();
        } catch (e: any) {
            Alert.alert('Error', formatApiDetail(e));
        }
    };

    const deleteCategory = (c: CategoryRow) => {
        const n = c.subforums?.length || 0;
        Alert.alert(
            'Delete category',
            n > 0
                ? `"${c.name}" has ${n} board(s). Deleting removes all boards, threads, and posts under them.`
                : `Delete "${c.name}"?`,
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Delete',
                    style: 'destructive',
                    onPress: async () => {
                        try {
                            await api.deleteAdminForumCategory(c.id);
                            await loadAll();
                        } catch (e: any) {
                            Alert.alert('Error', formatApiDetail(e));
                        }
                    },
                },
            ],
        );
    };

    const openNewSubforum = (categoryId: string) => {
        setSubCatId(categoryId);
        setSubName('');
        setSubDesc('');
        setSubOrder('');
        setSubPremium(false);
        setSubReadOnly(false);
        setEditSubId(null);
        setModal('sub_new');
    };

    const openNewBoardFromHeader = () => {
        if (v2Categories.length === 0) {
            Alert.alert('Create a category first', 'Add a category, then add a board. You can set Public vs Premium on each board.');
            return;
        }
        openNewSubforum(v2Categories[0].id);
    };

    const openEditSubforum = (sub: SubforumRow) => {
        setEditSubId(sub.id);
        setSubCatId(sub.category_id);
        setSubName(sub.name);
        setSubDesc(sub.description || '');
        setSubOrder(sub.order != null ? String(sub.order) : '');
        setSubPremium((sub.access_tier || '').toLowerCase() === 'premium');
        setSubReadOnly(sub.is_read_only);
        setModal('sub_edit');
    };

    const saveSubforum = async () => {
        const name = subName.trim();
        if (!name) {
            Alert.alert('Name required');
            return;
        }
        if (name.length < 2) {
            Alert.alert('Board name too short', 'Use at least 2 characters (server requirement).');
            return;
        }
        if (!subCatId) {
            Alert.alert('Pick a category');
            return;
        }
        const orderParsed = subOrder.trim() === '' ? NaN : parseInt(subOrder, 10);
        const orderVal = Number.isNaN(orderParsed) ? undefined : orderParsed;
        const base = {
            category_id: subCatId,
            name,
            description: subDesc.trim() || undefined,
            access_tier: (subPremium ? 'premium' : 'public') as 'public' | 'premium',
            is_read_only: subReadOnly,
        };
        try {
            if (modal === 'sub_new') {
                await api.createAdminForumSubforum(
                    orderVal !== undefined ? { ...base, order: orderVal } : base,
                );
            } else if (editSubId) {
                await api.updateAdminForumSubforum(
                    editSubId,
                    orderVal !== undefined ? { ...base, order: orderVal } : base,
                );
            }
            setModal('none');
            await loadAll();
        } catch (e: any) {
            Alert.alert('Error', formatApiDetail(e));
        }
    };

    const deleteSubforum = (sub: SubforumRow) => {
        Alert.alert(
            'Delete board',
            `Delete "${sub.name}" and all threads/posts? (${sub.thread_count} threads)`,
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Delete',
                    style: 'destructive',
                    onPress: async () => {
                        try {
                            await api.deleteAdminForumSubforum(sub.id);
                            await loadAll();
                        } catch (e: any) {
                            Alert.alert('Error', formatApiDetail(e));
                        }
                    },
                },
            ],
        );
    };

    const renderModal = () => (
        <Modal visible={modal !== 'none'} animationType="slide" transparent>
            <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : undefined}
                style={styles.modalOverlay}
            >
                <View style={styles.modalCard}>
                    <Text style={styles.modalTitle}>
                        {modal === 'cat_new' && 'New category'}
                        {modal === 'cat_edit' && 'Edit category'}
                        {modal === 'sub_new' && 'New board (forum)'}
                        {modal === 'sub_edit' && 'Edit board'}
                    </Text>
                    <ScrollView
                        style={[styles.modalScroll, { maxHeight: MODAL_BODY_MAX_H }]}
                        keyboardShouldPersistTaps="handled"
                        showsVerticalScrollIndicator={false}
                        nestedScrollEnabled
                    >
                        {(modal === 'sub_new' || modal === 'sub_edit') && (
                            <>
                                <Text style={styles.inputLabel}>Category</Text>
                                <ScrollView
                                    horizontal
                                    showsHorizontalScrollIndicator={false}
                                    style={styles.chipRow}
                                    nestedScrollEnabled
                                >
                                    {v2Categories.map((c) => (
                                        <TouchableOpacity
                                            key={c.id}
                                            style={[styles.chip, subCatId === c.id && styles.chipOn]}
                                            onPress={() => setSubCatId(c.id)}
                                        >
                                            <Text style={[styles.chipText, subCatId === c.id && styles.chipTextOn]}>
                                                {c.name}
                                            </Text>
                                        </TouchableOpacity>
                                    ))}
                                </ScrollView>
                                <Text style={styles.inputLabel}>Board name</Text>
                                <TextInput
                                    style={styles.input}
                                    value={subName}
                                    onChangeText={setSubName}
                                    placeholder="e.g. Influencer Q&A (min 2 characters)"
                                    placeholderTextColor={colors.textMuted}
                                />
                                <Text style={styles.inputLabel}>Description</Text>
                                <TextInput
                                    style={[styles.input, styles.inputMultiline]}
                                    value={subDesc}
                                    onChangeText={setSubDesc}
                                    multiline
                                    placeholderTextColor={colors.textMuted}
                                />
                                <Text style={styles.inputLabel}>Access</Text>
                                <Text style={styles.helperText}>
                                    Public: all signed-in users. Premium: subscribers on the Premium tier only.
                                </Text>
                                <View style={styles.segmentRow}>
                                    <TouchableOpacity
                                        style={[styles.segment, !subPremium && styles.segmentActive]}
                                        onPress={() => setSubPremium(false)}
                                        activeOpacity={0.85}
                                    >
                                        <Text style={[styles.segmentText, !subPremium && styles.segmentTextActive]}>
                                            Public
                                        </Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity
                                        style={[styles.segment, subPremium && styles.segmentActivePrem]}
                                        onPress={() => setSubPremium(true)}
                                        activeOpacity={0.85}
                                    >
                                        <Text style={[styles.segmentText, subPremium && styles.segmentTextActivePrem]}>
                                            Premium
                                        </Text>
                                    </TouchableOpacity>
                                </View>
                                <View style={styles.switchRow}>
                                    <View style={styles.switchLabelWrap}>
                                        <Text style={styles.switchLabel}>Read-only</Text>
                                        <Text style={styles.helperTextInline}>No new threads; existing posts stay visible.</Text>
                                    </View>
                                    <Switch value={subReadOnly} onValueChange={setSubReadOnly} />
                                </View>
                                <Text style={styles.inputLabel}>Sort order (optional)</Text>
                                <TextInput
                                    style={styles.input}
                                    value={subOrder}
                                    onChangeText={setSubOrder}
                                    keyboardType="number-pad"
                                    placeholder="Leave blank for default (9999)"
                                    placeholderTextColor={colors.textMuted}
                                />
                            </>
                        )}
                        {(modal === 'cat_new' || modal === 'cat_edit') && (
                            <>
                                <Text style={styles.inputLabel}>Name</Text>
                                <TextInput
                                    style={styles.input}
                                    value={catName}
                                    onChangeText={setCatName}
                                    placeholderTextColor={colors.textMuted}
                                />
                                <Text style={styles.inputLabel}>Description</Text>
                                <TextInput
                                    style={[styles.input, styles.inputMultiline]}
                                    value={catDesc}
                                    onChangeText={setCatDesc}
                                    multiline
                                    placeholderTextColor={colors.textMuted}
                                />
                                <Text style={styles.inputLabel}>Order</Text>
                                <TextInput
                                    style={styles.input}
                                    value={catOrder}
                                    onChangeText={setCatOrder}
                                    keyboardType="number-pad"
                                    placeholderTextColor={colors.textMuted}
                                />
                                <Text style={styles.helperText}>
                                    Categories group boards. Set Public vs Premium when you add each board.
                                </Text>
                            </>
                        )}
                    </ScrollView>
                    <View style={styles.modalActions}>
                        <TouchableOpacity style={styles.modalBtnGhost} onPress={() => setModal('none')}>
                            <Text style={styles.modalBtnGhostText}>Cancel</Text>
                        </TouchableOpacity>
                        {(modal === 'cat_new' || modal === 'cat_edit') && (
                            <TouchableOpacity style={styles.modalBtnPrimary} onPress={() => void saveCategory()}>
                                <Text style={styles.modalBtnPrimaryText}>Save</Text>
                            </TouchableOpacity>
                        )}
                        {(modal === 'sub_new' || modal === 'sub_edit') && (
                            <TouchableOpacity style={styles.modalBtnPrimary} onPress={() => void saveSubforum()}>
                                <Text style={styles.modalBtnPrimaryText}>Save</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                </View>
            </KeyboardAvoidingView>
        </Modal>
    );

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator color={colors.foreground} />
            </View>
        );
    }

    return (
        <View style={styles.container}>
            {renderModal()}
            <ScrollView
                refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.foreground} />}
                contentContainerStyle={styles.scrollPad}
            >
                <View style={styles.header}>
                    <Text style={styles.title}>Forums</Text>
                    <View style={styles.headerActions}>
                        <TouchableOpacity
                            style={styles.headerSecondaryBtn}
                            onPress={openNewBoardFromHeader}
                            activeOpacity={0.75}
                        >
                            <Text style={styles.headerSecondaryBtnText}>New board</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.createBtn} onPress={openNewCategory} activeOpacity={0.7}>
                            <Text style={styles.createBtnText}>Category</Text>
                        </TouchableOpacity>
                    </View>
                </View>
                <Text style={styles.sectionLead}>
                    Categories organize boards (forums). Each board is Public or Premium and can be read-only. Use New board
                    to set access; categories are folders only.
                </Text>

                {v2Categories.length === 0 ? (
                    <Text style={styles.empty}>No categories yet. Tap New category.</Text>
                ) : (
                    v2Categories.map((c) => (
                        <View key={c.id} style={styles.catBlock}>
                            <TouchableOpacity
                                style={styles.catHeader}
                                onPress={() => toggleExpand(c.id)}
                                activeOpacity={0.75}
                            >
                                <Ionicons
                                    name={expanded[c.id] ? 'chevron-down' : 'chevron-forward'}
                                    size={20}
                                    color={colors.foreground}
                                />
                                <View style={styles.catHeaderText}>
                                    <Text style={styles.catName}>{c.name}</Text>
                                    <Text style={styles.catMeta}>
                                        {c.subforums.length} board(s) · order {c.order}
                                    </Text>
                                </View>
                                <TouchableOpacity onPress={() => openEditCategory(c)} hitSlop={10} style={styles.iconBtn}>
                                    <Ionicons name="pencil-outline" size={20} color={colors.foreground} />
                                </TouchableOpacity>
                                <TouchableOpacity onPress={() => deleteCategory(c)} hitSlop={10} style={styles.iconBtn}>
                                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                                </TouchableOpacity>
                            </TouchableOpacity>
                            {expanded[c.id] ? (
                                <View style={styles.subList}>
                                    <TouchableOpacity
                                        style={styles.addBoardBtn}
                                        onPress={() => openNewSubforum(c.id)}
                                        activeOpacity={0.7}
                                    >
                                        <Ionicons name="add-circle-outline" size={20} color={colors.accent} />
                                        <Text style={styles.addBoardText}>Add board in this category</Text>
                                    </TouchableOpacity>
                                    {c.subforums.map((s) => (
                                        <View key={s.id} style={styles.subCard}>
                                            <View style={styles.subInfo}>
                                                <Text style={styles.subName}>{s.name}</Text>
                                                <View style={styles.badgeRow}>
                                                    <View
                                                        style={[
                                                            styles.tierPill,
                                                            (s.access_tier || '').toLowerCase() === 'premium'
                                                                ? styles.tierPremium
                                                                : styles.tierPublic,
                                                        ]}
                                                    >
                                                        <Text
                                                            style={[
                                                                styles.tierPillText,
                                                                (s.access_tier || '').toLowerCase() === 'premium' &&
                                                                    styles.tierPillTextPrem,
                                                            ]}
                                                        >
                                                            {(s.access_tier || '').toLowerCase() === 'premium'
                                                                ? 'Premium'
                                                                : 'Public'}
                                                        </Text>
                                                    </View>
                                                    {s.is_read_only ? (
                                                        <View style={styles.roPill}>
                                                            <Text style={styles.roPillText}>Read-only</Text>
                                                        </View>
                                                    ) : null}
                                                    <Text style={styles.threadCount}>{s.thread_count} threads</Text>
                                                </View>
                                            </View>
                                            <TouchableOpacity onPress={() => openEditSubforum(s)} style={styles.iconBtn}>
                                                <Ionicons name="pencil-outline" size={20} color={colors.foreground} />
                                            </TouchableOpacity>
                                            <TouchableOpacity onPress={() => deleteSubforum(s)} style={styles.iconBtn}>
                                                <Ionicons name="trash-outline" size={20} color={colors.error} />
                                            </TouchableOpacity>
                                        </View>
                                    ))}
                                </View>
                            ) : null}
                        </View>
                    ))
                )}

                <Text style={styles.legacyTitle}>Legacy chat channels</Text>
                <Text style={styles.legacySub}>
                    Realtime channel list (separate from thread forums). Open to moderate chat.
                </Text>
                {legacyChannels.map((item) => (
                    <TouchableOpacity
                        key={item.id}
                        style={styles.legacyCard}
                        onPress={() =>
                            navigation.navigate('ChannelChat', {
                                channelId: item.id,
                                channelName: item.name,
                                isAdminOnly: item.is_admin_only,
                            })
                        }
                        activeOpacity={0.72}
                    >
                        <Ionicons
                            name={item.is_admin_only ? 'megaphone-outline' : 'chatbubbles-outline'}
                            size={22}
                            color={colors.textSecondary}
                        />
                        <Text style={styles.legacyName} numberOfLines={2}>
                            {item.name}
                        </Text>
                        <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                    </TouchableOpacity>
                ))}
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background },
    scrollPad: { paddingBottom: 40 },
    header: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.lg,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: spacing.sm,
    },
    headerActions: { flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 0 },
    headerSecondaryBtn: {
        paddingHorizontal: 12,
        paddingVertical: 10,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
    },
    headerSecondaryBtnText: { fontSize: 13, fontWeight: '700', color: colors.foreground },
    title: { fontSize: 26, fontWeight: '700', color: colors.foreground, letterSpacing: -0.8, flex: 1, minWidth: 0 },
    createBtn: {
        backgroundColor: colors.foreground,
        paddingHorizontal: 14,
        paddingVertical: 10,
        borderRadius: borderRadius.lg,
    },
    createBtnText: { color: colors.buttonText, fontWeight: '700', fontSize: 13 },
    sectionLead: {
        marginHorizontal: spacing.lg,
        marginTop: spacing.sm,
        marginBottom: spacing.md,
        fontSize: 14,
        color: colors.textSecondary,
        lineHeight: 20,
    },
    empty: { marginHorizontal: spacing.lg, color: colors.textMuted, fontSize: 15 },
    catBlock: {
        marginHorizontal: spacing.lg,
        marginBottom: spacing.md,
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        overflow: 'hidden',
        ...shadows.sm,
    },
    catHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: spacing.md,
        gap: spacing.sm,
    },
    catHeaderText: { flex: 1, minWidth: 0 },
    catName: { fontSize: 17, fontWeight: '700', color: colors.foreground },
    catMeta: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
    subList: { paddingHorizontal: spacing.md, paddingBottom: spacing.md },
    addBoardBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingVertical: spacing.sm,
        marginBottom: spacing.sm,
    },
    addBoardText: { fontSize: 14, fontWeight: '600', color: colors.accent },
    subCard: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        marginBottom: spacing.sm,
    },
    subInfo: { flex: 1, minWidth: 0 },
    subName: { fontSize: 15, fontWeight: '600', color: colors.foreground },
    badgeRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 6 },
    tierPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: borderRadius.full },
    tierPublic: { backgroundColor: 'rgba(100,116,139,0.2)' },
    tierPremium: { backgroundColor: 'rgba(168,85,247,0.2)' },
    tierPillText: { fontSize: 11, fontWeight: '700', color: colors.textSecondary },
    tierPillTextPrem: { color: '#a855f7' },
    roPill: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: borderRadius.full,
        backgroundColor: 'rgba(234,179,8,0.2)',
    },
    roPillText: { fontSize: 11, fontWeight: '700', color: '#ca8a04' },
    threadCount: { fontSize: 12, color: colors.textMuted },
    iconBtn: { padding: 8 },
    legacyTitle: {
        marginHorizontal: spacing.lg,
        marginTop: spacing.xl,
        fontSize: 18,
        fontWeight: '700',
        color: colors.foreground,
    },
    legacySub: {
        marginHorizontal: spacing.lg,
        marginTop: 4,
        marginBottom: spacing.md,
        fontSize: 13,
        color: colors.textSecondary,
    },
    legacyCard: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        marginHorizontal: spacing.lg,
        marginBottom: 10,
        padding: spacing.md,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
    },
    legacyName: { flex: 1, fontSize: 15, fontWeight: '600', color: colors.foreground },
    modalOverlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'flex-end',
    },
    modalCard: {
        backgroundColor: colors.background,
        borderTopLeftRadius: borderRadius['2xl'],
        borderTopRightRadius: borderRadius['2xl'],
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.lg,
        paddingBottom: spacing.md,
        maxHeight: '90%',
    },
    modalScroll: { flexGrow: 0 },
    modalTitle: { fontSize: 20, fontWeight: '700', color: colors.foreground, marginBottom: spacing.sm },
    helperText: {
        fontSize: 13,
        color: colors.textSecondary,
        lineHeight: 18,
        marginBottom: spacing.sm,
    },
    helperTextInline: { fontSize: 12, color: colors.textMuted, marginTop: 2, lineHeight: 16 },
    segmentRow: { flexDirection: 'row', gap: 10, marginBottom: spacing.md },
    segment: {
        flex: 1,
        paddingVertical: 12,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        alignItems: 'center',
    },
    segmentActive: { borderColor: colors.foreground, backgroundColor: colors.surface },
    segmentActivePrem: { borderColor: '#a855f7', backgroundColor: 'rgba(168,85,247,0.12)' },
    segmentText: { fontSize: 15, fontWeight: '600', color: colors.textSecondary },
    segmentTextActive: { color: colors.foreground },
    segmentTextActivePrem: { color: '#7c3aed' },
    inputLabel: { fontSize: 13, fontWeight: '600', color: colors.textSecondary, marginBottom: 6, marginTop: 10 },
    input: {
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.md,
        padding: 12,
        fontSize: 16,
        color: colors.foreground,
        backgroundColor: colors.card,
    },
    inputMultiline: { minHeight: 72, textAlignVertical: 'top' },
    chipRow: { flexGrow: 0, marginBottom: 8 },
    chip: {
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
        marginRight: 8,
        borderWidth: 1,
        borderColor: colors.border,
    },
    chipOn: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    chipText: { fontSize: 13, fontWeight: '600', color: colors.foreground },
    chipTextOn: { color: colors.buttonText },
    switchRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginTop: spacing.sm,
        marginBottom: spacing.sm,
    },
    switchLabelWrap: { flex: 1, paddingRight: 12 },
    switchLabel: { fontSize: 14, fontWeight: '600', color: colors.foreground },
    modalActions: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        alignItems: 'center',
        gap: spacing.md,
        marginTop: spacing.md,
        paddingTop: spacing.md,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.border,
        flexWrap: 'wrap',
    },
    modalBtnGhost: { paddingVertical: 12, paddingHorizontal: 16 },
    modalBtnGhostText: { fontSize: 16, fontWeight: '600', color: colors.textSecondary },
    modalBtnPrimary: {
        backgroundColor: colors.foreground,
        paddingVertical: 12,
        paddingHorizontal: 20,
        borderRadius: borderRadius.full,
    },
    modalBtnPrimaryText: { fontSize: 16, fontWeight: '700', color: colors.buttonText },
});
