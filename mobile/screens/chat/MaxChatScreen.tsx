import React, { useState, useEffect, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, FlatList, KeyboardAvoidingView, Platform, ActivityIndicator, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRoute, useNavigation, useFocusEffect } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

interface Message { role: 'user' | 'assistant'; content: string; attachment_url?: string; attachment_type?: string; isTyping?: boolean; }

/** Walk up to the root navigator (stack) so we can open screens registered as stack siblings of Main. */
function navigateFromNestedToRoot(navigation: { getParent?: () => any }, routeName: string, params?: object) {
    let nav: any = navigation;
    for (let i = 0; i < 6; i++) {
        const parent = nav?.getParent?.();
        if (!parent) break;
        nav = parent;
    }
    if (nav?.navigate) {
        nav.navigate(routeName, params);
    }
}

export default function MaxChatScreen() {
    const route = useRoute<any>();
    const navigation = useNavigation<any>();
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [selectedImage, setSelectedImage] = useState<string | null>(null);
    const flatListRef = useRef<FlatList>(null);
    const initScheduleHandled = useRef(false);
    /** Heightmax: hide CTA after active schedule exists (chat or components screen). */
    const [heightmaxScheduleExists, setHeightmaxScheduleExists] = useState(false);

    const addTyping = () => setMessages(prev => [...prev.filter(m => !m.isTyping), { role: 'assistant', content: '', isTyping: true }]);
    const removeTyping = () => setMessages(prev => prev.filter(m => !m.isTyping));

    useEffect(() => { loadHistory(); }, []);

    const refreshHeightmaxScheduleExists = useCallback(async () => {
        if (route.params?.initSchedule !== 'heightmax') return;
        try {
            const res = await api.getMaxxSchedule('heightmax');
            setHeightmaxScheduleExists(Boolean(res?.schedule?.id));
        } catch {
            setHeightmaxScheduleExists(false);
        }
    }, [route.params?.initSchedule]);

    useFocusEffect(
        useCallback(() => {
            if (route.params?.initSchedule !== 'heightmax') {
                setHeightmaxScheduleExists(false);
                return;
            }
            let cancelled = false;
            (async () => {
                try {
                    const res = await api.getMaxxSchedule('heightmax');
                    const has = Boolean(res?.schedule?.id);
                    if (!cancelled) setHeightmaxScheduleExists(has);
                } catch {
                    if (!cancelled) setHeightmaxScheduleExists(false);
                }
            })();
            return () => {
                cancelled = true;
            };
        }, [route.params?.initSchedule]),
    );

    useEffect(() => {
        const initSchedule = route.params?.initSchedule;
        if (!initSchedule) return;
        if (initScheduleHandled.current === initSchedule) return;
        if (loading) return;
        initScheduleHandled.current = initSchedule;
        const maxxLabel = initSchedule.charAt(0).toUpperCase() + initSchedule.slice(1).replace('max', 'Max');
        sendMessageWithContext(
            `I want to start my ${maxxLabel} schedule.`,
            initSchedule,
        );
    }, [route.params?.initSchedule, loading]);

    const loadHistory = async () => { try { const { messages: history } = await api.getChatHistory(); setMessages(history || []); } catch (e) { console.error(e); } };

    const handlePickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, quality: 0.8 });
        if (!result.canceled) setSelectedImage(result.assets[0].uri);
    };

    const sendMessageWithContext = async (msg: string, initContext?: string) => {
        if (!msg.trim() || loading) return;
        setLoading(true);
        setMessages(prev => [...prev, { role: 'user', content: msg }]);
        addTyping();
        try {
            const { response } = await api.sendChatMessage(msg, undefined, undefined, initContext);
            removeTyping();
            setMessages(prev => [...prev, { role: 'assistant', content: response }]);
            if (initContext === 'heightmax') await refreshHeightmaxScheduleExists();
        } catch (e: any) {
            console.error('sendMessageWithContext error:', e?.response?.data || e?.message || e);
            removeTyping();
            setMessages(prev => [...prev, { role: 'assistant', content: 'sorry, something went wrong. try again.' }]);
        } finally {
            setLoading(false);
        }
    };

    const sendMessage = async () => {
        if ((!input.trim() && !selectedImage) || loading) return;
        const userContent = input.trim();
        let attachmentUrl: string | undefined; let attachmentType: string | undefined;
        setLoading(true); setInput('');
        try {
            if (selectedImage) {
                setUploading(true);
                const formData = new FormData();
                const filename = selectedImage.split('/').pop() || 'upload.jpg';
                const match = /\.(\w+)$/.exec(filename);
                formData.append('file', { uri: selectedImage, name: filename, type: match ? `image/${match[1]}` : 'image' } as any);
                const uploadRes = await api.uploadChatFile(formData);
                attachmentUrl = uploadRes.url; attachmentType = 'image'; setUploading(false);
            }
            setMessages(prev => [...prev, { role: 'user', content: userContent, attachment_url: attachmentUrl, attachment_type: attachmentType }]);
            setSelectedImage(null);
            addTyping();
            const { response } = await api.sendChatMessage(userContent, attachmentUrl, attachmentType);
            removeTyping();
            setMessages(prev => [...prev, { role: 'assistant', content: response }]);
            if (route.params?.initSchedule === 'heightmax') await refreshHeightmaxScheduleExists();
        } catch (e) { console.error(e); removeTyping(); setMessages(prev => [...prev, { role: 'assistant', content: 'sorry, something went wrong.' }]); }
        finally { setLoading(false); setUploading(false); }
    };

    const TypingDots = () => {
        const [dots, setDots] = React.useState('');
        React.useEffect(() => {
            const id = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 400);
            return () => clearInterval(id);
        }, []);
        return <Text style={styles.typingText}>typing{dots}</Text>;
    };

    const renderMessage = ({ item }: { item: Message }) => {
        if (item.isTyping) {
            return (
                <View style={styles.messageRow}>
                    <View style={[styles.bubble, styles.assistantBubble, styles.typingBubble]}>
                        <TypingDots />
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
                        <Image source={{ uri: api.resolveAttachmentUrl(item.attachment_url) }} style={styles.attachmentImage} resizeMode="cover" />
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

                <FlatList
                    ref={flatListRef}
                    data={messages}
                    renderItem={renderMessage}
                    keyExtractor={(item, i) => item.isTyping ? 'typing' : i.toString()}
                    contentContainerStyle={[styles.messageList, messages.length === 0 && styles.messageListEmpty]}
                    onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
                    showsVerticalScrollIndicator={false}
                    ListEmptyComponent={ListEmpty}
                />

                {route.params?.initSchedule === 'heightmax' && !heightmaxScheduleExists && (
                    <TouchableOpacity
                        style={styles.heightPartsCta}
                        activeOpacity={0.85}
                        onPress={() => navigateFromNestedToRoot(navigation, 'HeightScheduleComponents')}
                    >
                        <Ionicons name="options-outline" size={20} color={colors.buttonText} />
                        <Text style={styles.heightPartsCtaText}>customize height tracks</Text>
                        <Ionicons name="chevron-forward" size={18} color={colors.buttonText} />
                    </TouchableOpacity>
                )}

                <View style={styles.outerInputContainer}>
                    {selectedImage && (
                        <View style={styles.imagePreviewContainer}>
                            <Image source={{ uri: selectedImage }} style={styles.imagePreview} />
                            <TouchableOpacity style={styles.removeImageBtn} onPress={() => setSelectedImage(null)}>
                                <Ionicons name="close-circle" size={22} color={colors.error} />
                            </TouchableOpacity>
                            {uploading && <View style={styles.uploadOverlay}><ActivityIndicator color={colors.buttonText} /></View>}
                        </View>
                    )}
                    <View style={styles.inputContainer}>
                        <TouchableOpacity style={styles.attachButton} onPress={handlePickImage} disabled={loading || uploading}>
                            <Ionicons name="add-circle-outline" size={26} color={colors.textMuted} />
                        </TouchableOpacity>
                        <TextInput
                            style={styles.input}
                            placeholder="Ask Max anything..."
                            placeholderTextColor={colors.textMuted}
                            value={input}
                            onChangeText={setInput}
                            multiline
                            editable={!loading && !uploading}
                        />
                        <TouchableOpacity
                            style={[styles.sendButton, (!input.trim() && !selectedImage) && styles.disabledButton]}
                            onPress={sendMessage}
                            disabled={(!input.trim() && !selectedImage) || loading || uploading}
                        >
                            {loading || uploading ? <ActivityIndicator size="small" color={colors.buttonText} /> : <Ionicons name="send" size={18} color={colors.buttonText} />}
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
    imagePreviewContainer: { position: 'relative', marginBottom: spacing.sm, alignSelf: 'flex-start' },
    imagePreview: { width: 80, height: 80, borderRadius: 12 },
    removeImageBtn: { position: 'absolute', top: -6, right: -6, backgroundColor: colors.card, borderRadius: 14, ...shadows.sm },
    uploadOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', borderRadius: 12 },
    inputContainer: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        backgroundColor: colors.card,
        borderRadius: 24,
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
    },
    attachButton: { padding: 6, marginRight: 4 },
    input: { flex: 1, color: colors.textPrimary, fontSize: 15, paddingVertical: 10, paddingHorizontal: 8, maxHeight: 100 },
    sendButton: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.foreground, justifyContent: 'center', alignItems: 'center', marginLeft: 8, ...shadows.sm },
    disabledButton: { opacity: 0.35 },
    heightPartsCta: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        marginHorizontal: spacing.md,
        marginBottom: spacing.sm,
        paddingVertical: 12,
        paddingHorizontal: spacing.lg,
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.lg,
        ...shadows.md,
    },
    heightPartsCtaText: {
        flex: 1,
        fontSize: 15,
        fontWeight: '600',
        color: colors.buttonText,
    },
});
