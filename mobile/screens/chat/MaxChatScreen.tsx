import React, { useState, useEffect, useRef, useCallback } from 'react';
import { AppState, type AppStateStatus, View, Text, StyleSheet, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator, Linking } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { FlashList, FlashListRef } from '@shopify/flash-list';
import { Ionicons } from '@expo/vector-icons';
import { useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { useChatHistoryQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { ChatTypingIndicator, ChatTypingMode } from '../../components/ChatTypingIndicator';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { CachedImage } from '../../components/CachedImage';
import ChatConversationsDrawer from '../../components/ChatConversationsDrawer';

const PENDING_CHAT_KEY = '@max_pending_chat_v1';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  attachment_url?: string;
  attachment_type?: string;
  isTyping?: boolean;
  typingMode?: ChatTypingMode;
}

export default function MaxChatScreen() {
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
    const chatHistoryQuery = useChatHistoryQuery(activeConversationId);
    const [messages, setMessages] = useState<Message[]>([]);
    /** Keys on the active conversation so switching threads forces a re-seed
     *  from the query data (prevents stale messages from the previous thread). */
    const [seededForConversation, setSeededForConversation] = useState<string | null>(null);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [serverChoices, setServerChoices] = useState<string[]>([]);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const flatListRef = useRef<FlashListRef<Message>>(null);
    const initScheduleHandled = useRef(false);
    const initQuestionHandled = useRef<string | null>(null);
    const appStateRef = useRef<AppStateStatus>(AppState.currentState);
    /** Prevents auto "start schedule" running before history fetch finishes (otherwise setMessages(history) wipes the optimistic user line). */
    const [historyReady, setHistoryReady] = useState(false);

    useEffect(() => {
        if (!chatHistoryQuery.isSuccess) return;
        const data = chatHistoryQuery.data;
        // data shape was Message[] pre-multi-chat; now {messages, conversationId}.
        const msgs: Message[] = Array.isArray(data) ? data : data?.messages ?? [];
        const resolvedId: string | null =
            Array.isArray(data) ? null : data?.conversationId ?? null;

        // Seed once per conversation. Avoids wiping in-flight optimistic turns
        // when React Query refetches without a thread change.
        const keyFor = activeConversationId ?? resolvedId ?? '__default__';
        if (seededForConversation === keyFor) return;

        setMessages(msgs);
        setSeededForConversation(keyFor);
        setHistoryReady(true);
        if (!activeConversationId && resolvedId) {
            setActiveConversationId(resolvedId);
        }
    }, [chatHistoryQuery.isSuccess, chatHistoryQuery.data, activeConversationId, seededForConversation]);

    useEffect(() => {
        if (chatHistoryQuery.isError) {
            setHistoryReady(true);
        }
    }, [chatHistoryQuery.isError]);

    useEffect(() => {
        const initSchedule = route.params?.initSchedule;
        if (!initSchedule || !historyReady) return;
        if (initScheduleHandled.current === initSchedule) return;
        if (loading) return;
        initScheduleHandled.current = initSchedule;
        const maxxLabel = initSchedule.charAt(0).toUpperCase() + initSchedule.slice(1).replace('max', 'Max');
        sendMessageWithContext(
            `I want to start my ${maxxLabel} schedule.`,
            initSchedule,
            'start_schedule',
        );
    }, [route.params?.initSchedule, loading, historyReady]);

    useEffect(() => {
        const initQuestion = route.params?.initQuestion as string | undefined;
        if (!initQuestion || !historyReady) return;
        if (initQuestionHandled.current === initQuestion) return;
        if (loading) return;
        initQuestionHandled.current = initQuestion;
        sendMessageWithContext(initQuestion);
    }, [route.params?.initQuestion, loading, historyReady]);

    const sendMessageWithContext = async (msg: string, initContext?: string, chatIntent?: string) => {
        if (!msg.trim() || loading) return;
        setLoading(true);
        setServerChoices([]);
        setMessages((prev) => [
            ...prev,
            { role: 'user', content: msg },
            { role: 'assistant', content: '', isTyping: true, typingMode: initContext ? 'schedule' : 'default' },
        ]);
        try {
            const { response, choices, conversation_id } = await api.sendChatMessage(
                msg,
                undefined,
                undefined,
                initContext,
                chatIntent,
                activeConversationId ?? undefined,
            );
            // Adopt the server-assigned conversation on first message so the
            // mobile client stays aligned with backend routing (no second call).
            if (conversation_id && conversation_id !== activeConversationId) {
                setActiveConversationId(conversation_id);
            }
            setMessages(prev => [
                ...prev.filter((m) => !m.isTyping),
                { role: 'assistant', content: response },
            ]);
            setServerChoices(Array.isArray(choices) ? choices : []);
            // Invalidate the conversations list so the sidebar reorders + renames.
            queryClient.invalidateQueries({ queryKey: queryKeys.chatConversations });
            queryClient.invalidateQueries({
                predicate: (q) => {
                    const k = q.queryKey;
                    return k === queryKeys.schedulesActiveFull
                        || k === queryKeys.activeSchedulesSummary
                        || k === queryKeys.maxes;
                },
            });
        } catch (e: any) {
            console.error('sendMessageWithContext error:', e?.response?.data || e?.message || e);
            const serverMsg = e?.response?.data?.response || e?.response?.data?.detail;
            setMessages(prev => [
                ...prev.filter((m) => !m.isTyping),
                { role: 'assistant', content: serverMsg || 'Something went wrong — try sending again in a moment.' },
            ]);
        } finally {
            setLoading(false);
        }
    };

    // Retry any message that was queued while offline
    useEffect(() => {
        const trySendPending = async () => {
            const raw = await AsyncStorage.getItem(PENDING_CHAT_KEY).catch(() => null);
            if (!raw) return;
            let queued: { msg: string; initContext?: string; chatIntent?: string } | null = null;
            try { queued = JSON.parse(raw); } catch { return; }
            if (!queued?.msg) return;
            await AsyncStorage.removeItem(PENDING_CHAT_KEY).catch(() => undefined);
            sendMessageWithContext(queued.msg, queued.initContext, queued.chatIntent);
        };
        const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
            const prev = appStateRef.current;
            appStateRef.current = next;
            if (prev.match(/inactive|background/) && next === 'active') {
                void trySendPending();
            }
        });
        // Also check on mount (cold start)
        void trySendPending();
        return () => sub.remove();
    }, []);

    const sendMessage = async (presetArg?: unknown) => {
        const fromPreset = typeof presetArg === 'string' ? presetArg.trim() : '';
        const fromInput = String(input ?? '').trim();
        const userContent = fromPreset || fromInput;
        if (!userContent || loading) return;
        setLoading(true);
        setServerChoices([]);
        if (!fromPreset) setInput('');
        setMessages(prev => [
            ...prev,
            { role: 'user', content: userContent },
            { role: 'assistant', content: '', isTyping: true, typingMode: 'default' },
        ]);
        try {
            const { response, choices } = await api.sendChatMessage(
                userContent,
                undefined,
                undefined,
            );
            setMessages(prev => [
                ...prev.filter((m) => !m.isTyping),
                { role: 'assistant', content: response },
            ]);
            setServerChoices(Array.isArray(choices) ? choices : []);
            queryClient.setQueryData<Message[]>(queryKeys.chatHistory, (prev = []) => [
                ...prev,
                { role: 'user', content: userContent },
                { role: 'assistant', content: response },
            ]);
            queryClient.invalidateQueries({
                predicate: (q) => {
                    const k = q.queryKey;
                    return k === queryKeys.schedulesActiveFull
                        || k === queryKeys.activeSchedulesSummary
                        || k === queryKeys.maxes;
                },
            });
        } catch (e: any) {
            console.error(e);
            const serverMsg = e?.response?.data?.response || e?.response?.data?.detail;
            if (!e?.response) {
                await AsyncStorage.setItem(PENDING_CHAT_KEY, JSON.stringify({ msg: userContent })).catch(() => undefined);
            }
            setMessages(prev => [
                ...prev.filter((m) => !m.isTyping),
                { role: 'assistant', content: serverMsg || 'Something went wrong — try sending again in a moment.' },
            ]);
        }
        finally { setLoading(false); }
    };

    const quickReplies = serverChoices
        .map((c) => (typeof c === 'string' ? c.trim() : String(c ?? '').trim()))
        .filter((c) => c.length > 0);

    const openUrl = useCallback((url: string) => {
        Linking.openURL(url).catch(() => undefined);
    }, []);

    const extractProductLinks = useCallback((text: string): { label: string; url: string }[] => {
        const links: { label: string; url: string }[] = [];
        const oldFormat = /^-\s*(.+?):\s*(https?:\/\/\S+)/gm;
        let m: RegExpExecArray | null;
        while ((m = oldFormat.exec(text)) !== null) {
            links.push({ label: m[1].trim(), url: m[2].trim() });
        }
        const mdFormat = /\[([^\]]+)\]\((https?:\/\/www\.amazon\.com\/s\?[^\s)]+)\)/g;
        while ((m = mdFormat.exec(text)) !== null) {
            if (!links.some(l => l.url === m![2])) {
                links.push({ label: m[1].trim(), url: m[2].trim() });
            }
        }
        return links;
    }, []);

    const stripProductLinkLines = useCallback((text: string): string => {
        return text.replace(/^-\s*.+?:\s*https?:\/\/\S+\s*$/gm, '').replace(/\n{3,}/g, '\n\n').trim();
    }, []);

    const renderLinkedText = useCallback((text: string, baseStyle: any) => {
        const splitRe = /(\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s)]+)/g;
        const parts = text.split(splitRe);
        if (parts.length <= 1) return <Text style={baseStyle}>{text}</Text>;
        const mdLinkRe = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/;
        const bareUrlRe = /^https?:\/\//;
        return (
            <Text style={baseStyle}>
                {parts.map((part, i) => {
                    const mdMatch = mdLinkRe.exec(part);
                    if (mdMatch) {
                        return (
                            <Text key={i} style={styles.linkText} onPress={() => openUrl(mdMatch[2])}>
                                {mdMatch[1]}
                            </Text>
                        );
                    }
                    if (bareUrlRe.test(part)) {
                        return (
                            <Text key={i} style={styles.linkText} onPress={() => openUrl(part)}>
                                {part}
                            </Text>
                        );
                    }
                    return <Text key={i}>{part}</Text>;
                })}
            </Text>
        );
    }, [openUrl]);

    const renderMessage = ({ item }: { item: Message }) => {
        if (item.isTyping) {
            return (
                <View style={styles.messageRow}>
                    <View style={[styles.bubble, styles.assistantBubble, styles.typingBubble]}>
                        <ChatTypingIndicator mode={item.typingMode ?? 'default'} style={styles.typingText} />
                    </View>
                </View>
            );
        }
        if (!item.content?.trim() && !(item.attachment_url && item.attachment_type === 'image')) return null;

        const isAssistant = item.role === 'assistant';
        const productLinks = isAssistant && item.content ? extractProductLinks(item.content) : [];
        const displayText = productLinks.length > 0 ? stripProductLinkLines(item.content!) : item.content;

        return (
            <View style={[styles.messageRow, item.role === 'user' && styles.userMessageRow]}>
                <View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.assistantBubble]}>
                    {displayText ? renderLinkedText(displayText, [styles.messageText, item.role === 'user' && styles.userMessageText]) : null}
                    {productLinks.length > 0 && (
                        <View style={styles.productLinksContainer}>
                            {productLinks.map((link, i) => (
                                <TouchableOpacity
                                    key={i}
                                    style={styles.productLinkButton}
                                    onPress={() => openUrl(link.url)}
                                    activeOpacity={0.7}
                                >
                                    <Ionicons name="cart-outline" size={14} color={colors.foreground} style={{ marginRight: 6 }} />
                                    <Text style={styles.productLinkText} numberOfLines={1}>{link.label}</Text>
                                    <Ionicons name="open-outline" size={12} color={colors.textMuted} style={{ marginLeft: 6 }} />
                                </TouchableOpacity>
                            ))}
                        </View>
                    )}
                    {item.attachment_url && item.attachment_type === 'image' && (
                        <CachedImage uri={api.resolveAttachmentUrl(item.attachment_url)} style={styles.attachmentImage} contentFit="contain" />
                    )}
                </View>
            </View>
        );
    };

    const ListEmpty = () => (
        <View style={styles.emptyState}>
            <Text style={styles.emptyTitle}>Start a conversation</Text>
            <Text style={styles.emptySubtitle}>Ask Max about lookmaxxing, routines, or anything else.</Text>
        </View>
    );

    return (
        <View style={styles.container}>
            {/* Faint chat icon watermark in center background */}
            <View style={styles.watermarkWrap} pointerEvents="none">
                <Ionicons name="chatbubbles" size={140} color={colors.textMuted} style={styles.watermarkIcon} />
            </View>

            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
                <View style={[styles.header, { paddingTop: Math.max(insets.top + spacing.md, 52) }]}>
                    <TouchableOpacity
                        style={styles.headerMenuButton}
                        onPress={() => setDrawerOpen(true)}
                        accessibilityLabel="Open chat list"
                        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                    >
                        <Ionicons name="menu" size={22} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.headerEyebrow}>Coach</Text>
                    <Text style={styles.title}>Max</Text>
                    <Text style={styles.subtitle}>Your lookmaxxing coach</Text>
                </View>

                <ChatConversationsDrawer
                    visible={drawerOpen}
                    activeConversationId={activeConversationId}
                    onClose={() => setDrawerOpen(false)}
                    onSelect={(id) => {
                        // Empty id means the active conversation was deleted — clear
                        // state and let useChatHistoryQuery route to the newest thread
                        // (or show empty state on first-ever use).
                        setActiveConversationId(id || null);
                        setSeededForConversation(null);
                        setMessages([]);
                        setServerChoices([]);
                        queryClient.invalidateQueries({
                            predicate: (q) =>
                                q.queryKey[0] === 'chat' && q.queryKey[1] === 'history',
                        });
                    }}
                    onCreated={(id) => {
                        setActiveConversationId(id);
                        setSeededForConversation(null);
                        setMessages([]);
                        setServerChoices([]);
                    }}
                />

                {!historyReady && chatHistoryQuery.isPending ? (
                    <View style={styles.historyLoading}>
                        <ActivityIndicator size="large" color={colors.foreground} />
                    </View>
                ) : (
                    <FlashList
                        ref={flatListRef}
                        data={messages}
                        renderItem={renderMessage}
                        keyExtractor={(item, i) =>
                            item.isTyping ? `typing-${item.typingMode ?? 'default'}` : i.toString()
                        }
                        contentContainerStyle={[styles.messageList, messages.length === 0 && styles.messageListEmpty]}
                        onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
                        showsVerticalScrollIndicator={false}
                        ListEmptyComponent={ListEmpty}
                    />
                )}

                <View style={[styles.outerInputContainer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
                    {!loading && quickReplies.length > 0 && (
                        <View style={styles.quickReplyRow}>
                            {quickReplies.map((choice) => (
                                <TouchableOpacity
                                    key={choice}
                                    style={styles.quickReplyButton}
                                    onPress={() => sendMessage(choice)}
                                    activeOpacity={0.8}
                                >
                                    <Text style={styles.quickReplyText}>{choice}</Text>
                                </TouchableOpacity>
                            ))}
                        </View>
                    )}
                    <View style={styles.inputContainer}>
                        <TextInput
                            style={styles.input}
                            placeholder="Ask Max anything..."
                            placeholderTextColor={colors.textMuted}
                            value={input}
                            onChangeText={setInput}
                            multiline
                            editable={!loading}
                        />
                        <TouchableOpacity
                            style={[styles.sendButton, !input.trim() && styles.disabledButton]}
                            onPress={() => void sendMessage()}
                            disabled={!input.trim() || loading}
                        >
                            {loading ? <ActivityIndicator size="small" color={colors.buttonText} /> : <Ionicons name="send" size={18} color={colors.buttonText} />}
                        </TouchableOpacity>
                    </View>
                </View>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    keyboardView: { flex: 1 },
    historyLoading: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingVertical: spacing.xxl },
    watermarkWrap: {
        ...StyleSheet.absoluteFillObject,
        justifyContent: 'center',
        alignItems: 'center',
    },
    watermarkIcon: {
        opacity: 0.07,
    },
    header: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.lg,
        borderBottomWidth: 1,
        borderBottomColor: colors.borderLight,
        backgroundColor: colors.card,
        position: 'relative',
    },
    headerMenuButton: {
        position: 'absolute',
        top: 10,
        left: spacing.md,
        zIndex: 2,
        padding: 6,
    },
    headerEyebrow: {
        ...typography.label,
        fontSize: 10,
        color: colors.textMuted,
        marginBottom: 4,
        letterSpacing: 1,
    },
    title: { fontFamily: fonts.serif, fontSize: 28, fontWeight: '400', color: colors.foreground, letterSpacing: -0.5 },
    subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 6, lineHeight: 20 },
    messageList: { padding: spacing.lg, paddingBottom: spacing.xl },
    messageListEmpty: { flexGrow: 1 },
    messageRow: { flexDirection: 'row', marginBottom: spacing.md, paddingHorizontal: 4 },
    userMessageRow: { justifyContent: 'flex-end' },
    bubble: {
        maxWidth: '82%',
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.borderLight,
    },
    userBubble: {
        backgroundColor: colors.foreground,
        borderBottomRightRadius: borderRadius.sm,
        borderColor: colors.foreground,
    },
    assistantBubble: {
        backgroundColor: colors.card,
        borderBottomLeftRadius: borderRadius.sm,
        borderWidth: 1,
        borderColor: colors.border,
    },
    messageText: { fontSize: 15, lineHeight: 22, color: colors.foreground },
    userMessageText: { color: colors.buttonText },
    linkText: { color: '#60A5FA', textDecorationLine: 'underline' },
    productLinksContainer: { marginTop: 10, gap: 6 },
    productLinkButton: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.borderLight,
        borderRadius: borderRadius.md,
        paddingHorizontal: 12,
        paddingVertical: 9,
    },
    productLinkText: {
        flex: 1,
        fontSize: 13,
        fontWeight: '600',
        color: colors.foreground,
    },
    typingBubble: { paddingVertical: 10, paddingHorizontal: 16 },
    typingText: { fontSize: 14, color: colors.textMuted, fontStyle: 'italic' },
    attachmentImage: { width: 220, height: 160, borderRadius: 12, marginTop: spacing.sm },
    emptyState: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.xl },
    emptyTitle: { fontSize: 18, fontWeight: '600', color: colors.foreground, marginBottom: 8 },
    emptySubtitle: { fontSize: 14, color: colors.textMuted, textAlign: 'center', lineHeight: 20 },
    outerInputContainer: {
        padding: spacing.md,
        borderTopWidth: 1,
        borderTopColor: colors.borderLight,
        backgroundColor: colors.card,
    },
    quickReplyRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: spacing.sm,
        marginBottom: spacing.sm,
    },
    quickReplyButton: {
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.borderLight,
        borderRadius: borderRadius.full,
        paddingHorizontal: 14,
        paddingVertical: 9,
    },
    quickReplyText: {
        color: colors.textPrimary,
        fontSize: 13,
        fontWeight: '600',
    },
    inputContainer: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderWidth: 1,
        borderColor: colors.border,
    },
    input: { flex: 1, color: colors.textPrimary, fontSize: 15, paddingVertical: 10, paddingHorizontal: 4, maxHeight: 100 },
    sendButton: {
        width: 40,
        height: 40,
        borderRadius: borderRadius.md,
        backgroundColor: colors.foreground,
        justifyContent: 'center',
        alignItems: 'center',
        marginLeft: 8,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    disabledButton: { opacity: 0.35 },
});
