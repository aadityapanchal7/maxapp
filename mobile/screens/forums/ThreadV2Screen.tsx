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
};

export default function ThreadV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const route = useRoute<any>();
    const params = route.params ?? {};
    const threadId = params.threadId as string;
    const threadTitle = (params.threadTitle as string) ?? 'thread';

    const [sort, setSort] = useState<'new' | 'top'>('new');
    const [text, setText] = useState('');
    const [sending, setSending] = useState(false);
    const [quotePostId, setQuotePostId] = useState<string | null>(null);
    const [watching, setWatching] = useState(false);
    const [watchLoading, setWatchLoading] = useState(false);
    const listRef = useRef<FlashListRef<Post>>(null);

    const postsQ = useForumV2PostsQuery({ threadId, sort });
    const serverPosts: Post[] = useMemo(() => (postsQ.data?.posts ?? []) as Post[], [postsQ.data]);
    const [posts, setPosts] = useState<Post[]>([]);
    const loading = postsQ.isPending && posts.length === 0;

    useEffect(() => {
        setPosts(serverPosts);
    }, [serverPosts]);

    const submit = async () => {
        const msg = text.trim();
        if (!msg) return;
        setSending(true);
        try {
            await api.replyForumV2Thread(threadId, { content: msg, quote_post_id: quotePostId ?? undefined });
            setText('');
            setQuotePostId(null);
            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Posts(threadId, sort) });
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
            Alert.alert('error', 'couldn\'t update watch');
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

        // instant UI update
        setPosts((prev) => prev.map((p) => (p.id === postId ? applyOptimisticVote(p, value) : p)));
        try {
            const res = await api.voteForumV2Post(postId, value);
            // reconcile counts from server response if available
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

            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Posts(threadId, sort) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Posts(threadId, 'new') });
            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Posts(threadId, 'top') });
        } catch (e: any) {
            // rollback
            setPosts((prev) => prev.map((p) => (p.id === postId ? before : p)));
        }
    };

    const renderPost = ({ item }: { item: Post }) => {
        const mentions = (item.entities?.mentions || []) as string[];
        const quoted = item.entities?.quote_post_id as string | undefined;
        const upActive = item.my_vote === 1;
        const downActive = item.my_vote === -1;
        return (
            <View style={styles.postCard}>
                <View style={styles.postHeader}>
                    <Text style={styles.postUser} numberOfLines={1}>
                        @{item.username || 'user'}
                    </Text>
                    <View style={styles.votePill}>
                        <Ionicons name="arrow-up" size={14} color={upActive ? colors.background : colors.textSecondary} />
                        <Text style={[styles.votePillText, upActive && styles.votePillTextActive]}>
                            {(item.upvotes ?? 0).toString()}
                        </Text>
                        <Ionicons name="arrow-down" size={14} color={downActive ? colors.background : colors.textSecondary} />
                    </View>
                </View>
                {quoted ? <Text style={styles.quoteStub}>quoted post</Text> : null}
                <Text style={styles.postBody}>{item.content}</Text>
                {mentions.length > 0 ? (
                    <Text style={styles.mentions} numberOfLines={1}>
                        mentions: {mentions.map((m) => `@${m}`).join(' ')}
                    </Text>
                ) : null}
                <View style={styles.postActions}>
                    <TouchableOpacity
                        onPress={() => vote(item.id, 1)}
                        style={[styles.voteBtnIcon, upActive && styles.voteBtnIconActive]}
                        activeOpacity={0.85}
                    >
                        <Ionicons name="arrow-up" size={16} color={upActive ? colors.background : colors.textSecondary} />
                    </TouchableOpacity>
                    <TouchableOpacity
                        onPress={() => vote(item.id, -1)}
                        style={[styles.voteBtnIcon, downActive && styles.voteBtnIconActive]}
                        activeOpacity={0.85}
                    >
                        <Ionicons name="arrow-down" size={16} color={downActive ? colors.background : colors.textSecondary} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => setQuotePostId(item.id)} style={styles.actionBtn} activeOpacity={0.8}>
                        <Ionicons name="chatbox-ellipses-outline" size={16} color={colors.textSecondary} />
                        <Text style={styles.actionText}>quote</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                        onPress={async () => {
                            try {
                                const reportRes = await api.reportForumV2Post(item.id, 'reported from app');
                                Alert.alert('reported', reportRes?.message === 'Already reported' ? 'you already reported this post.' : 'thanks. we’ll review it.');
                            } catch {
                                Alert.alert('error', 'couldn’t report');
                            }
                        }}
                        style={styles.actionBtn}
                        activeOpacity={0.8}
                    >
                        <Ionicons name="flag-outline" size={16} color={colors.textSecondary} />
                        <Text style={styles.actionText}>report</Text>
                    </TouchableOpacity>
                </View>
            </View>
        );
    };

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn} activeOpacity={0.8}>
                    <Ionicons name="arrow-back" size={20} color={colors.textSecondary} />
                </TouchableOpacity>
                <View style={{ flex: 1 }}>
                    <Text style={styles.title} numberOfLines={1}>
                        {threadTitle}
                    </Text>
                    <Text style={styles.subtitle}>{posts.length.toString()} posts</Text>
                </View>
                <TouchableOpacity
                    onPress={toggleWatch}
                    disabled={watchLoading}
                    style={[styles.watchBtn, watching && styles.watchBtnActive]}
                    activeOpacity={0.85}
                >
                    <Ionicons name={watching ? 'eye' : 'eye-outline'} size={16} color={watching ? colors.background : colors.textSecondary} />
                </TouchableOpacity>
                <View style={styles.sortRow}>
                    {(['new', 'top'] as const).map((k) => (
                        <TouchableOpacity
                            key={k}
                            style={[styles.sortPill, sort === k && styles.sortPillActive]}
                            onPress={() => setSort(k)}
                            activeOpacity={0.85}
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
                    ref={listRef}
                    data={posts}
                    renderItem={renderPost}
                    keyExtractor={(p) => p.id}
                    contentContainerStyle={styles.list}
                />
            )}

            <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
                {quotePostId ? (
                    <View style={styles.quoteBar}>
                        <Text style={styles.quoteBarText} numberOfLines={1}>
                            quoting a post
                        </Text>
                        <TouchableOpacity onPress={() => setQuotePostId(null)} activeOpacity={0.8}>
                            <Ionicons name="close" size={18} color={colors.textMuted} />
                        </TouchableOpacity>
                    </View>
                ) : null}
                <View style={styles.composer}>
                    <TextInput
                        style={styles.input}
                        placeholder="reply..."
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
                        {sending ? <ActivityIndicator size="small" color={colors.background} /> : <Ionicons name="send" size={18} color={colors.background} />}
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
        gap: 12,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: colors.card,
    },
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
    title: { color: colors.foreground, fontSize: 16, fontWeight: '900' },
    subtitle: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
    watchBtn: {
        width: 34,
        height: 34,
        borderRadius: 17,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    watchBtnActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    sortRow: { flexDirection: 'row', gap: 8 },
    sortPill: {
        paddingHorizontal: 10,
        height: 30,
        borderRadius: 15,
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
        alignItems: 'center',
        justifyContent: 'center',
    },
    sortPillActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    sortText: { color: colors.textSecondary, fontSize: 12, fontWeight: '800' },
    sortTextActive: { color: colors.background },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    list: { padding: spacing.lg, paddingBottom: spacing.xl },
    postCard: {
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.lg,
        padding: spacing.lg,
        marginBottom: spacing.md,
        ...shadows.sm,
    },
    postHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    postUser: { color: colors.foreground, fontSize: 13, fontWeight: '900', flex: 1, paddingRight: 10 },
    votePill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingHorizontal: 10,
        height: 26,
        borderRadius: 13,
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    votePillText: { color: colors.textSecondary, fontSize: 12, fontWeight: '900' },
    votePillTextActive: { color: colors.background },
    quoteStub: { color: colors.textMuted, fontSize: 11, marginTop: 8 },
    postBody: { color: colors.foreground, fontSize: 13, lineHeight: 18, marginTop: 10 },
    mentions: { color: colors.textSecondary, fontSize: 11, marginTop: 10 },
    postActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginTop: 12 },
    actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    actionText: { color: colors.textSecondary, fontSize: 12, fontWeight: '800' },
    voteBtnIcon: {
        width: 34,
        height: 34,
        borderRadius: 17,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    voteBtnIconActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    composer: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        gap: 10,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        borderTopWidth: 1,
        borderTopColor: colors.border,
        backgroundColor: colors.card,
    },
    input: {
        flex: 1,
        minHeight: 40,
        maxHeight: 120,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surfaceLight,
        paddingHorizontal: 12,
        paddingVertical: 10,
        color: colors.foreground,
    },
    sendBtn: {
        width: 42,
        height: 42,
        borderRadius: 21,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.foreground,
    },
    sendBtnDisabled: { opacity: 0.45 },
    quoteBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingVertical: 8,
        borderTopWidth: 1,
        borderTopColor: colors.border,
        backgroundColor: colors.surfaceLight,
    },
    quoteBarText: { color: colors.textSecondary, fontSize: 12, fontWeight: '800' },
});

