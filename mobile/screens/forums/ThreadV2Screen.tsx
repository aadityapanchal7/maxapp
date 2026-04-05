import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator, Alert, KeyboardAvoidingView, Platform } from 'react-native';
import { FlashList, FlashListRef } from '@shopify/flash-list';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { useForumV2PostsQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

/** Reddit-style: one narrow column per nesting level with a vertical rule on the left. */
const THREAD_GUTTER_COL_W = 18;
const THREAD_LINE_W = 2;
const MAX_THREAD_DEPTH = 12;
const THREAD_LINE_COLORS = [
    '#a1a1aa',
    '#d4d4d8',
    '#71717a',
    '#e4e4e7',
    '#94a3b8',
    '#cbd5e1',
];

function ThreadGutter({ depth }: { depth: number }) {
    const d = Math.min(Math.max(depth, 0), MAX_THREAD_DEPTH);
    if (d <= 0) return null;
    return (
        <View style={gutterStyles.gutterRow} accessibilityElementsHidden>
            {Array.from({ length: d }).map((_, i) => (
                <View
                    key={i}
                    style={[
                        gutterStyles.gutterCol,
                        {
                            borderLeftWidth: THREAD_LINE_W,
                            borderLeftColor: THREAD_LINE_COLORS[i % THREAD_LINE_COLORS.length],
                        },
                    ]}
                />
            ))}
        </View>
    );
}

const gutterStyles = StyleSheet.create({
    gutterRow: { flexDirection: 'row', alignItems: 'stretch' },
    gutterCol: {
        width: THREAD_GUTTER_COL_W,
    },
});

type Post = {
    id: string;
    user_id: string;
    username?: string | null;
    user_avatar_url?: string;
    content: string;
    entities?: any;
    score?: number;
    upvotes?: number;
    downvotes?: number;
    my_vote?: number;
    created_at?: string;
    parent_post_id?: string | null;
};

type ThreadRow =
    | { key: string; kind: 'post'; post: Post; depth: number }
    | { key: string; kind: 'collapsed'; parentId: string; count: number; depth: number };

function sortByTime(a: Post, b: Post): number {
    const at = new Date(a.created_at || 0).getTime();
    const bt = new Date(b.created_at || 0).getTime();
    return at - bt;
}

/** Depth-first: OP, then replies under each parent; all direct replies collapsed behind one row until expanded (including a single reply). */
function buildThreadRows(posts: Post[], expanded: Record<string, boolean>): ThreadRow[] {
    if (posts.length === 0) return [];
    const sorted = [...posts].sort(sortByTime);
    const childrenOf: Record<string, Post[]> = {};
    for (const p of sorted) {
        const par = p.parent_post_id;
        if (!par) continue;
        if (!childrenOf[par]) childrenOf[par] = [];
        childrenOf[par].push(p);
    }
    for (const k of Object.keys(childrenOf)) {
        childrenOf[k].sort(sortByTime);
    }

    const roots = sorted.filter((p) => !p.parent_post_id);
    const op = roots[0] ?? sorted[0];
    const rootList = roots.length > 1 ? roots : [op];

    const rows: ThreadRow[] = [];

    function walk(p: Post, depth: number) {
        rows.push({ key: `post-${p.id}`, kind: 'post', post: p, depth });
        const kids = childrenOf[p.id] || [];
        if (kids.length === 0) return;
        rows.push({ key: `collapsed-${p.id}`, kind: 'collapsed', parentId: p.id, count: kids.length, depth });
        if (expanded[p.id]) {
            for (const k of kids) walk(k, depth + 1);
        }
    }

    for (const r of rootList) walk(r, 0);
    return rows;
}

export default function ThreadV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const route = useRoute<any>();
    const params = route.params ?? {};
    const threadId = params.threadId as string;
    const threadTitle = (params.threadTitle as string) ?? 'thread';

    const [text, setText] = useState('');
    const [sending, setSending] = useState(false);
    /** Parent post when user taps Reply (threading only; no quote text). */
    const [replyParentPostId, setReplyParentPostId] = useState<string | null>(null);
    const [watching, setWatching] = useState(false);
    const [watchLoading, setWatchLoading] = useState(false);
    const [expandedReplies, setExpandedReplies] = useState<Record<string, boolean>>({});
    const listRef = useRef<FlashListRef<ThreadRow>>(null);

    const postsQ = useForumV2PostsQuery({ threadId, sort: 'new' });
    const serverPosts: Post[] = useMemo(() => (postsQ.data?.posts ?? []) as Post[], [postsQ.data]);
    const [posts, setPosts] = useState<Post[]>([]);
    const loading = postsQ.isPending && posts.length === 0;

    useEffect(() => {
        setPosts(serverPosts);
    }, [serverPosts]);

    const threadRows = useMemo(() => buildThreadRows(posts, expandedReplies), [posts, expandedReplies]);

    const submit = async () => {
        const msg = text.trim();
        if (!msg) return;
        setSending(true);
        try {
            await api.replyForumV2Thread(threadId, {
                content: msg,
                parent_post_id: replyParentPostId ?? undefined,
            });
            setText('');
            setReplyParentPostId(null);
            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Posts(threadId, 'new') });
            setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 200);
        } catch (e: any) {
            const msg2 = e?.response?.data?.detail || e?.message || 'failed to reply';
            Alert.alert('couldn’t reply', String(msg2));
        } finally {
            setSending(false);
        }
    };

    const toggleWatch = async () => {
        setWatchLoading(true);
        try {
            const res = await api.watchForumV2Thread(threadId, !watching);
            setWatching(!!res?.watching);
        } catch {
            Alert.alert('error', "couldn't update watch");
        } finally {
            setWatchLoading(false);
        }
    };

    const applyOptimisticVote = (p: Post, desired: 1 | -1) => {
        const current: -1 | 0 | 1 = p.my_vote === 1 ? 1 : p.my_vote === -1 ? -1 : 0;
        const next: -1 | 0 | 1 = current === desired ? 0 : desired;

        let up = p.upvotes ?? 0;
        let down = p.downvotes ?? 0;

        if (current === 1) up -= 1;
        if (current === -1) down -= 1;
        if (next === 1) up += 1;
        if (next === -1) down += 1;

        return { ...p, my_vote: next, upvotes: Math.max(0, up), downvotes: Math.max(0, down) };
    };

    const vote = async (postId: string, value: 1 | -1) => {
        const before = posts.find((p) => p.id === postId);
        if (!before) return;

        setPosts((prev) => prev.map((p) => (p.id === postId ? applyOptimisticVote(p, value) : p)));
        try {
            const res = await api.voteForumV2Post(postId, value);
            if (res && typeof res === 'object') {
                setPosts((prev) =>
                    prev.map((p) =>
                        p.id === postId
                            ? {
                                  ...p,
                                  my_vote: typeof res.my_vote === 'number' ? res.my_vote : p.my_vote,
                                  upvotes: typeof res.upvotes === 'number' ? res.upvotes : p.upvotes,
                                  downvotes: typeof res.downvotes === 'number' ? res.downvotes : p.downvotes,
                              }
                            : p,
                    ),
                );
            }

            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Posts(threadId, 'new') });
        } catch {
            setPosts((prev) => prev.map((p) => (p.id === postId ? before : p)));
        }
    };

    const renderPostCard = (item: Post, depth: number) => {
        const mentions = (item.entities?.mentions || []) as string[];
        const upActive = item.my_vote === 1;
        const downActive = item.my_vote === -1;
        /** Top-level posts only (not a reply to another post). Nested replies cannot be replied to. */
        const canReply = !item.parent_post_id;

        return (
            <View style={styles.postRow}>
                <ThreadGutter depth={depth} />
                <View style={[styles.postCard, depth > 0 && styles.postCardReply]}>
                    <View style={styles.postHeader}>
                        <Text style={styles.postUser} numberOfLines={1}>
                            @{item.username || 'user'}
                        </Text>
                        <View style={styles.votePill}>
                            <Ionicons name="arrow-up" size={11} color={upActive ? colors.background : colors.textSecondary} />
                            <Text style={[styles.votePillText, upActive && styles.votePillTextActive]}>
                                {(item.upvotes ?? 0).toString()}
                            </Text>
                            <Ionicons name="arrow-down" size={11} color={downActive ? colors.background : colors.textSecondary} />
                        </View>
                    </View>
                    <Text style={styles.postBody}>{item.content}</Text>
                    {mentions.length > 0 ? (
                        <Text style={styles.mentions} numberOfLines={1}>
                            {mentions.map((m) => `@${m}`).join(' ')}
                        </Text>
                    ) : null}
                    <View style={styles.postActions}>
                        <TouchableOpacity
                            onPress={() => vote(item.id, 1)}
                            style={[styles.voteBtnIcon, upActive && styles.voteBtnIconActive]}
                            activeOpacity={0.85}
                        >
                            <Ionicons name="arrow-up" size={13} color={upActive ? colors.background : colors.textSecondary} />
                        </TouchableOpacity>
                        <TouchableOpacity
                            onPress={() => vote(item.id, -1)}
                            style={[styles.voteBtnIcon, downActive && styles.voteBtnIconActive]}
                            activeOpacity={0.85}
                        >
                            <Ionicons name="arrow-down" size={13} color={downActive ? colors.background : colors.textSecondary} />
                        </TouchableOpacity>
                        {canReply ? (
                            <TouchableOpacity onPress={() => setReplyParentPostId(item.id)} style={styles.actionBtn} activeOpacity={0.8}>
                                <Ionicons name="chatbox-ellipses-outline" size={13} color={colors.textSecondary} />
                                <Text style={styles.actionText}>reply</Text>
                            </TouchableOpacity>
                        ) : null}
                    </View>
                </View>
            </View>
        );
    };

    const renderRow = ({ item }: { item: ThreadRow }) => {
        if (item.kind === 'collapsed') {
            const isOpen = !!expandedReplies[item.parentId];
            return (
                <View style={styles.postRow}>
                    <ThreadGutter depth={item.depth} />
                    <TouchableOpacity
                        style={styles.collapsedBar}
                        onPress={() =>
                            setExpandedReplies((prev) => ({
                                ...prev,
                                [item.parentId]: !isOpen,
                            }))
                        }
                        activeOpacity={0.75}
                    >
                        <Ionicons name={isOpen ? 'chevron-up' : 'chevron-down'} size={12} color={colors.textMuted} />
                        <Text style={styles.collapsedText}>
                            {isOpen
                                ? 'Hide replies'
                                : `${item.count} ${item.count === 1 ? 'reply' : 'replies'}`}
                        </Text>
                    </TouchableOpacity>
                </View>
            );
        }
        return renderPostCard(item.post, item.depth);
    };

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn} activeOpacity={0.8}>
                    <Ionicons name="arrow-back" size={18} color={colors.textSecondary} />
                </TouchableOpacity>
                <View style={{ flex: 1 }}>
                    <Text style={styles.title} numberOfLines={1}>
                        {threadTitle}
                    </Text>
                    <Text style={styles.subtitle}>{posts.length} posts</Text>
                </View>
                <TouchableOpacity
                    onPress={toggleWatch}
                    disabled={watchLoading}
                    style={[styles.watchBtn, watching && styles.watchBtnActive]}
                    activeOpacity={0.85}
                >
                    <Ionicons name={watching ? 'eye' : 'eye-outline'} size={14} color={watching ? colors.background : colors.textSecondary} />
                </TouchableOpacity>
            </View>

            {loading ? (
                <View style={styles.loadingWrap}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            ) : (
                <FlashList
                    ref={listRef}
                    data={threadRows}
                    renderItem={renderRow}
                    keyExtractor={(r) => r.key}
                    getItemType={(r) => r.kind}
                    drawDistance={250}
                    contentContainerStyle={styles.list}
                />
            )}

            <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
                {replyParentPostId ? (
                    <View style={styles.quoteBar}>
                        <Text style={styles.quoteBarText} numberOfLines={1}>
                            Replying to comment
                        </Text>
                        <TouchableOpacity onPress={() => setReplyParentPostId(null)} activeOpacity={0.8}>
                            <Ionicons name="close" size={16} color={colors.textMuted} />
                        </TouchableOpacity>
                    </View>
                ) : null}
                <View style={styles.composer}>
                    <TextInput
                        style={styles.input}
                        placeholder="Reply to thread…"
                        placeholderTextColor={colors.textMuted}
                        value={text}
                        onChangeText={setText}
                        multiline
                        editable={!sending}
                    />
                    <TouchableOpacity
                        onPress={() => void submit()}
                        disabled={!text.trim() || sending}
                        style={[styles.sendBtn, (!text.trim() || sending) && styles.sendBtnDisabled]}
                        activeOpacity={0.85}
                    >
                        {sending ? <ActivityIndicator size="small" color={colors.background} /> : <Ionicons name="send" size={16} color={colors.background} />}
                    </TouchableOpacity>
                </View>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        paddingHorizontal: spacing.md,
        paddingBottom: spacing.sm,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: colors.card,
    },
    iconBtn: {
        width: 32,
        height: 32,
        borderRadius: 16,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    title: { color: colors.foreground, fontSize: 15, fontWeight: '800' },
    subtitle: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
    watchBtn: {
        width: 30,
        height: 30,
        borderRadius: 15,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    watchBtnActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    list: { paddingHorizontal: spacing.sm, paddingTop: spacing.sm, paddingBottom: spacing.lg },
    postRow: {
        flexDirection: 'row',
        alignItems: 'stretch',
        marginBottom: spacing.sm,
    },
    collapsedBar: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.sm,
        minHeight: 36,
    },
    collapsedText: { color: colors.textMuted, fontSize: 12, fontWeight: '700' },
    postCard: {
        flex: 1,
        minWidth: 0,
        backgroundColor: colors.card,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        borderRadius: borderRadius.md,
        paddingHorizontal: spacing.sm,
        paddingVertical: spacing.sm,
        ...shadows.sm,
    },
    postCardReply: {
        backgroundColor: colors.surface,
        borderColor: colors.borderLight,
    },
    postHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    postUser: { color: colors.foreground, fontSize: 12, fontWeight: '800', flex: 1, paddingRight: 8 },
    votePill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingHorizontal: 6,
        height: 22,
        borderRadius: 11,
        backgroundColor: colors.surfaceLight,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    votePillText: { color: colors.textSecondary, fontSize: 10, fontWeight: '800' },
    votePillTextActive: { color: colors.background },
    postBody: { color: colors.foreground, fontSize: 12, lineHeight: 16, marginTop: 6 },
    mentions: { color: colors.textSecondary, fontSize: 10, marginTop: 6 },
    postActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
    actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
    actionText: { color: colors.textSecondary, fontSize: 11, fontWeight: '700' },
    voteBtnIcon: {
        width: 28,
        height: 28,
        borderRadius: 14,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    voteBtnIconActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    composer: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        gap: 8,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        borderTopWidth: 1,
        borderTopColor: colors.border,
        backgroundColor: colors.card,
    },
    input: {
        flex: 1,
        minHeight: 36,
        maxHeight: 100,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surfaceLight,
        paddingHorizontal: 10,
        paddingVertical: 8,
        fontSize: 13,
        color: colors.foreground,
    },
    sendBtn: {
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.foreground,
    },
    sendBtnDisabled: { opacity: 0.45 },
    quoteBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.md,
        paddingVertical: 6,
        borderTopWidth: 1,
        borderTopColor: colors.border,
        backgroundColor: colors.surfaceLight,
        gap: 8,
    },
    quoteBarText: { color: colors.textSecondary, fontSize: 11, fontWeight: '700', flex: 1 },
});
