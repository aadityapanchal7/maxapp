import React, { useEffect, useState, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator, Image, NativeSyntheticEvent, TextInputKeyPressEventData } from 'react-native';
import { useNavigation, useRoute, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

interface Message {
    id: string;
    channel_id: string;
    user_id: string;
    user_email: string;
    username?: string;
    user_avatar_url?: string;
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
    const [highlightedId, setHighlightedId] = useState<string | null>(null);
    const [channelDescription, setChannelDescription] = useState<string | null>(null);
    const [channelCategory, setChannelCategory] = useState<string | null>(null);
    const [channelTags, setChannelTags] = useState<string[]>([]);
    const flatListRef = useRef<FlatList>(null);
    const isAdmin = user?.is_admin || false;
    const currentUserId = user?.id;
    const canPostTopLevel = !isAdminOnly || isAdmin;
    const UPVOTE = '\u2B06\uFE0F';
    const DOWNVOTE = '\u2B07\uFE0F';
    const LEGACY_UPVOTE = 'â¬†ï¸';
    const LEGACY_DOWNVOTE = 'â¬‡ï¸';
    const [pendingReactions, setPendingReactions] = useState<Record<string, boolean>>({});

    useFocusEffect(useCallback(() => {
        loadMessages();
        const interval = !isSearching ? setInterval(loadMessages, 2000) : null;
        return () => interval && clearInterval(interval);
    }, [channelId, searchQuery, isSearching]));

    const parseTimestamp = (dateString: string) => {
        if (!dateString) return 0;
        const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(dateString);
        let normalized = dateString;
        if (!normalized.includes('T') && normalized.includes(' ')) {
            normalized = normalized.replace(' ', 'T');
        }
        if (!hasTz) {
            normalized = `${normalized}Z`;
        }
        const time = new Date(normalized).getTime();
        return Number.isNaN(time) ? 0 : time;
    };

    const formatTime = (dateString: string) => {
        const dt = new Date(parseTimestamp(dateString));
        return dt.toLocaleString();
    };

    const loadMessages = async () => {
        try {
            const data = await api.getChannelMessages(channelId, 50, searchQuery);
            const sorted = (data.messages || []).slice().sort((a: Message, b: Message) => {
                const aUp = (a.reactions?.[UPVOTE] || a.reactions?.[LEGACY_UPVOTE] || []).length;
                const aDown = (a.reactions?.[DOWNVOTE] || a.reactions?.[LEGACY_DOWNVOTE] || []).length;
                const bUp = (b.reactions?.[UPVOTE] || b.reactions?.[LEGACY_UPVOTE] || []).length;
                const bDown = (b.reactions?.[DOWNVOTE] || b.reactions?.[LEGACY_DOWNVOTE] || []).length;
                const aScore = aUp - aDown;
                const bScore = bUp - bDown;
                if (aScore !== bScore) return bScore - aScore;
                const at = parseTimestamp(a.created_at);
                const bt = parseTimestamp(b.created_at);
                if (at !== bt) return bt - at;
                return b.id.localeCompare(a.id);
            });
            setMessages(sorted);
            if (data.is_admin_only !== undefined) setIsAdminOnly(data.is_admin_only);
            if (data.channel_description !== undefined) setChannelDescription(data.channel_description);
            if (data.channel_category !== undefined) setChannelCategory(data.channel_category);
            if (data.channel_tags !== undefined) setChannelTags(data.channel_tags || []);
        }
        catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const handlePickImage = async () => { const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, quality: 0.8 }); if (!result.canceled) setSelectedImage(result.assets[0].uri); };

    const handleSendMessage = async () => {
        if ((!messageText.trim() && !selectedImage) || sending) return;
        if (isAdminOnly && !isAdmin && !replyingTo) return;
        setSending(true); let attachmentUrl = undefined; let attachmentType = undefined;
        try {
            if (selectedImage) {
                setUploading(true);
                const formData = new FormData();
                if (Platform.OS === 'web') {
                    const blob = await fetch(selectedImage).then((res) => res.blob());
                    formData.append('file', blob, 'upload.jpg');
                } else {
                    const filename = selectedImage.split('/').pop() || 'upload.jpg';
                    const match = /\.(\w+)$/.exec(filename);
                    formData.append('file', { uri: selectedImage, name: filename, type: match ? `image/${match[1]}` : 'image' } as any);
                }
                const uploadRes = await api.uploadChatFile(formData); attachmentUrl = uploadRes.url; attachmentType = 'image'; setUploading(false);
            }
            const result = await api.sendChannelMessage(channelId, messageText.trim() || '', replyingTo?.id, attachmentUrl, attachmentType);
            if (result.message) {
                setMessages(prev => [...prev, result.message].sort((a, b) => {
                    const aUp = (a.reactions?.[UPVOTE] || a.reactions?.[LEGACY_UPVOTE] || []).length;
                    const aDown = (a.reactions?.[DOWNVOTE] || a.reactions?.[LEGACY_DOWNVOTE] || []).length;
                    const bUp = (b.reactions?.[UPVOTE] || b.reactions?.[LEGACY_UPVOTE] || []).length;
                    const bDown = (b.reactions?.[DOWNVOTE] || b.reactions?.[LEGACY_DOWNVOTE] || []).length;
                    const aScore = aUp - aDown;
                    const bScore = bUp - bDown;
                    if (aScore !== bScore) return bScore - aScore;
                    const at = parseTimestamp(a.created_at);
                    const bt = parseTimestamp(b.created_at);
                    if (at !== bt) return bt - at;
                    return b.id.localeCompare(a.id);
                }));
            }
            setMessageText(''); setReplyingTo(null); setSelectedImage(null);
            setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
        } catch (e) { console.error(e); } finally { setSending(false); setUploading(false); }
    };

    const handleKeyPress = (e: NativeSyntheticEvent<TextInputKeyPressEventData>) => {
        if (Platform.OS !== 'web') return;
        // @ts-ignore - web event has shiftKey
        const shiftKey = (e as any)?.nativeEvent?.shiftKey;
        if (e.nativeEvent.key === 'Enter' && !shiftKey) {
            e.preventDefault?.();
            if (messageText.trim() || selectedImage) {
                handleSendMessage();
            }
        }
    };

    const handleToggleReaction = async (messageId: string, emoji: string) => {
        const reactionKey = `${messageId}:${emoji}`;
        if (pendingReactions[reactionKey]) return;
        setPendingReactions(prev => ({ ...prev, [reactionKey]: true }));
        setMessages(prev => prev.map(m => {
            if (m.id !== messageId) return m;
            const reactions = { ...(m.reactions || {}) } as Record<string, string[]>;
            const userId = currentUserId || '';
            const target = emoji;
            const opposite = emoji === UPVOTE ? DOWNVOTE : emoji === DOWNVOTE ? UPVOTE : null;
            const targetList = new Set(reactions[target] || []);
            if (targetList.has(userId)) {
                targetList.delete(userId);
            } else {
                targetList.add(userId);
            }
            reactions[target] = Array.from(targetList);
            if (opposite) {
                const oppositeList = new Set(reactions[opposite] || []);
                oppositeList.delete(userId);
                if (oppositeList.size) reactions[opposite] = Array.from(oppositeList);
                else delete reactions[opposite];
                delete reactions[emoji === UPVOTE ? LEGACY_DOWNVOTE : LEGACY_UPVOTE];
            }
            delete reactions[emoji === UPVOTE ? LEGACY_UPVOTE : LEGACY_DOWNVOTE];
            return { ...m, reactions };
        }));
        try {
            const result = await api.toggleReaction(channelId, messageId, emoji);
            setMessages(prev => prev.map(m => m.id === messageId ? { ...m, reactions: result.reactions } : m));
        } catch (e) { console.error(e); }
        finally {
            setPendingReactions(prev => {
                const next = { ...prev };
                delete next[reactionKey];
                return next;
            });
        }
    };

    const getDisplayName = (message: Message) => {
        if (message.username && message.username.trim().length > 0) return message.username;
        return message.user_email.split('@')[0];
    };

    const scrollToMessage = (messageId: string) => {
        const index = messages.findIndex((m) => m.id === messageId);
        if (index === -1) return;
        setHighlightedId(messageId);
        flatListRef.current?.scrollToIndex({ index, animated: true });
        setTimeout(() => setHighlightedId(null), 1800);
    };

    const renderMessage = ({ item, index }: { item: Message; index: number }) => {
        const showFullHeader = true;
        const repliedMessage = item.parent_id ? messages.find(m => m.id === item.parent_id) : null;
        const isHighlighted = highlightedId === item.id;
        const isReply = !!item.parent_id;
        const upvotes = (item.reactions?.[UPVOTE] || item.reactions?.[LEGACY_UPVOTE] || []).length;
        const downvotes = (item.reactions?.[DOWNVOTE] || item.reactions?.[LEGACY_DOWNVOTE] || []).length;
        const score = upvotes - downvotes;

        return (
            <View style={[styles.messageRow, isReply && styles.replyRow, isHighlighted && styles.messageHighlight]}>
                <View style={styles.userPanel}>
                    <View style={styles.userAvatarWrap}>
                        {item.user_avatar_url ? (
                            <Image source={{ uri: api.resolveAttachmentUrl(item.user_avatar_url) }} style={styles.userAvatar} />
                        ) : (
                            <View style={styles.avatarMini}>
                                <Text style={styles.avatarInitial}>{getDisplayName(item)[0]?.toUpperCase()}</Text>
                            </View>
                        )}
                    </View>
                    <Text style={styles.userPanelName} numberOfLines={1}>{getDisplayName(item)}</Text>
                    <Text style={styles.userPanelRole}>{item.is_admin ? 'Admin' : 'Member'}</Text>
                </View>
                <View style={styles.contentColumn}>
                    <View style={styles.metaRow}>
                        <Text style={styles.postIndex}>#{index + 1}</Text>
                        <Text style={styles.metaTime}>{formatTime(item.created_at)}</Text>
                        <View style={styles.votePill}>
                            <Text style={styles.voteScore}>{score}</Text>
                        </View>
                    </View>
                    {repliedMessage && (
                        <TouchableOpacity
                            style={styles.replyContext}
                            onPress={() => scrollToMessage(repliedMessage.id)}
                            activeOpacity={0.7}
                        >
                            <Text style={styles.replyContextText} numberOfLines={1}>
                                <Text style={styles.replyContextUser}>{getDisplayName(repliedMessage)}: </Text>
                                {repliedMessage.content}
                            </Text>
                            <Ionicons name="arrow-up" size={14} color={colors.textMuted} />
                        </TouchableOpacity>
                    )}
                    <View style={styles.messageBody}>
                        {item.content ? <Text style={styles.messageText}>{item.content}</Text> : null}
                        {item.attachment_url && item.attachment_type === 'image' && (
                            <Image source={{ uri: api.resolveAttachmentUrl(item.attachment_url) }} style={styles.attachmentImage} resizeMode="cover" />
                        )}
                    </View>
                    {renderReactions(item)}
                    <View style={styles.messageActions}>
                        <TouchableOpacity onPress={() => handleToggleReaction(item.id, UPVOTE)} style={styles.actionBtn} activeOpacity={0.6}>
                            <Ionicons name="arrow-up" size={14} color={colors.textMuted} />
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => handleToggleReaction(item.id, DOWNVOTE)} style={styles.actionBtn} activeOpacity={0.6}>
                            <Ionicons name="arrow-down" size={14} color={colors.textMuted} />
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => setReplyingTo(item)} style={styles.actionBtn} activeOpacity={0.6}>
                            <Ionicons name="arrow-undo" size={14} color={colors.textMuted} />
                        </TouchableOpacity>
                        {item.user_id !== currentUserId && (
                            <TouchableOpacity onPress={() => handleToggleReaction(item.id, '\uD83D\uDD25')} style={styles.actionBtn} activeOpacity={0.6}>
                                <Ionicons name="flash" size={14} color={colors.textMuted} />
                            </TouchableOpacity>
                        )}
                    </View>
                </View>
            </View>
        );
    };

    const renderReactions = (message: Message) => {
        if (!message.reactions || Object.keys(message.reactions).length === 0) return null;
        const entries = Object.entries(message.reactions).map(([emoji, userIds]) => {
            const normalizedEmoji = emoji === LEGACY_UPVOTE ? UPVOTE : emoji === LEGACY_DOWNVOTE ? DOWNVOTE : emoji;
            return [normalizedEmoji, userIds] as [string, string[]];
        });
        return (
            <View style={styles.reactionsRow}>
                {entries.map(([emoji, userIds]) => {
                    const hasReacted = currentUserId ? userIds.includes(currentUserId) : false;
                    return (
                        <TouchableOpacity key={emoji} onPress={() => handleToggleReaction(message.id, emoji)} style={[styles.reactionBadge, hasReacted && styles.reactionBadgeActive]}>
                            <Text style={styles.reactionEmoji}>{emoji}</Text>
                            <Text style={[styles.reactionCount, hasReacted && styles.reactionCountActive]}>{userIds.length}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>
        );
    };

    if (loading && messages.length === 0) return <View style={[styles.container, styles.center]}><ActivityIndicator size="large" color={colors.foreground} /></View>;

    const placeholderText = replyingTo
        ? `Replying to ${getDisplayName(replyingTo)}`
        : isAdminOnly && !isAdmin
        ? 'Only admins can start announcements'
        : `Message #${channelName} (press Enter to send)`;

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
                <View style={[styles.header, { paddingTop: insets.top + spacing.sm, paddingBottom: spacing.md }]}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                        <Ionicons name="chevron-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    {!isSearching ? (
                        <>
                            <View style={styles.headerCenter}>
                                <Text style={styles.channelName} numberOfLines={1}>{channelName}</Text>
                                <Text style={styles.channelHint}>Channel</Text>
                            </View>
                            <TouchableOpacity onPress={() => setIsSearching(true)} style={styles.headerAction} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                                <Ionicons name="search" size={22} color={colors.textMuted} />
                            </TouchableOpacity>
                        </>
                    ) : (
                        <View style={styles.searchBar}>
                            <Ionicons name="search" size={18} color={colors.textMuted} style={{ marginRight: spacing.sm }} />
                            <TextInput style={styles.searchInput} placeholder="Search messages..." placeholderTextColor={colors.textMuted} value={searchQuery} onChangeText={setSearchQuery} autoFocus />
                            <TouchableOpacity onPress={() => { setIsSearching(false); setSearchQuery(''); }}><Text style={styles.cancelText}>Cancel</Text></TouchableOpacity>
                        </View>
                    )}
                </View>

                <FlatList ref={flatListRef} data={messages} renderItem={renderMessage} keyExtractor={(item) => item.id} contentContainerStyle={[styles.messagesList, { paddingBottom: insets.bottom + 24 }]} style={styles.messagesListContainer} onContentSizeChange={() => { if (!isSearching) flatListRef.current?.scrollToEnd({ animated: false }); }} onScrollToIndexFailed={(info) => { setTimeout(() => { flatListRef.current?.scrollToIndex({ index: info.index, animated: true }); }, 250); }} showsVerticalScrollIndicator={false}
                    ListHeaderComponent={
                        !isSearching ? (
                            <View style={styles.threadHeader}>
                                <Text style={styles.breadcrumb}>Community · {channelCategory || 'general'}</Text>
                                <Text style={styles.threadTitle}>{channelName}</Text>
                                {!!channelDescription && <Text style={styles.threadSubtitle}>{channelDescription}</Text>}
                                {!!channelTags.length && (
                                    <View style={styles.tagRow}>
                                        {channelTags.slice(0, 5).map((tag) => (
                                            <View key={tag} style={styles.tagPill}><Text style={styles.tagText}>{tag}</Text></View>
                                        ))}
                                    </View>
                                )}
                            </View>
                        ) : null
                    }
                    ListEmptyComponent={
                    <View style={styles.emptyState}>
                        {isSearching ? (
                            <Text style={styles.welcomeSubtitle}>No messages found for "{searchQuery}"</Text>
                        ) : (
                            <>
                                <View style={styles.emptyStateIcon}><Ionicons name="chatbubble-ellipses-outline" size={40} color={colors.textMuted} /></View>
                                <Text style={styles.welcomeTitle}>{channelName}</Text>
                                <Text style={styles.welcomeSubtitle}>No messages yet. Be the first to say something.</Text>
                            </>
                        )}
                    </View>
                } />

                {isAdminOnly && !isAdmin && !replyingTo && !isSearching && (
                    <View style={styles.restrictedInfo}><Ionicons name="information-circle" size={18} color={colors.textMuted} /><Text style={styles.restrictedInfoText}>Only admins can post announcements. Reply to comment.</Text></View>
                )}

                {!isSearching && (isAdmin || !isAdminOnly || replyingTo) && (
                    <View style={[styles.inputWrapper, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
                        {replyingTo && (
                            <View style={styles.replyPreview}>
                                <Text style={styles.replyPreviewText} numberOfLines={1}>
                                    Replying to{' '}
                                    <Text style={{ fontWeight: '600' }}>{getDisplayName(replyingTo)}</Text>
                                </Text>
                                <TouchableOpacity onPress={() => setReplyingTo(null)}>
                                    <Ionicons name="close-circle" size={18} color={colors.textMuted} />
                                </TouchableOpacity>
                            </View>
                        )}
                        {selectedImage && <View style={styles.imagePreviewContainer}><Image source={{ uri: selectedImage }} style={styles.imagePreview} /><TouchableOpacity style={styles.removeImageBtn} onPress={() => setSelectedImage(null)}><Ionicons name="close-circle" size={22} color={colors.error} /></TouchableOpacity>{uploading && <View style={styles.uploadOverlay}><ActivityIndicator color={colors.buttonText} /></View>}</View>}
                        <View style={styles.inputContainer}>
                            <TouchableOpacity style={styles.attachBtn} onPress={handlePickImage} disabled={uploading}><Ionicons name="add-circle" size={24} color={colors.textMuted} /></TouchableOpacity>
                            <TextInput
                                style={styles.input}
                                placeholder={placeholderText}
                                placeholderTextColor={colors.textMuted}
                                value={messageText}
                                onChangeText={setMessageText}
                                multiline
                                editable={(canPostTopLevel || !!replyingTo) && !uploading}
                                onKeyPress={handleKeyPress}
                                returnKeyType="send"
                                autoFocus={Platform.OS === 'web'}
                            />
                            <TouchableOpacity style={[styles.sendBtn, (messageText.trim() || selectedImage) && (canPostTopLevel || !!replyingTo) && styles.sendBtnActive, (!messageText.trim() && !selectedImage || (!canPostTopLevel && !replyingTo)) && styles.disabledBtn]} onPress={handleSendMessage} disabled={(!messageText.trim() && !selectedImage) || sending || uploading || (!canPostTopLevel && !replyingTo)}>
                                {uploading || sending ? <ActivityIndicator size="small" color={colors.buttonText} /> : <Ionicons name="send" size={18} color={(messageText.trim() || selectedImage) && (canPostTopLevel || !!replyingTo) ? colors.buttonText : colors.textMuted} />}
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
    header: { backgroundColor: colors.card, flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, ...shadows.sm },
    backButton: { marginRight: spacing.sm },
    headerCenter: { flex: 1, minWidth: 0 },
    channelName: { fontSize: 18, fontWeight: '700', color: colors.foreground },
    channelHint: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
    headerAction: { padding: spacing.xs },
    searchBar: { flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: 10, paddingHorizontal: spacing.sm, height: 40 },
    searchInput: { flex: 1, color: colors.textPrimary, fontSize: 15, paddingVertical: 8, marginRight: spacing.sm },
    cancelText: { color: colors.info, fontWeight: '600', fontSize: 15 },
    messagesListContainer: { backgroundColor: colors.surface },
    messagesList: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.lg },
    messageRow: {
        flexDirection: 'row',
        backgroundColor: colors.card,
        borderRadius: 12,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
    },
    replyRow: {
        borderLeftWidth: 3,
        borderLeftColor: colors.info,
    },
    messageHighlight: { borderColor: colors.info },
    userPanel: {
        width: 120,
        padding: spacing.md,
        borderRightWidth: 1,
        borderRightColor: colors.border,
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderTopLeftRadius: 12,
        borderBottomLeftRadius: 12,
    },
    userAvatarWrap: { marginBottom: spacing.sm },
    userAvatar: { width: 56, height: 56, borderRadius: 28 },
    avatarMini: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.foreground, justifyContent: 'center', alignItems: 'center' },
    avatarInitial: { color: colors.buttonText, fontWeight: '700', fontSize: 16 },
    userPanelName: { fontSize: 13, fontWeight: '700', color: colors.foreground, textAlign: 'center' },
    userPanelRole: { fontSize: 11, color: colors.textMuted, marginTop: 4 },
    contentColumn: { flex: 1, minWidth: 0, padding: spacing.md },
    metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm },
    postIndex: { fontSize: 11, color: colors.textMuted, fontWeight: '600' },
    metaTime: { fontSize: 11, color: colors.textMuted },
    votePill: { backgroundColor: colors.surface, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, borderWidth: 1, borderColor: colors.border },
    voteScore: { fontSize: 11, color: colors.textSecondary, fontWeight: '600' },
    replyContext: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        backgroundColor: colors.surface,
        borderRadius: 8,
        paddingHorizontal: spacing.sm,
        paddingVertical: 6,
        marginBottom: 8,
        borderLeftWidth: 3,
        borderLeftColor: colors.info,
    },
    replyContextText: { color: colors.textSecondary, fontSize: 13, flex: 1 },
    replyContextUser: { fontWeight: '600', color: colors.foreground },
    messageBody: { backgroundColor: colors.background, borderRadius: 8, padding: spacing.md },
    messageText: { color: colors.foreground, fontSize: 15, lineHeight: 22 },
    attachmentImage: { width: '100%', aspectRatio: 1.33, borderRadius: 12, marginTop: spacing.sm, backgroundColor: colors.surface, maxWidth: 260 },
    messageActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm, alignItems: 'center' },
    actionBtn: { padding: 6 },
    reactionsRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 8, gap: 6 },
    reactionBadge: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12, borderWidth: 1, borderColor: colors.border },
    reactionBadgeActive: { backgroundColor: colors.accentMuted, borderColor: colors.foreground },
    reactionEmoji: { fontSize: 13 },
    reactionCount: { fontSize: 11, color: colors.textSecondary, marginLeft: 4 },
    reactionCountActive: { color: colors.foreground, fontWeight: '600' },
    emptyState: { padding: spacing.xxl, alignItems: 'center' },
    emptyStateIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center', marginBottom: spacing.lg },
    welcomeTitle: { fontSize: 20, fontWeight: '700', color: colors.foreground, textAlign: 'center', marginBottom: spacing.sm },
    welcomeSubtitle: { fontSize: 14, color: colors.textMuted, textAlign: 'center', lineHeight: 20 },
    threadHeader: { backgroundColor: colors.card, padding: spacing.lg, borderRadius: 12, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.lg },
    breadcrumb: { fontSize: 11, color: colors.textMuted, letterSpacing: 0.4, textTransform: 'uppercase' },
    threadTitle: { fontSize: 20, fontWeight: '700', color: colors.foreground, marginTop: 6 },
    threadSubtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 6, lineHeight: 18 },
    tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.sm },
    tagPill: { backgroundColor: colors.surface, borderRadius: borderRadius.full, paddingHorizontal: 8, paddingVertical: 2, borderWidth: 1, borderColor: colors.border },
    tagText: { fontSize: 10, color: colors.textMuted, fontWeight: '600' },
    inputWrapper: { paddingHorizontal: spacing.md, paddingTop: spacing.sm, backgroundColor: colors.background, borderTopWidth: 1, borderTopColor: colors.border },
    replyPreview: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: colors.surface, paddingVertical: 10, paddingHorizontal: spacing.md, borderRadius: 12, marginBottom: spacing.sm, borderLeftWidth: 3, borderLeftColor: colors.info },
    replyPreviewText: { color: colors.textSecondary, fontSize: 13, flex: 1 },
    imagePreviewContainer: { position: 'relative', marginBottom: spacing.sm, alignSelf: 'flex-start' },
    imagePreview: { width: 88, height: 88, borderRadius: 12 },
    removeImageBtn: { position: 'absolute', top: -6, right: -6, backgroundColor: colors.card, borderRadius: 14, ...shadows.sm },
    uploadOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', borderRadius: borderRadius.md },
    inputContainer: { flexDirection: 'row', alignItems: 'flex-end', backgroundColor: colors.card, borderRadius: 22, paddingHorizontal: spacing.sm, paddingVertical: 6, paddingRight: 4, borderWidth: 1, borderColor: colors.border, ...shadows.sm },
    attachBtn: { padding: 8, marginRight: 4 },
    input: { flex: 1, color: colors.textPrimary, paddingHorizontal: spacing.sm, fontSize: 15, maxHeight: 100, minHeight: 38 },
    sendBtn: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center' },
    sendBtnActive: { backgroundColor: colors.foreground },
    disabledBtn: { opacity: 0.4 },
    restrictedInfo: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, gap: 8 },
    restrictedInfoText: { color: colors.textMuted, fontSize: 13, fontWeight: '500' },
});
