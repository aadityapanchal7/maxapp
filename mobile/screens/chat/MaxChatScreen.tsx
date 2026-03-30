import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
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
    const flatListRef = useRef<FlashListRef<Message>>(null);
    const initScheduleHandled = useRef(false);
    /** Prevents auto "start schedule" running before history fetch finishes (otherwise setMessages(history) wipes the optimistic user line). */
    const [historyReady, setHistoryReady] = useState(false);

    const addTyping = (mode: ChatTypingMode = 'default') =>
        setMessages((prev) => [
            ...prev.filter((m) => !m.isTyping),
            { role: 'assistant', content: '', isTyping: true, typingMode: mode },
        ]);
    const removeTyping = () => setMessages((prev) => prev.filter((m) => !m.isTyping));

    useEffect(() => {
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

    const sendMessageWithContext = async (msg: string, initContext?: string) => {
        if (!msg.trim() || loading) return;
        setLoading(true);
        setMessages((prev) => [...prev, { role: 'user', content: msg }]);
        addTyping(initContext ? 'schedule' : 'default');
        try {
            const { response } = await api.sendChatMessage(msg, undefined, undefined, initContext);
            removeTyping();
            setMessages(prev => [...prev, { role: 'assistant', content: response }]);
            void queryClient.invalidateQueries({ queryKey: queryKeys.chatHistory });
        } catch (e: any) {
            console.error('sendMessageWithContext error:', e?.response?.data || e?.message || e);
            removeTyping();
            setMessages(prev => [...prev, { role: 'assistant', content: 'sorry, something went wrong. try again.' }]);
        } finally {
            setLoading(false);
        }
    };

    const sendMessage = async () => {
        if (!input.trim() || loading) return;
        const userContent = input.trim();
        setLoading(true); setInput('');
        try {
            setMessages(prev => [...prev, { role: 'user', content: userContent }]);
            const scheduleCtx = route.params?.initSchedule as string | undefined;
            addTyping(scheduleCtx ? 'schedule' : 'default');
            const { response } = await api.sendChatMessage(
                userContent,
                undefined,
                undefined,
                scheduleCtx,
            );
            removeTyping();
            setMessages(prev => [...prev, { role: 'assistant', content: response }]);
            void queryClient.invalidateQueries({ queryKey: queryKeys.chatHistory });
        } catch (e) { console.error(e); removeTyping(); setMessages(prev => [...prev, { role: 'assistant', content: 'sorry, something went wrong.' }]); }
        finally { setLoading(false); }
    };

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
                            onPress={sendMessage}
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
