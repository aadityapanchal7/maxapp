import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    TextInput,
    ActivityIndicator,
    Alert,
    KeyboardAvoidingView,
    Platform,
    RefreshControl,
} from 'react-native';
import { FlashList, FlashListRef } from '@shopify/flash-list';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { useForumV2PostsQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';
import { CachedImage } from '../../components/CachedImage';

/** Reddit-style: one narrow column per nesting level with a vertical rule on the left. */
const THREAD_GUTTER_COL_W = 22;
const THREAD_LINE_W = 2;
const MAX_THREAD_DEPTH = 12;
const THREAD_LINE_COLORS = [
    'rgba(10, 10, 10, 0.07)',
    'rgba(10, 10, 10, 0.04)',
    'rgba(156, 156, 148, 0.35)',
    'rgba(10, 10, 10, 0.09)',
    'rgba(107, 107, 99, 0.22)',
    'rgba(10, 10, 10, 0.05)',
];

function formatRelativeTime(iso?: string): string {
    if (!iso) return '';
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return '';
    const s = Math.floor((Date.now() - t) / 1000);
    if (s < 45) return 'now';
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    if (s < 604800) return `${Math.floor(s / 86400)}d`;
    return `${Math.floor(s / 604800)}w`;
}

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

function getPostTimestamp(post: Post): number {
    const ts = new Date(post.created_at || 0).getTime();
    return Number.isNaN(ts) ? 0 : ts;
}

function getPostScore(post: Post): number {
    if (typeof post.score === 'number') return post.score;
    return (post.upvotes ?? 0) - (post.downvotes ?? 0);
}

function sortByRatingDesc(a: Post, b: Post): number {
    const scoreDiff = getPostScore(b) - getPostScore(a);
    if (scoreDiff !== 0) return scoreDiff;

    const timeDiff = getPostTimestamp(b) - getPostTimestamp(a);
    if (timeDiff !== 0) return timeDiff;

    return b.id.localeCompare(a.id);
}

/** Depth-first: OP, then replies under each parent; all direct replies collapsed behind one row until expanded (including a single reply). */
function buildThreadRows(posts: Post[], expanded: Record<string, boolean>): ThreadRow[] {
    if (posts.length === 0) return [];
    const sorted = [...posts].sort(sortByRatingDesc);
    const childrenOf: Record<string, Post[]> = {};
    for (const p of sorted) {
        const par = p.parent_post_id;
        if (!par) continue;
        if (!childrenOf[par]) childrenOf[par] = [];
        childrenOf[par].push(p);
    }
    for (const k of Object.keys(childrenOf)) {
        childrenOf[k].sort(sortByRatingDesc);
    }

    const roots = sorted.filter((p) => !p.parent_post_id);
    const rootList = roots.length > 0 ? roots : [sorted[0]];

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

    const onRefresh = useCallback(() => void postsQ.refetch(), [postsQ]);
    const listRefreshing = postsQ.isRefetching && !postsQ.isPending;

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
        const net = (item.upvotes ?? 0) - (item.downvotes ?? 0);
        const scoreText = net === 0 && (item.upvotes ?? 0) === 0 && (item.downvotes ?? 0) === 0 ? '—' : String(net);
        const rel = formatRelativeTime(item.created_at);
        const avatarUri = item.user_avatar_url ? api.resolveAttachmentUrl(item.user_avatar_url) : null;

        return (
            <View style={[styles.postRow, depth > 0 && styles.postRowReply]}>
                <ThreadGutter depth={depth} />
                <View style={[styles.postCard, depth > 0 && styles.postCardReply]}>
                    <View style={styles.postHeader}>
                        <View style={styles.postHeaderMain}>
                            {avatarUri ? (
                                <CachedImage
                                    uri={avatarUri}
                                    style={[styles.avatar, depth > 0 && styles.avatarReply]}
                                    accessibilityIgnoresInvertColors
                                />
                            ) : (
                                <View style={[styles.avatarFallback, depth > 0 && styles.avatarFallbackReply]} accessibilityElementsHidden>
                                    <Ionicons name="person" size={13} color={colors.textMuted} />
                                </View>
                            )}
                            <Text style={[styles.postUser, depth > 0 && styles.postUserReply]} numberOfLines={1}>
                                {item.username || 'user'}
                            </Text>
                        </View>
                        {rel ? <Text style={styles.postTime}>{rel}</Text> : null}
                    </View>
                    <Text style={[styles.postBody, depth > 0 && styles.postBodyReply]}>{item.content}</Text>
                    {mentions.length > 0 ? (
                        <Text style={styles.mentions} numberOfLines={1}>
                            {mentions.map((m) => `@${m}`).join(' ')}
                        </Text>
                    ) : null}
                    <View style={[styles.postActions, depth > 0 && styles.postActionsReply]}>
                        <View style={styles.voteCluster}>
                            <TouchableOpacity
                                onPress={() => vote(item.id, 1)}
                                style={[styles.voteHit, upActive && styles.voteHitActive]}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityLabel="Upvote"
                                accessibilityState={{ selected: upActive }}
                                hitSlop={{ top: 6, bottom: 6, left: 8, right: 4 }}
                            >
                                <Ionicons
                                    name="arrow-up"
                                    size={15}
                                    color={upActive ? colors.foreground : colors.textMuted}
                                />
                            </TouchableOpacity>
                            <Text style={[styles.voteScore, net > 0 && styles.voteScorePos, net < 0 && styles.voteScoreNeg]} accessibilityLabel={`Score ${scoreText}`}>
                                {scoreText}
                            </Text>
                            <TouchableOpacity
                                onPress={() => vote(item.id, -1)}
                                style={[styles.voteHit, downActive && styles.voteHitActive]}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityLabel="Downvote"
                                accessibilityState={{ selected: downActive }}
                                hitSlop={{ top: 6, bottom: 6, left: 4, right: 8 }}
                            >
                                <Ionicons
                                    name="arrow-down"
                                    size={15}
                                    color={downActive ? colors.foreground : colors.textMuted}
                                />
                            </TouchableOpacity>
                        </View>
                        {canReply ? (
                            <TouchableOpacity
                                onPress={() => setReplyParentPostId(item.id)}
                                style={styles.replyBtn}
                                activeOpacity={0.8}
                                accessibilityRole="button"
                                accessibilityLabel="Reply to this post"
                                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                            >
                                <Ionicons name="chatbubble-outline" size={14} color={colors.textMuted} />
                                <Text style={styles.replyBtnText}>Reply</Text>
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
                        accessibilityRole="button"
                        accessibilityLabel={isOpen ? 'Hide replies' : `Show ${item.count} ${item.count === 1 ? 'reply' : 'replies'}`}
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

    const keyboardVerticalOffset = Platform.OS === 'ios' ? insets.top + 8 : 0;

    return (
        <View style={styles.container}>
            <View style={styles.screenFill} pointerEvents="none" />
            <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={styles.iconBtn}
                    activeOpacity={0.8}
                    accessibilityRole="button"
                    accessibilityLabel="Go back"
                >
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
                    accessibilityRole="button"
                    accessibilityLabel={watching ? 'Stop watching thread' : 'Watch thread for new posts'}
                    accessibilityState={{ busy: watchLoading, selected: watching }}
                >
                    <Ionicons name={watching ? 'eye' : 'eye-outline'} size={14} color={watching ? colors.background : colors.textSecondary} />
                </TouchableOpacity>
            </View>

            {loading ? (
                <View style={styles.loadingWrap}>
                    <ActivityIndicator size="large" color={colors.foreground} />
                </View>
            ) : (
                <View style={styles.listWrap}>
                    <FlashList
                        ref={listRef}
                        data={threadRows}
                        renderItem={renderRow}
                        keyExtractor={(r) => r.key}
                        getItemType={(r) => r.kind}
                        drawDistance={250}
                        contentContainerStyle={styles.list}
                        keyboardShouldPersistTaps="handled"
                        refreshControl={
                            <RefreshControl refreshing={listRefreshing} onRefresh={onRefresh} tintColor={colors.foreground} />
                        }
                    />
                </View>
            )}

            <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : undefined}
                keyboardVerticalOffset={keyboardVerticalOffset}
                style={styles.keyboardChrome}
            >
                {replyParentPostId ? (
                    <View style={styles.quoteBar}>
                        <Text style={styles.quoteBarText} numberOfLines={1}>
                            Replying to comment
                        </Text>
                        <TouchableOpacity
                            onPress={() => setReplyParentPostId(null)}
                            activeOpacity={0.8}
                            accessibilityRole="button"
                            accessibilityLabel="Cancel reply"
                            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                            style={styles.quoteBarClose}
                        >
                            <Ionicons name="close" size={18} color={colors.textMuted} />
                        </TouchableOpacity>
                    </View>
                ) : null}
                <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
                    <TextInput
                        style={styles.input}
                        placeholder="Reply to thread…"
                        placeholderTextColor={colors.textMuted}
                        value={text}
                        onChangeText={setText}
                        multiline
                        editable={!sending}
                        textAlignVertical="top"
                    />
                    <TouchableOpacity
                        onPress={() => void submit()}
                        disabled={!text.trim() || sending}
                        style={[styles.sendBtn, (!text.trim() || sending) && styles.sendBtnDisabled]}
                        activeOpacity={0.85}
                        accessibilityRole="button"
                        accessibilityLabel="Send reply"
                        accessibilityState={{ disabled: !text.trim() || sending }}
                    >
                        {sending ? (
                            <ActivityIndicator size="small" color={colors.background} />
                        ) : (
                            <Ionicons
                                name="send"
                                size={18}
                                color={!text.trim() ? colors.textMuted : colors.background}
                            />
                        )}
                    </TouchableOpacity>
                </View>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background, overflow: 'hidden' },
    screenFill: { ...StyleSheet.absoluteFillObject, backgroundColor: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
        backgroundColor: colors.background,
        zIndex: 1,
    },
    iconBtn: {
        width: 40,
        height: 40,
        alignItems: 'center',
        justifyContent: 'center',
    },
    title: { ...typography.h3, fontSize: 17, letterSpacing: -0.2 },
    subtitle: { ...typography.caption, marginTop: 4, color: colors.textMuted, fontWeight: '400' },
    watchBtn: {
        width: 40,
        height: 40,
        alignItems: 'center',
        justifyContent: 'center',
    },
    watchBtnActive: { backgroundColor: colors.foreground, borderRadius: borderRadius.full },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    listWrap: { flex: 1 },
    keyboardChrome: { backgroundColor: colors.background },
    list: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl },
    postRow: {
        flexDirection: 'row',
        alignItems: 'stretch',
        marginBottom: spacing.md,
    },
    postRowReply: { marginBottom: spacing.sm },
    collapsedBar: {
        alignSelf: 'flex-start',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 6,
        paddingHorizontal: spacing.sm,
        minHeight: 28,
        marginBottom: 2,
    },
    collapsedText: { color: colors.textSecondary, fontSize: 12, fontWeight: '500', letterSpacing: 0.2 },
    postCard: {
        flex: 1,
        minWidth: 0,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
    },
    postCardReply: {
        backgroundColor: 'transparent',
        borderWidth: 0,
        borderLeftWidth: StyleSheet.hairlineWidth,
        borderLeftColor: colors.border,
        borderRadius: borderRadius.sm,
        paddingVertical: spacing.md,
        shadowOpacity: 0,
        shadowRadius: 0,
        shadowOffset: { width: 0, height: 0 },
        elevation: 0,
    },
    postHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: spacing.sm,
    },
    postHeaderMain: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        flex: 1,
        minWidth: 0,
    },
    avatar: {
        width: 28,
        height: 28,
        borderRadius: 14,
        backgroundColor: colors.surfaceLight,
    },
    avatarReply: { width: 24, height: 24, borderRadius: 12 },
    avatarFallback: {
        width: 28,
        height: 28,
        borderRadius: 14,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    avatarFallbackReply: { width: 24, height: 24, borderRadius: 12 },
    postUser: { color: colors.foreground, fontSize: 14, fontWeight: '600', flex: 1, letterSpacing: -0.1 },
    postUserReply: { fontSize: 13 },
    postTime: { color: colors.textMuted, fontSize: 12, fontWeight: '500', flexShrink: 0, letterSpacing: 0.1 },
    postBody: {
        ...typography.bodySmall,
        color: colors.foreground,
        fontSize: 15,
        lineHeight: 22,
        marginTop: spacing.sm,
        fontWeight: '400',
    },
    postBodyReply: { marginTop: 6, lineHeight: 20 },
    mentions: { color: colors.textSecondary, fontSize: 12, marginTop: spacing.xs },
    postActions: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginTop: spacing.md,
        paddingTop: spacing.sm,
    },
    postActionsReply: { marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 0 },
    voteCluster: { flexDirection: 'row', alignItems: 'center', gap: 2 },
    voteHit: {
        minWidth: 30,
        minHeight: 30,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: borderRadius.sm,
    },
    voteHitActive: { backgroundColor: colors.accentMuted },
    voteScore: {
        minWidth: 26,
        textAlign: 'center',
        fontSize: 13,
        fontWeight: '500',
        color: colors.textMuted,
        letterSpacing: 0,
    },
    voteScorePos: { color: colors.textPrimary },
    voteScoreNeg: { color: colors.textMuted },
    replyBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        minHeight: 30,
        paddingVertical: 4,
        paddingHorizontal: spacing.sm,
        borderRadius: borderRadius.sm,
        backgroundColor: 'transparent',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    replyBtnText: { color: colors.textSecondary, fontSize: 12, fontWeight: '500', letterSpacing: 0.15 },
    composer: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        gap: spacing.sm,
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.border,
        backgroundColor: colors.background,
    },
    input: {
        flex: 1,
        minHeight: 48,
        maxHeight: 120,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.background,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.md,
        fontSize: 15,
        lineHeight: 22,
        color: colors.foreground,
    },
    sendBtn: {
        width: 44,
        height: 44,
        borderRadius: borderRadius.lg,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.foreground,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.foreground,
    },
    sendBtnDisabled: { backgroundColor: colors.surface, borderColor: colors.border },
    quoteBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.sm,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.border,
        backgroundColor: colors.surface,
        gap: spacing.sm,
    },
    quoteBarText: { color: colors.textMuted, fontSize: 11, fontWeight: '500', flex: 1, letterSpacing: 0.2 },
    quoteBarClose: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
});
