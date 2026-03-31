import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { useForumV2CategoriesQuery, useForumV2SubforumsQuery } from '../../hooks/useAppQueries';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

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

export default function ForumsHomeV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { user } = useAuth() as any;
    const catsQ = useForumV2CategoriesQuery();
    const subsQ = useForumV2SubforumsQuery(null);

    const categories: Category[] = useMemo(() => catsQ.data ?? [], [catsQ.data]);
    const subforums: Subforum[] = useMemo(() => subsQ.data ?? [], [subsQ.data]);
    const loading = (catsQ.isPending && categories.length === 0) || (subsQ.isPending && subforums.length === 0);

    const canAccessPremium = !!user?.is_paid || !!user?.is_admin;
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

    const subsByCategory = useMemo(() => {
        const m = new Map<string, Subforum[]>();
        for (const s of subforums) {
            const tier = (s.access_tier ?? 'public').toLowerCase();
            if (tier === 'premium' && !canAccessPremium) continue;
            const arr = m.get(s.category_id) ?? [];
            arr.push(s);
            m.set(s.category_id, arr);
        }
        for (const [k, arr] of m.entries()) {
            arr.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
            m.set(k, arr);
        }
        return m;
    }, [subforums, canAccessPremium]);

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

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <View style={styles.headerRow}>
                    <Text style={styles.title}>Forums</Text>
                    <View style={styles.headerActions}>
                        <TouchableOpacity
                            style={styles.pill}
                            onPress={() => navigation.navigate('CreateSubforumV2')}
                            activeOpacity={0.8}
                        >
                            <Ionicons name="add" size={16} color={colors.textSecondary} />
                            <Text style={styles.pillText}>Create board</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={styles.iconBtn}
                            onPress={() => navigation.navigate('ForumNotificationsV2')}
                            activeOpacity={0.8}
                        >
                            <Ionicons name="notifications-outline" size={20} color={colors.textSecondary} />
                        </TouchableOpacity>
                    </View>
                </View>
                <Text style={styles.subTitle}>pick a board. post something useful.</Text>
            </View>

            {loading ? (
                <View style={styles.loadingWrap}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            ) : (
                <ScrollView contentContainerStyle={styles.scroll}>
                    {categories.map((c) => {
                        const boards = subsByCategory.get(c.id) ?? [];
                        if (boards.length === 0) return null;
                        return (
                            <View key={c.id} style={styles.section}>
                                <TouchableOpacity style={styles.sectionHeader} onPress={() => toggleCollapsed(c.id)} activeOpacity={0.85}>
                                    <View style={{ flex: 1 }}>
                                        <Text style={styles.sectionTitle}>{c.name}</Text>
                                        {c.description ? <Text style={styles.sectionDesc}>{c.description}</Text> : null}
                                    </View>
                                    <Ionicons
                                        name={collapsed[c.id] ? 'chevron-down' : 'chevron-up'}
                                        size={18}
                                        color={colors.textMuted}
                                    />
                                </TouchableOpacity>
                                {!collapsed[c.id] ? (
                                    <View style={styles.card}>
                                        {boards.map((s) => {
                                            return (
                                                <TouchableOpacity
                                                    key={s.id}
                                                    style={styles.boardRow}
                                                    onPress={() => openSubforum(s)}
                                                    activeOpacity={0.8}
                                                >
                                                    <View style={styles.boardMain}>
                                                        <View style={styles.boardTitleRow}>
                                                            <Text style={styles.boardName} numberOfLines={1}>
                                                                {s.name}
                                                            </Text>
                                                            {s.is_read_only ? <Text style={styles.readOnly}>read-only</Text> : null}
                                                        </View>
                                                        {s.description ? (
                                                            <Text style={styles.boardDesc} numberOfLines={2}>
                                                                {s.description}
                                                            </Text>
                                                        ) : null}
                                                        <Text style={styles.meta}>
                                                            {(s.thread_count ?? 0).toString()} threads
                                                        </Text>
                                                    </View>
                                                    <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                                                </TouchableOpacity>
                                            );
                                        })}
                                    </View>
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
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: colors.card,
    },
    headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    title: { fontSize: 22, fontWeight: '800', color: colors.foreground, letterSpacing: -0.4 },
    subTitle: { marginTop: 6, color: colors.textMuted, fontSize: 12 },
    headerActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
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
    pill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingHorizontal: 10,
        height: 36,
        borderRadius: 18,
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    pillText: { color: colors.textSecondary, fontSize: 12, fontWeight: '600' },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    scroll: { padding: spacing.lg, paddingBottom: spacing.xxl },
    section: { marginBottom: spacing.lg },
    sectionHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 10,
    },
    sectionTitle: { color: colors.foreground, fontSize: 16, fontWeight: '800' },
    sectionDesc: { color: colors.textMuted, fontSize: 12, marginTop: 4, marginBottom: 10 },
    card: {
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.lg,
        overflow: 'hidden',
        ...shadows.sm,
    },
    boardRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
    },
    boardMain: { flex: 1, paddingRight: 10 },
    boardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
    boardName: { color: colors.foreground, fontSize: 14, fontWeight: '800', maxWidth: '80%' },
    boardDesc: { color: colors.textMuted, fontSize: 12, marginTop: 6, lineHeight: 16 },
    meta: { color: colors.textMuted, fontSize: 11, marginTop: 6 },
    readOnly: { color: colors.textMuted, fontSize: 11, fontWeight: '700' },
});

