import React, { useState, useEffect, useRef } from 'react';
import { AppState, type AppStateStatus, View, Text, StyleSheet, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { FlashList, FlashListRef } from '@shopify/flash-list';
import { Ionicons } from '@expo/vector-icons';
import { useRoute } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { useChatHistoryQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { ChatTypingIndicator, ChatTypingMode } from '../../components/ChatTypingIndicator';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { CachedImage } from '../../components/CachedImage';

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
    const queryClient = useQueryClient();
    const chatHistoryQuery = useChatHistoryQuery();
    const [messages, setMessages] = useState<Message[]>([]);
    const [historySeeded, setHistorySeeded] = useState(false);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [serverChoices, setServerChoices] = useState<string[]>([]);
    const flatListRef = useRef<FlashListRef<Message>>(null);
    const initScheduleHandled = useRef(false);
    const initQuestionHandled = useRef<string | null>(null);
    const appStateRef = useRef<AppStateStatus>(AppState.currentState);
    /** Prevents auto "start schedule" running before history fetch finishes (otherwise setMessages(history) wipes the optimistic user line). */
    const [historyReady, setHistoryReady] = useState(false);

    useEffect(() => {
        // #region agent log
        fetch('http://127.0.0.1:7566/ingest/6f717954-8152-4e14-9416-684887fdea59',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'da450c'},body:JSON.stringify({sessionId:'da450c',location:'MaxChatScreen.tsx:historyEffect',message:'chat history query state',data:{isSuccess:chatHistoryQuery.isSuccess,isError:chatHistoryQuery.isError,isPending:chatHistoryQuery.isPending,historySeeded,dataLen:chatHistoryQuery.data?.length,error:String(chatHistoryQuery.error?.message||'').substring(0,200)},timestamp:Date.now(),hypothesisId:'B'})}).catch(()=>{});
        // #endregion
        if (!chatHistoryQuery.isSuccess || historySeeded) return;
        setMessages(chatHistoryQuery.data ?? []);
        setHistoryReady(true);
        setHistorySeeded(true);
    }, [chatHistoryQuery.isSuccess, chatHistoryQuery.data, historySeeded]);

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

    const sendMessageWithContext = async (msg: string, initContext?: string) => {
        // #region agent log
        fetch('http://127.0.0.1:7566/ingest/6f717954-8152-4e14-9416-684887fdea59',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'da450c'},body:JSON.stringify({sessionId:'da450c',location:'MaxChatScreen.tsx:sendMessageWithContext',message:'sendMessageWithContext called',data:{msg:msg?.substring(0,80),initContext,loading,historyReady},timestamp:Date.now(),hypothesisId:'A,C'})}).catch(()=>{});
        // #endregion
        if (!msg.trim() || loading) return;
        setLoading(true);
        setServerChoices([]);
        setMessages((prev) => [
            ...prev,
            { role: 'user', content: msg },
            { role: 'assistant', content: '', isTyping: true, typingMode: initContext ? 'schedule' : 'default' },
        ]);
        try {
            const { response, choices } = await api.sendChatMessage(msg, undefined, undefined, initContext);
            setMessages(prev => [
                ...prev.filter((m) => !m.isTyping),
                { role: 'assistant', content: response },
            ]);
            setServerChoices(Array.isArray(choices) ? choices : []);
            // Update React Query cache with the new exchange instead of invalidating+refetching
            // the whole history. Saves a roundtrip and avoids the loading spinner flash.
            queryClient.setQueryData<Message[]>(queryKeys.chatHistory, (prev = []) => [
                ...prev,
                { role: 'user', content: msg },
                { role: 'assistant', content: response },
            ]);
        } catch (e: any) {
            console.error('sendMessageWithContext error:', e?.response?.data || e?.message || e);
            // #region agent log
            fetch('http://127.0.0.1:7566/ingest/6f717954-8152-4e14-9416-684887fdea59',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'da450c'},body:JSON.stringify({sessionId:'da450c',location:'MaxChatScreen.tsx:sendMessageWithContext:catch',message:'sendMessageWithContext error',data:{status:e?.response?.status,statusText:e?.response?.statusText,data:JSON.stringify(e?.response?.data)?.substring(0,300),message:e?.message,hasResponse:!!e?.response},timestamp:Date.now(),hypothesisId:'A,D,E'})}).catch(()=>{});
            // #endregion
            const isNetworkErr = !e?.response;
            if (isNetworkErr) {
                await AsyncStorage.setItem(PENDING_CHAT_KEY, JSON.stringify({ msg, initContext })).catch(() => undefined);
                setMessages(prev => [
                    ...prev.filter((m) => !m.isTyping),
                    { role: 'assistant', content: "You\u2019re offline \u2014 your message is saved and I\u2019ll send it the moment you\u2019re back." },
                ]);
            } else {
                setMessages(prev => [
                    ...prev.filter((m) => !m.isTyping),
                    { role: 'assistant', content: 'My thinking was interrupted \u2014 please don\u2019t leave the app while I\u2019m working on your response. Try sending again.' },
                ]);
            }
        } finally {
            setLoading(false);
        }
    };

    // Retry any message that was queued while offline
    useEffect(() => {
        const trySendPending = async () => {
            const raw = await AsyncStorage.getItem(PENDING_CHAT_KEY).catch(() => null);
            if (!raw) return;
            let queued: { msg: string; initContext?: string } | null = null;
            try { queued = JSON.parse(raw); } catch { return; }
            if (!queued?.msg) return;
            await AsyncStorage.removeItem(PENDING_CHAT_KEY).catch(() => undefined);
            sendMessageWithContext(queued.msg, queued.initContext);
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
        // #region agent log
        fetch('http://127.0.0.1:7566/ingest/6f717954-8152-4e14-9416-684887fdea59',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'da450c'},body:JSON.stringify({sessionId:'da450c',location:'MaxChatScreen.tsx:sendMessage',message:'sendMessage called',data:{userContent:userContent?.substring(0,80),fromPreset:!!fromPreset,loading,historyReady},timestamp:Date.now(),hypothesisId:'C'})}).catch(()=>{});
        // #endregion
        if (!userContent || loading) return;
        setLoading(true);
        setServerChoices([]);
        if (!fromPreset) setInput('');
        const scheduleCtx = route.params?.initSchedule as string | undefined;
        setMessages(prev => [
            ...prev,
            { role: 'user', content: userContent },
            { role: 'assistant', content: '', isTyping: true, typingMode: scheduleCtx ? 'schedule' : 'default' },
        ]);
        try {
            const { response, choices } = await api.sendChatMessage(
                userContent,
                undefined,
                undefined,
                scheduleCtx,
            );
            // #region agent log
            fetch('http://127.0.0.1:7566/ingest/6f717954-8152-4e14-9416-684887fdea59',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'da450c'},body:JSON.stringify({sessionId:'da450c',location:'MaxChatScreen.tsx:sendMessage:success',message:'sendMessage got response',data:{responseLen:response?.length,responsePeek:response?.substring(0,100),choicesLen:choices?.length},timestamp:Date.now(),hypothesisId:'D'})}).catch(()=>{});
            // #endregion
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
        } catch (e: any) {
            console.error(e);
            // #region agent log
            fetch('http://127.0.0.1:7566/ingest/6f717954-8152-4e14-9416-684887fdea59',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'da450c'},body:JSON.stringify({sessionId:'da450c',location:'MaxChatScreen.tsx:sendMessage:catch',message:'sendMessage error',data:{status:e?.response?.status,statusText:e?.response?.statusText,data:JSON.stringify(e?.response?.data)?.substring(0,300),message:e?.message,hasResponse:!!e?.response},timestamp:Date.now(),hypothesisId:'A,D,E'})}).catch(()=>{});
            // #endregion
            const isNetworkErr = !e?.response;
            if (isNetworkErr) {
                await AsyncStorage.setItem(PENDING_CHAT_KEY, JSON.stringify({ msg: userContent, initContext: scheduleCtx })).catch(() => undefined);
                setMessages(prev => [
                    ...prev.filter((m) => !m.isTyping),
                    { role: 'assistant', content: "You\u2019re offline \u2014 your message is saved and I\u2019ll send it the moment you\u2019re back." },
                ]);
            } else {
                setMessages(prev => [
                    ...prev.filter((m) => !m.isTyping),
                    { role: 'assistant', content: 'My thinking was interrupted \u2014 please don\u2019t leave the app while I\u2019m working on your response. Try sending again.' },
                ]);
            }
        }
        finally { setLoading(false); }
    };

    const quickReplies = serverChoices
        .map((c) => (typeof c === 'string' ? c.trim() : String(c ?? '').trim()))
        .filter((c) => c.length > 0);

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
        return (
            <View style={[styles.messageRow, item.role === 'user' && styles.userMessageRow]}>
                <View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.assistantBubble]}>
                    {item.content ? <Text style={[styles.messageText, item.role === 'user' && styles.userMessageText]}>{item.content}</Text> : null}
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
                <View style={styles.header}>
                    <Text style={styles.title}>Max</Text>
                    <Text style={styles.subtitle}>Your lookmaxxing coach</Text>
                </View>

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

                <View style={styles.outerInputContainer}>
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
        paddingTop: 64,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.lg,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: colors.card,
    },
    title: { fontSize: 26, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
    subtitle: { fontSize: 14, color: colors.textMuted, marginTop: 4 },
    messageList: { padding: spacing.lg, paddingBottom: spacing.xl },
    messageListEmpty: { flexGrow: 1 },
    messageRow: { flexDirection: 'row', marginBottom: spacing.md, paddingHorizontal: 4 },
    userMessageRow: { justifyContent: 'flex-end' },
    bubble: {
        maxWidth: '82%',
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderRadius: 18,
        ...shadows.sm,
    },
    userBubble: {
        backgroundColor: colors.foreground,
        borderBottomRightRadius: 6,
        ...shadows.md,
    },
    assistantBubble: {
        backgroundColor: colors.card,
        borderBottomLeftRadius: 6,
        borderWidth: 1,
        borderColor: colors.border,
    },
    messageText: { fontSize: 15, lineHeight: 22, color: colors.foreground },
    userMessageText: { color: colors.buttonText },
    typingBubble: { paddingVertical: 10, paddingHorizontal: 16 },
    typingText: { fontSize: 14, color: colors.textMuted, fontStyle: 'italic' },
    attachmentImage: { width: 220, height: 160, borderRadius: 12, marginTop: spacing.sm },
    emptyState: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.xl },
    emptyTitle: { fontSize: 18, fontWeight: '600', color: colors.foreground, marginBottom: 8 },
    emptySubtitle: { fontSize: 14, color: colors.textMuted, textAlign: 'center', lineHeight: 20 },
    outerInputContainer: {
        padding: spacing.md,
        paddingBottom: spacing.lg,
        borderTopWidth: 1,
        borderTopColor: colors.border,
        backgroundColor: colors.background,
    },
    quickReplyRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: spacing.sm,
        marginBottom: spacing.sm,
    },
    quickReplyButton: {
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
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
        borderRadius: 24,
        paddingHorizontal: 14,
        paddingVertical: 8,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
    },
    input: { flex: 1, color: colors.textPrimary, fontSize: 15, paddingVertical: 10, paddingHorizontal: 4, maxHeight: 100 },
    sendButton: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.foreground, justifyContent: 'center', alignItems: 'center', marginLeft: 8, ...shadows.sm },
    disabledButton: { opacity: 0.35 },
});
