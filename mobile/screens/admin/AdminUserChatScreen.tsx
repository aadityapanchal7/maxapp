import React, { useState, useEffect, useRef } from 'react';
import {
    View, Text, StyleSheet, TextInput, TouchableOpacity,
    FlatList, KeyboardAvoidingView, Platform, ActivityIndicator
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

export default function AdminUserChatScreen({ route, navigation }: any) {
    const { userId, userEmail } = route.params;
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [initialLoading, setInitialLoading] = useState(true);
    const flatListRef = useRef<FlatList>(null);

    useEffect(() => {
        loadHistory();
    }, []);

    const loadHistory = async () => {
        try {
            const data = await api.getAdminUserChat(userId);
            setMessages(data.messages || []);
        } catch (error) {
            console.error('Failed to load chat:', error);
        } finally {
            setInitialLoading(false);
        }
    };

    const sendMessage = async () => {
        if (!input.trim() || loading) return;

        const text = input.trim();
        setInput('');
        setLoading(true);

        // Optimistic UI — show message immediately
        setMessages(prev => [...prev, { role: 'assistant', content: text }]);

        try {
            await api.sendAdminUserChat(userId, text);
        } catch (error) {
            console.error('Failed to send:', error);
            // Remove optimistic message on failure
            setMessages(prev => prev.slice(0, -1));
        } finally {
            setLoading(false);
        }
    };

    const renderMessage = ({ item }: { item: Message }) => {
        // In admin view: user messages on LEFT, admin/assistant on RIGHT
        const isUser = item.role === 'user';
        return (
            <View style={[styles.messageBubble, isUser ? styles.userBubble : styles.adminBubble]}>
                <Text style={[styles.messageText, !isUser && styles.adminMessageText]}>{item.content}</Text>
            </View>
        );
    };

    return (
        <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
            <KeyboardAvoidingView
                style={styles.keyboardView}
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
                keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
            >
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                        <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>
                    <View style={styles.headerInfo}>
                        <Text style={styles.title} numberOfLines={1}>{userEmail}</Text>
                        <Text style={styles.subtitle}>Replying as Cannon</Text>
                    </View>
                </View>

                {initialLoading ? (
                    <View style={styles.center}>
                        <ActivityIndicator color={colors.primaryLight} />
                    </View>
                ) : messages.length === 0 ? (
                    <View style={styles.center}>
                        <Ionicons name="chatbubble-ellipses-outline" size={48} color={colors.textMuted} />
                        <Text style={styles.emptyText}>No messages yet</Text>
                        <Text style={styles.emptySubtext}>Send a message as Cannon to start the conversation</Text>
                    </View>
                ) : (
                    <FlatList
                        ref={flatListRef}
                        data={messages}
                        renderItem={renderMessage}
                        keyExtractor={(_, i) => i.toString()}
                        contentContainerStyle={styles.messageList}
                        onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
                        showsVerticalScrollIndicator={false}
                    />
                )}

                <View style={styles.inputContainer}>
                    <TextInput
                        style={styles.input}
                        placeholder="Reply as Cannon..."
                        placeholderTextColor="rgba(255,255,255,0.5)"
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
                        {loading ? (
                            <ActivityIndicator size="small" color="#000000" />
                        ) : (
                            <Ionicons name="send" size={22} color="#000000" />
                        )}
                    </TouchableOpacity>
                </View>
            </KeyboardAvoidingView>
        </LinearGradient>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1 },
    keyboardView: { flex: 1 },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingTop: 50,
        paddingHorizontal: spacing.md,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(255,255,255,0.1)',
    },
    backBtn: { padding: 8, marginRight: 8 },
    headerInfo: { flex: 1 },
    title: { ...typography.h2, color: '#FFFFFF', fontSize: 18 },
    subtitle: { ...typography.caption, color: colors.primaryLight, fontWeight: '600' },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.xl },
    emptyText: { ...typography.body, color: colors.textMuted, marginTop: spacing.md },
    emptySubtext: { ...typography.caption, color: colors.textMuted, marginTop: 4, textAlign: 'center' },
    messageList: { padding: spacing.lg, paddingBottom: spacing.xl },
    messageBubble: {
        maxWidth: '80%',
        padding: spacing.md,
        borderRadius: borderRadius.lg,
        marginBottom: spacing.sm,
    },
    userBubble: {
        alignSelf: 'flex-start',
        backgroundColor: 'rgba(255,255,255,0.12)',
    },
    adminBubble: {
        alignSelf: 'flex-end',
        backgroundColor: '#FFFFFF',
    },
    messageText: { ...typography.body, color: '#FFFFFF' },
    adminMessageText: { color: '#000000' },
    inputContainer: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        padding: spacing.md,
        borderTopWidth: 1,
        borderTopColor: 'rgba(255,255,255,0.1)',
    },
    input: {
        flex: 1,
        backgroundColor: 'rgba(255,255,255,0.1)',
        borderRadius: borderRadius.md,
        padding: spacing.md,
        color: '#FFFFFF',
        maxHeight: 100,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.2)',
    },
    sendButton: {
        width: 48,
        height: 48,
        borderRadius: 24,
        backgroundColor: '#FFFFFF',
        justifyContent: 'center',
        alignItems: 'center',
        marginLeft: spacing.sm,
    },
    disabledButton: { opacity: 0.5 },
});
