import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, FlatList, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius } from '../../theme/dark';

interface Message { role: 'user' | 'assistant'; content: string; }

export default function AdminUserChatScreen({ route, navigation }: any) {
    const { userId, userEmail } = route.params;
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [initialLoading, setInitialLoading] = useState(true);
    const flatListRef = useRef<FlatList>(null);

    useEffect(() => { loadHistory(); }, []);

    const loadHistory = async () => {
        try { const data = await api.getAdminUserChat(userId); setMessages(data.messages || []); }
        catch (error) { console.error('Failed to load chat:', error); }
        finally { setInitialLoading(false); }
    };

    const sendMessage = async () => {
        if (!input.trim() || loading) return;
        const text = input.trim();
        setInput(''); setLoading(true);
        setMessages(prev => [...prev, { role: 'assistant', content: text }]);
        try { await api.sendAdminUserChat(userId, text); }
        catch (error) { console.error('Failed to send:', error); setMessages(prev => prev.slice(0, -1)); }
        finally { setLoading(false); }
    };

    const renderMessage = ({ item }: { item: Message }) => {
        const isUser = item.role === 'user';
        return (
            <View style={[styles.messageBubble, isUser ? styles.userBubble : styles.adminBubble]}>
                <Text style={[styles.messageText, !isUser && styles.adminMessageText]}>{item.content}</Text>
            </View>
        );
    };

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                        <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                    </TouchableOpacity>
                    <View style={styles.headerInfo}>
                        <Text style={styles.title} numberOfLines={1}>{userEmail}</Text>
                        <Text style={styles.subtitle}>Replying as Max</Text>
                    </View>
                </View>

                {initialLoading ? (
                    <View style={styles.center}><ActivityIndicator color={colors.foreground} /></View>
                ) : messages.length === 0 ? (
                    <View style={styles.center}>
                        <Text style={styles.emptyText}>No messages yet</Text>
                    </View>
                ) : (
                    <FlatList ref={flatListRef} data={messages} renderItem={renderMessage} keyExtractor={(_, i) => i.toString()} contentContainerStyle={styles.messageList} onContentSizeChange={() => flatListRef.current?.scrollToEnd()} showsVerticalScrollIndicator={false} />
                )}

                <View style={styles.inputContainer}>
                    <TextInput style={styles.input} placeholder="Reply as Max..." placeholderTextColor={colors.textMuted} value={input} onChangeText={setInput} multiline editable={!loading} />
                    <TouchableOpacity style={[styles.sendButton, !input.trim() && styles.disabledButton]} onPress={sendMessage} disabled={!input.trim() || loading}>
                        {loading ? <ActivityIndicator size="small" color={colors.buttonText} /> : <Ionicons name="send" size={18} color={colors.buttonText} />}
                    </TouchableOpacity>
                </View>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    keyboardView: { flex: 1 },
    header: { flexDirection: 'row', alignItems: 'center', paddingTop: 56, paddingHorizontal: spacing.md, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
    backBtn: { padding: 8, marginRight: 8 },
    headerInfo: { flex: 1 },
    title: { fontSize: 16, fontWeight: '600', color: colors.foreground },
    subtitle: { fontSize: 11, color: colors.textMuted, fontWeight: '500', marginTop: 1 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.xl },
    emptyText: { fontSize: 14, color: colors.textMuted, marginTop: spacing.md },
    emptySubtext: { fontSize: 12, color: colors.textMuted, marginTop: 4, textAlign: 'center' },
    messageList: { padding: spacing.lg, paddingBottom: spacing.xl },
    messageBubble: { maxWidth: '80%', padding: spacing.md, borderRadius: borderRadius.lg, marginBottom: spacing.sm },
    userBubble: { alignSelf: 'flex-start', backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    adminBubble: { alignSelf: 'flex-end', backgroundColor: colors.foreground, borderWidth: 1, borderColor: colors.foreground },
    messageText: { fontSize: 14, color: colors.foreground, lineHeight: 20 },
    adminMessageText: { color: colors.buttonText },
    inputContainer: { flexDirection: 'row', alignItems: 'flex-end', padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.borderLight },
    input: {
        flex: 1,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        color: colors.textPrimary,
        maxHeight: 100,
        fontSize: 14,
        borderWidth: 1,
        borderColor: colors.border,
    },
    sendButton: {
        width: 40,
        height: 40,
        borderRadius: borderRadius.md,
        backgroundColor: colors.foreground,
        justifyContent: 'center',
        alignItems: 'center',
        marginLeft: spacing.sm,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    disabledButton: { opacity: 0.3 },
});
