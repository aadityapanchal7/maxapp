/**
 * Slide-in drawer showing the user's chat threads.
 *
 * Mounted inside MaxChatScreen — a hamburger icon in the header toggles it.
 * Tapping a row switches the active conversation; the "New chat" button
 * creates a fresh thread server-side and surfaces its id to the parent.
 *
 * Intentionally minimal on styling: inherits the dark theme from the rest of
 * the app so the existing chat screen UX isn't disturbed.
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    Modal,
    Platform,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';

import api from '../services/api';
import { queryKeys } from '../lib/queryClient';
import { useChatConversationsQuery } from '../hooks/useAppQueries';
import { colors, spacing, typography } from '../theme/dark';

type Conversation = {
    id: string;
    title: string;
    channel: string;
    is_archived: boolean;
    last_message_at: string | null;
    created_at: string | null;
    updated_at: string | null;
};

export type ChatConversationsDrawerProps = {
    visible: boolean;
    activeConversationId: string | null;
    onClose: () => void;
    onSelect: (conversationId: string) => void;
    onCreated: (conversationId: string) => void;
};

function formatWhen(iso: string | null): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const today = new Date();
    const sameDay =
        d.getFullYear() === today.getFullYear() &&
        d.getMonth() === today.getMonth() &&
        d.getDate() === today.getDate();
    if (sameDay) {
        return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function ChatConversationsDrawer({
    visible,
    activeConversationId,
    onClose,
    onSelect,
    onCreated,
}: ChatConversationsDrawerProps) {
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const convQuery = useChatConversationsQuery();

    const [creating, setCreating] = useState(false);
    const [renamingId, setRenamingId] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState('');

    const conversations: Conversation[] = useMemo(
        () => (convQuery.data ?? []) as Conversation[],
        [convQuery.data]
    );

    const invalidate = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.chatConversations });
    }, [queryClient]);

    const handleNewChat = useCallback(async () => {
        if (creating) return;
        setCreating(true);
        try {
            const { conversation } = await api.createChatConversation();
            invalidate();
            onCreated(conversation.id);
            onClose();
        } catch (e: any) {
            Alert.alert('Could not start a new chat', e?.message || 'Please try again.');
        } finally {
            setCreating(false);
        }
    }, [creating, invalidate, onClose, onCreated]);

    const handleSelect = useCallback(
        (id: string) => {
            onSelect(id);
            onClose();
        },
        [onClose, onSelect]
    );

    const startRename = useCallback((conv: Conversation) => {
        setRenamingId(conv.id);
        setRenameValue(conv.title);
    }, []);

    const commitRename = useCallback(async () => {
        if (!renamingId) return;
        const title = renameValue.trim();
        if (!title) {
            setRenamingId(null);
            return;
        }
        try {
            await api.renameChatConversation(renamingId, title);
            invalidate();
        } catch (e: any) {
            Alert.alert('Rename failed', e?.message || 'Please try again.');
        } finally {
            setRenamingId(null);
            setRenameValue('');
        }
    }, [invalidate, renameValue, renamingId]);

    const confirmDelete = useCallback(
        (conv: Conversation) => {
            Alert.alert(
                'Delete chat?',
                `"${conv.title}" will be permanently removed along with all its messages.`,
                [
                    { text: 'Cancel', style: 'cancel' },
                    {
                        text: 'Delete',
                        style: 'destructive',
                        onPress: async () => {
                            try {
                                await api.deleteChatConversation(conv.id);
                                invalidate();
                                if (conv.id === activeConversationId) {
                                    // Caller needs to route to a sibling or create fresh.
                                    onSelect('');
                                }
                            } catch (e: any) {
                                Alert.alert('Delete failed', e?.message || 'Please try again.');
                            }
                        },
                    },
                ]
            );
        },
        [activeConversationId, invalidate, onSelect]
    );

    return (
        <Modal
            animationType="fade"
            transparent
            visible={visible}
            onRequestClose={onClose}
        >
            <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="Close chat list" />
            <View
                style={[
                    styles.drawer,
                    {
                        paddingTop: Math.max(insets.top + spacing.md, 44),
                        paddingBottom: Math.max(insets.bottom, spacing.md),
                    },
                ]}
            >
                <View style={styles.drawerHeader}>
                    <Text style={styles.drawerTitle}>Your chats</Text>
                    <TouchableOpacity onPress={onClose} accessibilityLabel="Close">
                        <Ionicons name="close" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                </View>

                <TouchableOpacity
                    style={styles.newChatButton}
                    onPress={handleNewChat}
                    activeOpacity={0.8}
                    disabled={creating}
                >
                    <Ionicons name="add" size={18} color={colors.foreground} style={{ marginRight: 8 }} />
                    <Text style={styles.newChatText}>
                        {creating ? 'Starting…' : 'New chat'}
                    </Text>
                </TouchableOpacity>

                <ScrollView style={styles.list} contentContainerStyle={{ paddingBottom: spacing.lg }}>
                    {convQuery.isPending && conversations.length === 0 && (
                        <View style={styles.centered}>
                            <ActivityIndicator color={colors.foreground} />
                        </View>
                    )}
                    {!convQuery.isPending && conversations.length === 0 && (
                        <View style={styles.centered}>
                            <Text style={styles.empty}>No chats yet — tap New chat to start.</Text>
                        </View>
                    )}
                    {conversations.map((conv) => {
                        const isActive = conv.id === activeConversationId;
                        const isRenaming = renamingId === conv.id;
                        return (
                            <View
                                key={conv.id}
                                style={[styles.row, isActive && styles.rowActive]}
                            >
                                {isRenaming ? (
                                    <View style={styles.renameWrap}>
                                        <TextInput
                                            style={styles.renameInput}
                                            value={renameValue}
                                            onChangeText={setRenameValue}
                                            autoFocus
                                            onBlur={commitRename}
                                            onSubmitEditing={commitRename}
                                            returnKeyType="done"
                                            placeholder="Chat title"
                                            placeholderTextColor={colors.textMuted}
                                            maxLength={60}
                                        />
                                    </View>
                                ) : (
                                    <TouchableOpacity
                                        style={styles.rowMain}
                                        onPress={() => handleSelect(conv.id)}
                                        onLongPress={() => startRename(conv)}
                                        activeOpacity={0.7}
                                    >
                                        <Text style={styles.rowTitle} numberOfLines={1}>
                                            {conv.title || 'new chat'}
                                        </Text>
                                        <Text style={styles.rowMeta}>
                                            {formatWhen(conv.last_message_at || conv.created_at)}
                                        </Text>
                                    </TouchableOpacity>
                                )}
                                <TouchableOpacity
                                    style={styles.rowAction}
                                    onPress={() => confirmDelete(conv)}
                                    accessibilityLabel="Delete chat"
                                >
                                    <Ionicons name="trash-outline" size={18} color={colors.textMuted} />
                                </TouchableOpacity>
                            </View>
                        );
                    })}
                </ScrollView>
            </View>
        </Modal>
    );
}

const DRAWER_WIDTH = Platform.select({ default: 320, web: 360 }) ?? 320;

const styles = StyleSheet.create({
    backdrop: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(0,0,0,0.55)',
    },
    drawer: {
        position: 'absolute',
        top: 0,
        bottom: 0,
        left: 0,
        width: DRAWER_WIDTH,
        backgroundColor: '#0E0E10',
        paddingHorizontal: spacing.md,
        shadowColor: '#000',
        shadowOpacity: 0.4,
        shadowRadius: 20,
        elevation: 8,
    },
    drawerHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.md,
    },
    drawerTitle: {
        color: colors.foreground,
        fontSize: typography.title?.fontSize ?? 20,
        fontWeight: '700',
    },
    newChatButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 10,
        borderRadius: 10,
        backgroundColor: '#1C1C1F',
        marginBottom: spacing.md,
    },
    newChatText: {
        color: colors.foreground,
        fontSize: 15,
        fontWeight: '600',
    },
    list: {
        flex: 1,
    },
    centered: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: spacing.xl,
    },
    empty: {
        color: colors.textMuted,
        fontSize: 14,
        textAlign: 'center',
    },
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 10,
        paddingHorizontal: 10,
        borderRadius: 8,
        marginBottom: 4,
    },
    rowActive: {
        backgroundColor: '#1F1F23',
    },
    rowMain: {
        flex: 1,
    },
    rowTitle: {
        color: colors.foreground,
        fontSize: 15,
        fontWeight: '500',
    },
    rowMeta: {
        color: colors.textMuted,
        fontSize: 12,
        marginTop: 2,
    },
    rowAction: {
        paddingHorizontal: 8,
        paddingVertical: 6,
    },
    renameWrap: {
        flex: 1,
    },
    renameInput: {
        color: colors.foreground,
        fontSize: 15,
        paddingVertical: 6,
        paddingHorizontal: 8,
        borderWidth: 1,
        borderColor: '#2A2A2F',
        borderRadius: 6,
    },
});
