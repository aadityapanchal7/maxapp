import React, { useState, useRef, useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator, NativeSyntheticEvent, TextInputKeyPressEventData, Alert, AppState } from 'react-native';
import { FlashList, FlashListRef } from '@shopify/flash-list';
import { useNavigation, useRoute, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { CachedImage } from '../../components/CachedImage';
import { colors, spacing, borderRadius } from '../../theme/dark';

interface Message {
    id: string;
    channel_id: string;
    user_id: string;
    user_email: string;
    /** Server may send display handle separately from email prefix. */
    username?: string | null;
    user_avatar_url?: string;
    content: string;
    attachment_url?: string;
    attachment_type?: string;
    created_at: string;
    is_admin: boolean;
    parent_id?: string;
    reactions?: Record<string, string[]>;
}

function parseMessageTimestamp(dateString: string): number {
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
}

function sortMessagesChronological(msgs: Message[]): Message[] {
    return msgs.slice().sort((a, b) => {
        const at = parseMessageTimestamp(a.created_at);
        const bt = parseMessageTimestamp(b.created_at);
        if (at !== bt) return at - bt;
        return a.id.localeCompare(b.id);
    });
}

export default function ChannelChatScreen() {
    const navigation = useNavigation();
    const insets = useSafeAreaInsets();
    const route = useRoute<any>();
    const params = route.params ?? {};
    const channelId = params.channelId as string | undefined;
    const channelName = (params.channelName as string | undefined) ?? 'Channel';
    const [isAdminOnly, setIsAdminOnly] = useState(!!params.isAdminOnly);
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
    const flatListRef = useRef<FlashListRef<Message>>(null);
    const appStateRef = useRef(AppState.currentState);
    const isAdmin = user?.is_admin || false;
    const currentUserId = user?.id;
    const canPostTopLevel = !isAdminOnly || isAdmin;
    const UPVOTE = '\u2B06\uFE0F';
    const DOWNVOTE = '\u2B07\uFE0F';
    const LEGACY_UPVOTE = 'â¬†ï¸';
    const LEGACY_DOWNVOTE = 'â¬‡ï¸';
    const [pendingReactions, setPendingReactions] = useState<Record<string, boolean>>({});
    const loadMessagesInFlight = useRef(false);
    const wsConnectedRef = useRef(false);

    const forumWsRef = useRef<WebSocket | null>(null);
    const connectRef = useRef<(() => void) | null>(null);

    useEffect(() => {
        if (!channelId || isSearching) {
            wsConnectedRef.current = false;
            return;
        }
        let cancelled = false;
        let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
        let attempt = 0;

        const handleMessage = (e: MessageEvent) => {
            try {
                const data = JSON.parse(String(e.data)) as {
                    type?: string;
                    message?: Message;
                    message_id?: string;
                    reactions?: Record<string, string[]>;
                };
                if (data.type === 'message' && data.message) {
                    const m = data.message;
                    setMessages((prev) => {
                        if (prev.some((x) => x.id === m.id)) return prev;
                        return sortMessagesChronological([...prev, m]);
                    });
                } else if (data.type === 'reactions' && data.message_id && data.reactions) {
                    const mid = data.message_id;
                    const rx = data.reactions;
                    setMessages((prev) =>
                        prev.map((msg) => (msg.id === mid ? { ...msg, reactions: rx } : msg)),
                    );
                }
            } catch {
                /* ignore malformed */
            }
        };

        const connect = () => {
            void (async () => {
                const url = await api.getForumChannelWebSocketUrl(channelId);
                if (!url || cancelled) return;
                const ws = new WebSocket(url);
                forumWsRef.current = ws;
                ws.onopen = () => {
                    if (cancelled) return;
                    wsConnectedRef.current = true;
                    attempt = 0;
                };
                ws.onmessage = handleMessage;
                ws.onerror = () => {
                    wsConnectedRef.current = false;
                };
                ws.onclose = () => {
                    wsConnectedRef.current = false;
                    if (forumWsRef.current === ws) forumWsRef.current = null;
                    if (cancelled) return;
                    const delay = Math.min(30000, 1000 * Math.pow(2, attempt));
                    attempt += 1;
                    reconnectTimer = setTimeout(connect, delay);
                };
            })();
        };

        connectRef.current = connect;
        connect();
        return () => {
            cancelled = true;
            connectRef.current = null;
            if (reconnectTimer) clearTimeout(reconnectTimer);
            wsConnectedRef.current = false;
            try {
                forumWsRef.current?.close();
            } catch {
                /* ignore */
            }
            forumWsRef.current = null;
        };
    }, [channelId, isSearching]);

    // On foreground resume: reconnect WebSocket immediately and reload messages
    // to catch anything missed while the app was backgrounded.
    useEffect(() => {
        const sub = AppState.addEventListener('change', (next) => {
            const prev = appStateRef.current;
            appStateRef.current = next;
            if (prev.match(/inactive|background/) && next === 'active') {
                if (!wsConnectedRef.current) {
                    const ws = forumWsRef.current;
                    const alreadyLive = ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN);
                    if (!alreadyLive) connectRef.current?.();
                }
                void loadMessages();
            }
        });
        return () => sub.remove();
    }, []);

    useFocusEffect(useCallback(() => {
        if (!channelId) return;
        void loadMessages();
        if (isSearching) return undefined;
        const interval = setInterval(() => {
            if (appStateRef.current !== 'active') return;
            if (wsConnectedRef.current) return;
            void loadMessages();
        }, 12000);
        return () => clearInterval(interval);
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

    const formatShortTime = (dateString: string) => {
        const dt = new Date(parseTimestamp(dateString));
        if (Number.isNaN(dt.getTime())) return '';
        return dt.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    };

    const loadMessages = async () => {
        if (!channelId) return;
        if (loadMessagesInFlight.current) return;
        loadMessagesInFlight.current = true;
        try {
            const data = await api.getChannelMessages(channelId, 10, searchQuery);
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
        catch (e) { console.error(e); } finally { setLoading(false); loadMessagesInFlight.current = false; }
    };

    const handlePickImage = async () => { const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, quality: 0.8 }); if (!result.canceled) setSelectedImage(result.assets[0].uri); };

    const handleSendMessage = async () => {
        if (!channelId) return;
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
                setMessages(prev => sortMessagesChronological([...prev, result.message]));
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
        if (!channelId) return;
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
        if (message.username && message.username.trim().length > 0) return message.username.trim();
        const email = message.user_email || '';
        if (!email.includes('@')) return email.trim() || 'User';
        return email.split('@')[0];
    };

    const submitReport = async (item: Message, reason: string) => {
        if (!channelId) return;
        try {
            const res = await api.reportChannelMessage(channelId, item.id, reason);
            Alert.alert('Report sent', res.message || 'Thank you. Our team will review this.');
        } catch {
            Alert.alert('Error', 'Could not submit report. Try again later.');
        }
    };

    const blockUserFromMessage = async (item: Message) => {
        try {
            await api.blockUser(item.user_id);
            Alert.alert('Blocked', 'You will no longer see this user’s posts in channels.');
            loadMessages();
        } catch {
            Alert.alert('Error', 'Could not block this user.');
        }
    };

    const openMessageMenu = (item: Message) => {
        if (!currentUserId || item.user_id === currentUserId) return;
        Alert.alert('Message options', undefined, [
            {
                text: 'Report',
                onPress: () =>
                    Alert.alert('Report this message', 'Why are you reporting it?', [
                        { text: 'Spam or scam', onPress: () => submitReport(item, 'Spam or scam') },
                        { text: 'Harassment or hate', onPress: () => submitReport(item, 'Harassment or hate') },
                        { text: 'Nudity or sexual content', onPress: () => submitReport(item, 'Nudity or sexual content') },
                        { text: 'Something else', onPress: () => submitReport(item, 'Other') },
                        { text: 'Cancel', style: 'cancel' },
                    ]),
            },
            {
                text: 'Block user',
                style: 'destructive',
                onPress: () =>
                    Alert.alert(
                        'Block this user?',
                        'Their messages will be hidden for you in all channels. You can contact support if you need help.',
                        [
                            { text: 'Cancel', style: 'cancel' },
                            { text: 'Block', style: 'destructive', onPress: () => void blockUserFromMessage(item) },
                        ]
                    ),
            },
            { text: 'Cancel', style: 'cancel' },
        ]);
    };

    const scrollToMessage = (messageId: string) => {
        const index = messages.findIndex((m) => m.id === messageId);
        if (index === -1) return;
        setHighlightedId(messageId);
        flatListRef.current?.scrollToIndex({ index, animated: true, viewPosition: 0.5 });
        setTimeout(() => setHighlightedId(null), 1800);
    };

    const renderMessage = ({ item, index }: { item: Message; index: number }) => {
        const isReply = !!item.parent_id;
        const repliedMessage = item.parent_id ? messages.find(m => m.id === item.parent_id) : null;
        const isHighlighted = highlightedId === item.id;
        const prev = index > 0 ? messages[index - 1] : null;
        const groupWithPrev =
            !!prev &&
            prev.user_id === item.user_id &&
            parseTimestamp(item.created_at) - parseTimestamp(prev.created_at) < 7 * 60 * 1000;

        return (
            <View style={[styles.msgRow, isReply && styles.replyRow, isHighlighted && styles.msgHighlight, groupWithPrev && styles.msgRowGrouped]}>
                <View style={styles.msgAvatarSlot}>
                    {!groupWithPrev ? (
                        item.user_avatar_url ? (
                            <CachedImage uri={api.resolveAttachmentUrl(item.user_avatar_url)} style={styles.msgAvatar} />
                        ) : (
                            <View style={styles.msgAvatarFallback}>
                                <Text style={styles.msgAvatarInitial}>{getDisplayName(item)[0]?.toUpperCase()}</Text>
                            </View>
                        )
                    ) : null}
                </View>
                <View style={styles.msgBody}>
                    {!groupWithPrev && (
                        <View style={styles.msgAuthorRow}>
                            <Text style={styles.msgAuthor}>{getDisplayName(item)}</Text>
                            {item.is_admin ? <Text style={styles.msgModBadge}>MOD</Text> : null}
                            <Text style={styles.msgTime}>{formatShortTime(item.created_at)}</Text>
                        </View>
                    )}
                    {repliedMessage && (
                        <TouchableOpacity
                            style={styles.replyContext}
                            onPress={() => scrollToMessage(repliedMessage.id)}
                            activeOpacity={0.7}
                        >
                            <Ionicons name="return-down-forward" size={12} color={colors.textMuted} style={{ marginRight: 4 }} />
                            <Text style={styles.replyContextText} numberOfLines={1}>
                                <Text style={styles.replyContextUser}>{getDisplayName(repliedMessage)} </Text>
                                {repliedMessage.content}
                            </Text>
                        </TouchableOpacity>
                    )}
                    {item.content ? <Text style={styles.messageText}>{item.content}</Text> : null}
                    {item.attachment_url && item.attachment_type === 'image' && (
                        <CachedImage uri={api.resolveAttachmentUrl(item.attachment_url)} style={styles.attachmentImage} contentFit="contain" />
                    )}
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
                        {item.user_id !== currentUserId && currentUserId ? (
                            <TouchableOpacity onPress={() => openMessageMenu(item)} style={styles.actionBtn} activeOpacity={0.6}>
                                <Ionicons name="ellipsis-horizontal" size={16} color={colors.textMuted} />
                            </TouchableOpacity>
                        ) : null}
                    </View>
                </View>
            </View>
        );
    };

    const renderReactions = (message: Message) => {
        if (!message.reactions || Object.keys(message.reactions).length === 0) return null;
        const entries = Object.entries(message.reactions)
            .map(([emoji, userIds]) => {
                const normalizedEmoji = emoji === LEGACY_UPVOTE ? UPVOTE : emoji === LEGACY_DOWNVOTE ? DOWNVOTE : emoji;
                return [normalizedEmoji, userIds] as [string, string[]];
            })
            .filter(([emoji]) => emoji !== UPVOTE && emoji !== DOWNVOTE);
        if (entries.length === 0) return null;
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

    if (!channelId) {
        return (
            <View style={[styles.container, styles.center]}>
                <View style={styles.errorCard}>
                    <Ionicons name="alert-circle-outline" size={40} color={colors.textMuted} />
                    <Text style={styles.errorTitle}>Channel unavailable</Text>
                    <Text style={styles.errorSubtitle}>This channel could not be opened.</Text>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.errorBackBtn} activeOpacity={0.7}>
                        <Text style={styles.errorBackText}>Go back</Text>
                    </TouchableOpacity>
                </View>
            </View>
        );
    }

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
                            <View style={[styles.headerChannelIcon, isAdminOnly ? styles.headerChannelIconOfficial : styles.headerChannelIconCommunity]}>
                                <Ionicons
                                    name={isAdminOnly ? 'megaphone-outline' : 'chatbubbles-outline'}
                                    size={20}
                                    color={isAdminOnly ? colors.info : colors.textSecondary}
                                />
                            </View>
                            <View style={styles.headerCenter}>
                                <Text style={styles.channelName} numberOfLines={1}>
                                    {channelName}
                                </Text>
                                <View style={styles.liveRow}>
                                    <View style={styles.liveDot} />
                                    <Text style={styles.channelHint}>Live</Text>
                                </View>
                            </View>
                            <TouchableOpacity onPress={() => setIsSearching(true)} style={styles.headerAction} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                                <Ionicons name="search-outline" size={22} color={colors.textSecondary} />
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

                <FlashList
                    ref={flatListRef}
                    data={messages}
                    renderItem={renderMessage}
                    keyExtractor={(item) => item.id}
                    contentContainerStyle={[styles.messagesList, { paddingBottom: insets.bottom + 24 }]}
                    style={styles.messagesListContainer}
                    onContentSizeChange={() => {
                        if (!isSearching) flatListRef.current?.scrollToEnd({ animated: false });
                    }}
                    showsVerticalScrollIndicator={false}
                    ListHeaderComponent={
                        !isSearching ? (
                            <View style={styles.threadHeader}>
                                <View style={styles.threadHeaderHero}>
                                    <View style={[styles.threadIconWrap, isAdminOnly ? styles.threadIconOfficial : styles.threadIconCommunity]}>
                                        <Ionicons
                                            name={isAdminOnly ? 'megaphone-outline' : 'chatbubbles-outline'}
                                            size={22}
                                            color={isAdminOnly ? colors.info : colors.textSecondary}
                                        />
                                    </View>
                                    <View style={styles.threadHeaderTextBlock}>
                                        <Text style={styles.threadTitle} numberOfLines={2}>
                                            {channelName}
                                        </Text>
                                        {!!channelDescription && (
                                            <Text style={styles.threadSubtitle} numberOfLines={3}>
                                                {channelDescription}
                                            </Text>
                                        )}
                                        {(!!channelCategory || channelTags.length > 0) && (
                                            <View style={styles.threadMetaChips}>
                                                {!!channelCategory && (
                                                    <View style={styles.threadChip}>
                                                        <Text style={styles.threadChipText}>{channelCategory}</Text>
                                                    </View>
                                                )}
                                                {channelTags.slice(0, 6).map((tag) => (
                                                    <View key={tag} style={styles.threadTagChip}>
                                                        <Text style={styles.threadTagChipText}>#{tag}</Text>
                                                    </View>
                                                ))}
                                            </View>
                                        )}
                                    </View>
                                </View>
                                <Text style={styles.ugcNotice}>Long-press a message to report or block.</Text>
                            </View>
                        ) : null
                    }
                    ListEmptyComponent={
                    <View style={styles.emptyState}>
                        {isSearching ? (
                            <>
                                <View style={styles.emptyStateIcon}>
                                    <Ionicons name="search-outline" size={36} color={colors.textMuted} />
                                </View>
                                <Text style={styles.welcomeTitle}>No results</Text>
                                <Text style={styles.welcomeSubtitle}>Nothing matches &quot;{searchQuery}&quot;</Text>
                            </>
                        ) : (
                            <>
                                <View style={styles.emptyStateIcon}>
                                    <Ionicons name="chatbubbles-outline" size={36} color={colors.textSecondary} />
                                </View>
                                <Text style={styles.welcomeTitle}>Start the thread</Text>
                                <Text style={styles.welcomeSubtitle}>No messages yet. Say hello and kick things off.</Text>
                            </>
                        )}
                    </View>
                } />

                {isAdminOnly && !isAdmin && !replyingTo && !isSearching && (
                    <View style={styles.restrictedInfo}>
                        <Ionicons name="information-circle-outline" size={20} color={colors.info} />
                        <Text style={styles.restrictedInfoText}>Only admins can post new topics here. You can still reply to existing messages.</Text>
                    </View>
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
                        {selectedImage && <View style={styles.imagePreviewContainer}><CachedImage uri={selectedImage} style={styles.imagePreview} /><TouchableOpacity style={styles.removeImageBtn} onPress={() => setSelectedImage(null)}><Ionicons name="close-circle" size={22} color={colors.error} /></TouchableOpacity>{uploading && <View style={styles.uploadOverlay}><ActivityIndicator color={colors.buttonText} /></View>}</View>}
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
    header: {
        backgroundColor: colors.background,
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.borderLight,
    },
    backButton: { marginRight: spacing.xs },
    headerChannelIcon: {
        width: 40,
        height: 40,
        borderRadius: borderRadius.lg,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: spacing.sm,
    },
    headerChannelIconOfficial: { backgroundColor: 'rgba(59, 130, 246, 0.1)' },
    headerChannelIconCommunity: { backgroundColor: colors.surface },
    headerCenter: { flex: 1, minWidth: 0 },
    channelName: { fontSize: 17, fontWeight: '600', color: colors.foreground, letterSpacing: -0.35 },
    liveRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 },
    liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success },
    channelHint: { fontSize: 11, fontWeight: '600', color: colors.textSecondary, letterSpacing: 0.3, textTransform: 'uppercase' },
    headerAction: { padding: spacing.xs },
    searchBar: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        paddingHorizontal: spacing.md,
        minHeight: 44,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
    },
    searchInput: { flex: 1, color: colors.textPrimary, fontSize: 15, paddingVertical: 8, marginRight: spacing.sm },
    cancelText: { color: colors.foreground, fontWeight: '600', fontSize: 15 },
    messagesListContainer: { backgroundColor: colors.background },
    messagesList: { paddingHorizontal: spacing.md, paddingTop: spacing.md, paddingBottom: spacing.sm },
    msgRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        paddingVertical: 12,
        paddingHorizontal: 12,
        marginBottom: 10,
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        borderWidth: 1,
        borderColor: colors.border,
    },
    msgRowGrouped: {
        marginTop: -6,
        paddingTop: 8,
        paddingBottom: 12,
        borderTopLeftRadius: borderRadius.sm,
        borderTopRightRadius: borderRadius.sm,
    },
    replyRow: { borderLeftWidth: 2, borderLeftColor: colors.info, paddingLeft: 6, marginLeft: 2 },
    msgHighlight: { backgroundColor: colors.accentMuted },
    msgAvatarSlot: { width: 40, alignItems: 'center', marginRight: 8 },
    msgAvatar: { width: 36, height: 36, borderRadius: 18 },
    msgAvatarFallback: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.foreground, justifyContent: 'center', alignItems: 'center' },
    msgAvatarInitial: { color: colors.buttonText, fontWeight: '700', fontSize: 13 },
    msgBody: { flex: 1, minWidth: 0 },
    msgAuthorRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6, marginBottom: 2 },
    msgAuthor: { fontSize: 15, fontWeight: '600', color: colors.foreground, letterSpacing: -0.2 },
    msgModBadge: {
        fontSize: 10,
        fontWeight: '700',
        color: colors.info,
        backgroundColor: 'rgba(59, 130, 246, 0.12)',
        paddingHorizontal: 6,
        paddingVertical: 2,
        borderRadius: borderRadius.full,
        overflow: 'hidden',
    },
    msgTime: { fontSize: 11, color: colors.textMuted, fontWeight: '500' },
    replyContext: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        paddingHorizontal: 10,
        paddingVertical: 6,
        marginBottom: 6,
    },
    replyContextText: { color: colors.textSecondary, fontSize: 12, flex: 1 },
    replyContextUser: { fontWeight: '600', color: colors.foreground },
    messageText: { color: colors.foreground, fontSize: 15, lineHeight: 22 },
    attachmentImage: {
        width: '100%',
        maxWidth: 280,
        aspectRatio: 1.33,
        borderRadius: borderRadius.lg,
        marginTop: 8,
        backgroundColor: colors.surface,
    },
    messageActions: { flexDirection: 'row', gap: 4, marginTop: 4, alignItems: 'center', opacity: 0.85 },
    actionBtn: { padding: 4 },
    reactionsRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 4, gap: 4 },
    reactionBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: borderRadius.full,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
    },
    reactionBadgeActive: { backgroundColor: colors.accentMuted, borderColor: colors.foreground },
    reactionEmoji: { fontSize: 13 },
    reactionCount: { fontSize: 11, color: colors.textSecondary, marginLeft: 4 },
    reactionCountActive: { color: colors.foreground, fontWeight: '600' },
    emptyState: { padding: spacing.xxl, alignItems: 'center', paddingHorizontal: spacing.lg },
    emptyStateIcon: {
        width: 80,
        height: 80,
        borderRadius: 40,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: spacing.lg,
    },
    welcomeTitle: { fontSize: 20, fontWeight: '600', color: colors.foreground, textAlign: 'center', marginBottom: spacing.sm, letterSpacing: -0.4 },
    welcomeSubtitle: { fontSize: 15, color: colors.textSecondary, textAlign: 'center', lineHeight: 22, maxWidth: 280 },
    errorCard: {
        alignItems: 'center',
        padding: spacing.xl,
        marginHorizontal: spacing.lg,
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        borderWidth: 1,
        borderColor: colors.border,
    },
    errorTitle: { fontSize: 18, fontWeight: '600', color: colors.foreground, marginTop: spacing.md, letterSpacing: -0.3 },
    errorSubtitle: { fontSize: 14, color: colors.textSecondary, textAlign: 'center', marginTop: spacing.sm, lineHeight: 20 },
    errorBackBtn: { marginTop: spacing.lg, paddingVertical: 10, paddingHorizontal: spacing.lg, backgroundColor: colors.foreground, borderRadius: borderRadius.full },
    errorBackText: { color: colors.background, fontWeight: '600', fontSize: 15 },
    threadHeader: {
        marginBottom: spacing.md,
        padding: spacing.md,
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        borderWidth: 1,
        borderColor: colors.border,
    },
    threadHeaderHero: { flexDirection: 'row', alignItems: 'flex-start' },
    threadIconWrap: {
        width: 48,
        height: 48,
        borderRadius: borderRadius.lg,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: spacing.md,
    },
    threadIconOfficial: { backgroundColor: 'rgba(59, 130, 246, 0.1)' },
    threadIconCommunity: { backgroundColor: colors.surface },
    threadHeaderTextBlock: { flex: 1, minWidth: 0 },
    threadTitle: { fontSize: 18, fontWeight: '600', color: colors.foreground, letterSpacing: -0.4, lineHeight: 24 },
    threadSubtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 6, lineHeight: 20 },
    threadMetaChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
    threadChip: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
    },
    threadChipText: { fontSize: 11, fontWeight: '600', color: colors.textSecondary, textTransform: 'capitalize' },
    threadTagChip: {
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: borderRadius.full,
        backgroundColor: colors.accentMuted,
    },
    threadTagChipText: { fontSize: 11, fontWeight: '600', color: colors.textSecondary },
    ugcNotice: { fontSize: 11, color: colors.textMuted, marginTop: 12, lineHeight: 16 },
    inputWrapper: {
        paddingHorizontal: spacing.md,
        paddingTop: spacing.md,
        paddingBottom: spacing.xs,
        backgroundColor: colors.background,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.borderLight,
    },
    replyPreview: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: colors.surface,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.lg,
        marginBottom: spacing.sm,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
    },
    replyPreviewText: { color: colors.textSecondary, fontSize: 13, flex: 1 },
    imagePreviewContainer: { position: 'relative', marginBottom: spacing.sm, alignSelf: 'flex-start' },
    imagePreview: { width: 88, height: 88, borderRadius: 12 },
    removeImageBtn: {
        position: 'absolute',
        top: -6,
        right: -6,
        backgroundColor: colors.card,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    uploadOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', borderRadius: borderRadius.md },
    inputContainer: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        paddingHorizontal: spacing.sm,
        paddingVertical: 8,
        paddingRight: 6,
        borderWidth: 1,
        borderColor: colors.border,
    },
    attachBtn: { padding: 8, marginRight: 4 },
    input: { flex: 1, color: colors.textPrimary, paddingHorizontal: spacing.sm, fontSize: 15, maxHeight: 100, minHeight: 38 },
    sendBtn: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center' },
    sendBtnActive: { backgroundColor: colors.foreground },
    disabledBtn: { opacity: 0.4 },
    restrictedInfo: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        marginHorizontal: spacing.md,
        marginBottom: spacing.sm,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        backgroundColor: 'rgba(59, 130, 246, 0.08)',
        borderRadius: borderRadius.lg,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: 'rgba(59, 130, 246, 0.2)',
    },
    restrictedInfoText: { flex: 1, color: colors.textSecondary, fontSize: 13, fontWeight: '500', lineHeight: 18 },
});
