import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
    View, Text, StyleSheet, FlatList, TextInput, TouchableOpacity,
    KeyboardAvoidingView, Platform, ActivityIndicator, Image
} from 'react-native';
import { useNavigation, useRoute, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

interface Message {
    id: string;
    channel_id: string;
    user_id: string;
    user_email: string;
    content: string;
    attachment_url?: string;
    attachment_type?: string;
    created_at: string;
    is_admin: boolean;
    parent_id?: string;
    reactions?: Record<string, string[]>;
}

export default function ChannelChatScreen() {
    const navigation = useNavigation();
    const insets = useSafeAreaInsets();
    const route = useRoute<any>();
    const { channelId, channelName } = route.params;
    const [isAdminOnly, setIsAdminOnly] = useState(route.params.isAdminOnly || false);
    const { user } = useAuth();

    const [messages, setMessages] = useState<Message[]>([]);
    const [loading, setLoading] = useState(true);
    const [messageText, setMessageText] = useState('');
    const [sending, setSending] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [selectedImage, setSelectedImage] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [replyingTo, setReplyingTo] = useState<Message | null>(null);
    const flatListRef = useRef<FlatList>(null);

    const isAdmin = user?.is_admin || false;
    const currentUserId = user?.id;

    // Permission Logic: In admin-only channels, non-admins can ONLY reply
    const canPostTopLevel = !isAdminOnly || isAdmin;

    useFocusEffect(
        useCallback(() => {
            loadMessages();
            const interval = !isSearching ? setInterval(loadMessages, 5000) : null;
            return () => interval && clearInterval(interval);
        }, [channelId, searchQuery, isSearching])
    );

    const loadMessages = async () => {
        try {
            const data = await api.getChannelMessages(channelId, 50, searchQuery);
            setMessages(data.messages || []);
            if (data.is_admin_only !== undefined) {
                setIsAdminOnly(data.is_admin_only);
            }
        } catch (error) {
            console.error("Failed to load messages", error);
        } finally {
            setLoading(false);
        }
    };

    const handlePickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ['images'],
            allowsEditing: true,
            quality: 0.8,
        });

        if (!result.canceled) {
            setSelectedImage(result.assets[0].uri);
        }
    };

    const handleSendMessage = async () => {
        if ((!messageText.trim() && !selectedImage) || sending) return;

        // Guard: Only admins can post top-level in restricted channels
        if (isAdminOnly && !isAdmin && !replyingTo) return;

        setSending(true);
        let attachmentUrl = undefined;
        let attachmentType = undefined;

        try {
            if (selectedImage) {
                setUploading(true);
                const formData = new FormData();
                const filename = selectedImage.split('/').pop() || 'upload.jpg';
                const match = /\.(\w+)$/.exec(filename);
                const type = match ? `image/${match[1]}` : `image`;

                formData.append('file', {
                    uri: selectedImage,
                    name: filename,
                    type,
                } as any);

                const uploadRes = await api.uploadChatFile(formData);
                attachmentUrl = uploadRes.url;
                attachmentType = 'image';
                setUploading(false);
            }

            const result = await api.sendChannelMessage(
                channelId,
                messageText.trim() || (attachmentUrl ? "" : ""),
                replyingTo?.id,
                attachmentUrl,
                attachmentType
            );

            if (result.message) {
                setMessages(prev => [...prev, result.message]);
            }
            setMessageText('');
            setReplyingTo(null);
            setSelectedImage(null);
            setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
        } catch (error) {
            console.error("Failed to send message", error);
        } finally {
            setSending(false);
            setUploading(false);
        }
    };

    const handleToggleReaction = async (messageId: string, emoji: string) => {
        try {
            const result = await api.toggleReaction(channelId, messageId, emoji);
            setMessages(prev => prev.map(m => m.id === messageId ? { ...m, reactions: result.reactions } : m));
        } catch (error) {
            console.error("Failed to toggle reaction", error);
        }
    };

    const formatTime = (dateString: string) => {
        const date = new Date(dateString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    const renderMessage = ({ item, index }: { item: Message; index: number }) => {
        const prevMessage = index > 0 ? messages[index - 1] : null;
        const isSameUser = prevMessage && prevMessage.user_id === item.user_id;
        const isCurrentUser = item.user_id === currentUserId;
        const timeDiff = prevMessage ? (new Date(item.created_at).getTime() - new Date(prevMessage.created_at).getTime()) / 60000 : 999;
        const showFullHeader = !isSameUser || timeDiff > 5 || item.parent_id;

        // Find the message being replied to
        const repliedMessage = item.parent_id ? messages.find(m => m.id === item.parent_id) : null;

        return (
            <View style={[
                styles.messageWrapper,
                isCurrentUser ? styles.userMessageWrapper : styles.otherMessageWrapper,
                !showFullHeader && styles.compactMessage
            ]}>
                {repliedMessage && (
                    <View style={[
                        styles.replyContext,
                        isCurrentUser ? styles.userReplyContext : styles.otherReplyContext
                    ]}>
                        {!isCurrentUser && <View style={styles.replyLine} />}
                        <Text style={styles.replyContextText} numberOfLines={1}>
                            <Text style={styles.replyContextUser}>{repliedMessage.user_email.split('@')[0]}: </Text>
                            {repliedMessage.content}
                        </Text>
                        {isCurrentUser && <View style={[styles.replyLine, { borderLeftWidth: 0, borderRightWidth: 2, marginRight: 0, marginLeft: 8, borderTopRightRadius: 4, borderTopLeftRadius: 0 }]} />}
                    </View>
                )}

                <View style={[
                    styles.messageHeaderRow,
                    isCurrentUser && styles.userMessageHeaderRow
                ]}>
                    {!isCurrentUser && showFullHeader && (
                        <View style={styles.avatarMini}>
                            <Text style={styles.avatarInitial}>{item.user_email[0].toUpperCase()}</Text>
                        </View>
                    )}

                    {!isCurrentUser && !showFullHeader && <View style={{ width: 44 }} />}

                    <View style={[
                        styles.messageContentArea,
                        isCurrentUser ? styles.userContentArea : styles.otherContentArea
                    ]}>
                        <View style={[
                            styles.bubble,
                            isCurrentUser ? styles.userBubble : styles.otherBubble,
                            item.is_admin && styles.adminHighlight
                        ]}>
                            {showFullHeader && !isCurrentUser && (
                                <View style={styles.nameRow}>
                                    <Text style={[styles.userName, item.is_admin && styles.adminName]}>
                                        {item.user_email.split('@')[0]}
                                    </Text>
                                    {item.is_admin && <View style={styles.adminTag}><Text style={styles.adminTagText}>ADMIN</Text></View>}
                                </View>
                            )}

                            {item.content ? (
                                <Text style={[
                                    styles.messageText,
                                    isCurrentUser && styles.userMessageText
                                ]}>
                                    {item.content}
                                </Text>
                            ) : null}

                            {item.attachment_url && item.attachment_type === 'image' && (
                                <Image
                                    source={{ uri: api.resolveAttachmentUrl(item.attachment_url) }}
                                    style={styles.attachmentImage}
                                    resizeMode="cover"
                                />
                            )}
                        </View>

                        <Text style={[
                            styles.timestamp,
                            isCurrentUser ? styles.userTimestampOutside : styles.otherTimestampOutside
                        ]}>
                            {formatTime(item.created_at)}
                        </Text>

                        {renderReactions(item)}
                    </View>
                </View>

                <View style={[
                    styles.messageActions,
                    isCurrentUser ? styles.userMessageActions : styles.otherMessageActions
                ]}>
                    <TouchableOpacity onPress={() => setReplyingTo(item)} style={styles.actionBtn}>
                        <Ionicons name="arrow-undo" size={16} color={colors.textMuted} />
                    </TouchableOpacity>
                    {!isCurrentUser && (
                        <TouchableOpacity onPress={() => handleToggleReaction(item.id, '🔥')} style={styles.actionBtn}>
                            <Ionicons name="flash" size={16} color={colors.textMuted} />
                        </TouchableOpacity>
                    )}
                </View>
            </View>
        );
    };

    const renderReactions = (message: Message) => {
        if (!message.reactions || Object.keys(message.reactions).length === 0) return null;
        return (
            <View style={styles.reactionsRow}>
                {Object.entries(message.reactions).map(([emoji, userIds]) => {
                    const hasReacted = currentUserId ? userIds.includes(currentUserId) : false;
                    return (
                        <TouchableOpacity
                            key={emoji}
                            onPress={() => handleToggleReaction(message.id, emoji)}
                            style={[styles.reactionBadge, hasReacted && styles.reactionBadgeActive]}
                        >
                            <Text style={styles.reactionEmoji}>{emoji}</Text>
                            <Text style={[styles.reactionCount, hasReacted && styles.reactionCountActive]}>{userIds.length}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>
        );
    };

    if (loading && messages.length === 0) {
        return (
            <View style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color={colors.primaryLight} />
            </View>
        );
    }

    const placeholderText = replyingTo
        ? `Replying to ${replyingTo.user_email}`
        : isAdminOnly && !isAdmin
            ? "Only admins can start announcements"
            : `Message #${channelName}`;

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView
                style={styles.keyboardView}
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
                keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
            >
                {/* Header */}
                <View style={[styles.header, { paddingTop: insets.top + spacing.sm, paddingBottom: spacing.sm }]}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                        <Ionicons name="chevron-back" size={24} color="#FFFFFF" />
                    </TouchableOpacity>

                    {!isSearching ? (
                        <>
                            <View style={styles.headerLeft}>
                                <Text style={styles.channelPrefix}>#</Text>
                                <Text style={styles.channelName}>{channelName}</Text>
                            </View>
                            <TouchableOpacity onPress={() => setIsSearching(true)} style={styles.headerAction}>
                                <Ionicons name="search" size={24} color={colors.textMuted} />
                            </TouchableOpacity>
                        </>
                    ) : (
                        <View style={styles.searchBar}>
                            <TextInput
                                style={styles.searchInput}
                                placeholder="Search messages..."
                                placeholderTextColor={colors.textMuted}
                                value={searchQuery}
                                onChangeText={setSearchQuery}
                                autoFocus
                            />
                            <TouchableOpacity onPress={() => { setIsSearching(false); setSearchQuery(''); }}>
                                <Text style={styles.cancelText}>Cancel</Text>
                            </TouchableOpacity>
                        </View>
                    )}
                </View>

                {/* Messages List */}
                <FlatList
                    ref={flatListRef}
                    data={messages}
                    renderItem={renderMessage}
                    keyExtractor={(item) => item.id}
                    contentContainerStyle={[styles.messagesList, { paddingBottom: insets.bottom + 20 }]}
                    onContentSizeChange={() => {
                        if (!isSearching) flatListRef.current?.scrollToEnd({ animated: false });
                    }}
                    showsVerticalScrollIndicator={false}
                    ListEmptyComponent={
                        <View style={styles.emptyState}>
                            {isSearching ? (
                                <Text style={styles.welcomeSubtitle}>No messages found for "{searchQuery}"</Text>
                            ) : (
                                <>
                                    <Text style={styles.welcomeTitle}>Welcome to #{channelName}!</Text>
                                    <Text style={styles.welcomeSubtitle}>This is the start of the #{channelName} channel.</Text>
                                </>
                            )}
                        </View>
                    }
                />

                {isAdminOnly && !isAdmin && !replyingTo && !isSearching && (
                    <View style={styles.restrictedInfo}>
                        <Ionicons name="information-circle" size={20} color={colors.textMuted} />
                        <Text style={styles.restrictedInfoText}>
                            Only admins can post announcements. You can reply to them to comment.
                        </Text>
                    </View>
                )}

                {/* Input Area */}
                {!isSearching && (isAdmin || !isAdminOnly || replyingTo) && (
                    <View style={[styles.inputWrapper, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
                        {replyingTo && (
                            <View style={styles.replyPreview}>
                                <Text style={styles.replyPreviewText} numberOfLines={1}>
                                    Replying to <Text style={{ fontWeight: 'bold' }}>{replyingTo.user_email}</Text>
                                </Text>
                                <TouchableOpacity onPress={() => setReplyingTo(null)}>
                                    <Ionicons name="close-circle" size={20} color={colors.textMuted} />
                                </TouchableOpacity>
                            </View>
                        )}

                        {selectedImage && (
                            <View style={styles.imagePreviewContainer}>
                                <Image source={{ uri: selectedImage }} style={styles.imagePreview} />
                                <TouchableOpacity style={styles.removeImageBtn} onPress={() => setSelectedImage(null)}>
                                    <Ionicons name="close-circle" size={24} color="#FF3B30" />
                                </TouchableOpacity>
                                {uploading && (
                                    <View style={styles.uploadOverlay}>
                                        <ActivityIndicator color="#FFFFFF" />
                                    </View>
                                )}
                            </View>
                        )}

                        <View style={styles.inputContainer}>
                            <TouchableOpacity style={styles.attachBtn} onPress={handlePickImage} disabled={uploading}>
                                <Ionicons name="add-circle" size={28} color={colors.primaryLight} />
                            </TouchableOpacity>
                            <TextInput
                                style={styles.input}
                                placeholder={placeholderText}
                                placeholderTextColor={colors.textMuted}
                                value={messageText}
                                onChangeText={setMessageText}
                                multiline
                                editable={(canPostTopLevel || !!replyingTo) && !uploading}
                            />
                            <TouchableOpacity
                                style={[styles.sendBtn, (!messageText.trim() && !selectedImage || (!canPostTopLevel && !replyingTo)) && styles.disabledBtn]}
                                onPress={handleSendMessage}
                                disabled={(!messageText.trim() && !selectedImage) || sending || uploading || (!canPostTopLevel && !replyingTo)}
                            >
                                {uploading || sending ? (
                                    <ActivityIndicator size="small" color={colors.primaryLight} />
                                ) : (
                                    <Ionicons name="send" size={20} color={messageText.trim() || selectedImage ? colors.primaryLight : colors.textMuted} />
                                )}
                            </TouchableOpacity>
                        </View>
                    </View>
                )}
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    center: { justifyContent: 'center', alignItems: 'center' },
    keyboardView: { flex: 1 },
    header: {
        backgroundColor: colors.surface,
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(255,255,255,0.05)',
    },
    backButton: { marginRight: spacing.md },
    headerLeft: { flex: 1, flexDirection: 'row', alignItems: 'center' },
    channelPrefix: { color: colors.primaryLight, fontSize: 24, fontWeight: '300', marginRight: 4 },
    channelName: { ...typography.h3, color: '#FFFFFF' },
    headerAction: { padding: spacing.xs },
    searchBar: { flex: 1, flexDirection: 'row', alignItems: 'center' },
    searchInput: { flex: 1, color: '#FFFFFF', fontSize: 16, backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: borderRadius.sm, paddingHorizontal: spacing.sm, height: 40, marginRight: spacing.sm },
    cancelText: { color: colors.primaryLight, fontWeight: '600' },

    messagesList: { paddingHorizontal: spacing.md, paddingTop: spacing.md },
    messageWrapper: { marginBottom: spacing.md, width: '100%' },
    userMessageWrapper: { alignItems: 'flex-end' },
    otherMessageWrapper: { alignItems: 'flex-start' },
    compactMessage: { marginBottom: spacing.xs },

    bubble: {
        padding: spacing.sm,
        borderRadius: borderRadius.lg,
        maxWidth: '85%',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.1,
        shadowRadius: 2,
        elevation: 1,
    },
    userBubble: {
        backgroundColor: colors.primary,
        borderTopRightRadius: 2,
    },
    otherBubble: {
        backgroundColor: colors.surface,
        borderTopLeftRadius: 2,
    },
    adminHighlight: {
        borderWidth: 1.5,
        borderColor: colors.warning,
        backgroundColor: 'rgba(255, 179, 0, 0.1)',
    },

    replyContext: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
    userReplyContext: { alignSelf: 'flex-end', marginRight: 4 },
    otherReplyContext: { alignSelf: 'flex-start', marginLeft: 52 },
    replyLine: { width: 15, height: 10, borderLeftWidth: 2, borderTopWidth: 2, borderColor: colors.border, borderTopLeftRadius: 4, marginRight: 8, marginTop: 4 },
    replyContextText: { color: colors.textSecondary, fontSize: 12 },
    replyContextUser: { fontWeight: '700', color: colors.primaryLight },

    messageHeaderRow: { flexDirection: 'row', width: '100%' },
    userMessageHeaderRow: { flexDirection: 'row-reverse' },
    avatarMini: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.primary, justifyContent: 'center', alignItems: 'center', marginRight: spacing.sm, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
    avatarInitial: { color: '#FFFFFF', fontWeight: 'bold', fontSize: 14 },
    messageContentArea: { flexShrink: 1 },
    userContentArea: { alignItems: 'flex-end' },
    otherContentArea: { flex: 1 },
    nameRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
    userName: { color: colors.primaryLight, fontWeight: 'bold', fontSize: 13 },
    adminName: { color: colors.warning },
    adminTag: { backgroundColor: colors.primary, paddingHorizontal: 4, borderRadius: 4, marginLeft: 8 },
    adminTagText: { color: '#FFFFFF', fontSize: 10, fontWeight: 'bold' },
    timestamp: { color: colors.textMuted, fontSize: 10, marginTop: 4 },
    userTimestampOutside: { alignSelf: 'flex-end', marginRight: 4 },
    otherTimestampOutside: { alignSelf: 'flex-start', marginLeft: 4 },
    messageText: { color: colors.textPrimary, fontSize: 15, lineHeight: 22 },
    userMessageText: { color: '#FFFFFF' },
    attachmentImage: {
        width: '100%',
        aspectRatio: 1.33,
        borderRadius: borderRadius.md,
        marginTop: spacing.xs,
        backgroundColor: colors.surfaceLight,
        maxWidth: 280,
    },
    messageActions: { flexDirection: 'row', gap: spacing.sm, marginTop: 4 },
    userMessageActions: { alignSelf: 'flex-end' },
    otherMessageActions: { paddingLeft: 52 },
    actionBtn: { padding: 4 },

    compactMessageRow: { flexDirection: 'row', width: '100%' },
    userCompactRow: { flexDirection: 'row-reverse' },
    compactTime: { color: colors.textMuted, fontSize: 9, width: 40, marginTop: 8, textAlign: 'center' },
    userCompactTime: { marginLeft: 4 },
    otherCompactTime: { marginRight: 4 },

    reactionsRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 6, gap: 4 },
    reactionBadge: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surfaceLight, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)' },
    reactionBadgeActive: { backgroundColor: 'rgba(109, 55, 212, 0.2)', borderColor: colors.primaryLight },
    reactionEmoji: { fontSize: 14 },
    reactionCount: { fontSize: 12, color: colors.textSecondary, marginLeft: 4 },
    reactionCountActive: { color: colors.primaryLight, fontWeight: 'bold' },

    emptyState: { padding: spacing.xxl, alignItems: 'center' },
    welcomeTitle: { ...typography.h2, color: '#FFFFFF', textAlign: 'center', marginBottom: spacing.sm },
    welcomeSubtitle: { ...typography.bodySmall, color: colors.textMuted, textAlign: 'center' },

    inputWrapper: { paddingHorizontal: spacing.md, paddingTop: spacing.xs, backgroundColor: colors.background },
    replyPreview: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: colors.surface, padding: spacing.sm, borderTopLeftRadius: borderRadius.md, borderTopRightRadius: borderRadius.md, borderBottomWidth: 1, borderBottomColor: colors.border },
    replyPreviewText: { color: colors.textSecondary, fontSize: 12 },
    imagePreviewContainer: { position: 'relative', marginBottom: spacing.sm, alignSelf: 'flex-start' },
    imagePreview: { width: 100, height: 100, borderRadius: borderRadius.md },
    removeImageBtn: { position: 'absolute', top: -10, right: -10, backgroundColor: '#FFFFFF', borderRadius: 12 },
    uploadOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', borderRadius: borderRadius.md },
    inputContainer: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: borderRadius.xl, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)' },
    attachBtn: { padding: 4 },
    input: { flex: 1, color: '#FFFFFF', paddingHorizontal: spacing.sm, fontSize: 16, maxHeight: 120, minHeight: 40 },
    sendBtn: { padding: 8 },
    disabledBtn: { opacity: 0.3 },
    restrictedInfo: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        padding: spacing.md,
        backgroundColor: colors.surface,
        borderTopWidth: 1,
        borderTopColor: 'rgba(255,255,255,0.05)',
        gap: 8,
    },
    restrictedInfoText: {
        color: colors.textMuted,
        fontSize: 12,
        fontWeight: '500',
    },
});
