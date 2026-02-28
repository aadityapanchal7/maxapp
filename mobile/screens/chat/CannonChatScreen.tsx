import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, FlatList, KeyboardAvoidingView, Platform, ActivityIndicator, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

interface Message { role: 'user' | 'assistant'; content: string; attachment_url?: string; attachment_type?: string; }

export default function CannonChatScreen() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [selectedImage, setSelectedImage] = useState<string | null>(null);
    const flatListRef = useRef<FlatList>(null);

    useEffect(() => { loadHistory(); }, []);

    const loadHistory = async () => { try { const { messages: history } = await api.getChatHistory(); setMessages(history || []); } catch (e) { console.error(e); } };

    const handlePickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, quality: 0.8 });
        if (!result.canceled) setSelectedImage(result.assets[0].uri);
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
            const { response } = await api.sendChatMessage(userContent, attachmentUrl, attachmentType);
            setMessages(prev => [...prev, { role: 'assistant', content: response }]);
        } catch (e) { console.error(e); setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, something went wrong.' }]); }
        finally { setLoading(false); setUploading(false); }
    };

    const renderMessage = ({ item }: { item: Message }) => (
        <View style={[styles.messageBubble, item.role === 'user' ? styles.userBubble : styles.assistantBubble]}>
            {item.content ? <Text style={[styles.messageText, item.role === 'user' && styles.userMessageText]}>{item.content}</Text> : null}
            {item.attachment_url && item.attachment_type === 'image' && (
                <Image source={{ uri: api.resolveAttachmentUrl(item.attachment_url) }} style={styles.attachmentImage} resizeMode="cover" />
            )}
        </View>
    );

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
                <View style={styles.header}>
                    <Text style={styles.title}>Cannon</Text>
                    <Text style={styles.subtitle}>Your Lookmaxxing Coach</Text>
                </View>

                <FlatList ref={flatListRef} data={messages} renderItem={renderMessage} keyExtractor={(_, i) => i.toString()} contentContainerStyle={styles.messageList} onContentSizeChange={() => flatListRef.current?.scrollToEnd()} showsVerticalScrollIndicator={false} />

                <View style={styles.outerInputContainer}>
                    {selectedImage && (
                        <View style={styles.imagePreviewContainer}>
                            <Image source={{ uri: selectedImage }} style={styles.imagePreview} />
                            <TouchableOpacity style={styles.removeImageBtn} onPress={() => setSelectedImage(null)}>
                                <Ionicons name="close-circle" size={24} color={colors.error} />
                            </TouchableOpacity>
                            {uploading && <View style={styles.uploadOverlay}><ActivityIndicator color={colors.buttonText} /></View>}
                        </View>
                    )}
                    <View style={styles.inputContainer}>
                        <TouchableOpacity style={styles.attachButton} onPress={handlePickImage} disabled={loading || uploading}>
                            <Ionicons name="add" size={24} color={colors.textMuted} />
                        </TouchableOpacity>
                        <TextInput style={styles.input} placeholder="Ask Cannon anything..." placeholderTextColor={colors.textMuted} value={input} onChangeText={setInput} multiline editable={!loading && !uploading} />
                        <TouchableOpacity style={[styles.sendButton, (!input.trim() && !selectedImage) && styles.disabledButton]} onPress={sendMessage} disabled={(!input.trim() && !selectedImage) || loading || uploading}>
                            {loading || uploading ? <ActivityIndicator size="small" color={colors.buttonText} /> : <Ionicons name="send" size={20} color={colors.buttonText} />}
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
    header: { paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
    title: { ...typography.h2 },
    subtitle: { ...typography.caption },
    messageList: { padding: spacing.lg },
    messageBubble: { maxWidth: '80%', padding: spacing.md, borderRadius: borderRadius.lg, marginBottom: spacing.sm },
    userBubble: { alignSelf: 'flex-end', backgroundColor: colors.accent },
    assistantBubble: { alignSelf: 'flex-start', backgroundColor: colors.surface },
    messageText: { ...typography.body },
    userMessageText: { color: colors.buttonText },
    attachmentImage: { width: 220, height: 160, borderRadius: borderRadius.md, marginTop: spacing.sm },
    outerInputContainer: { padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border },
    imagePreviewContainer: { position: 'relative', marginBottom: spacing.sm, marginLeft: spacing.md },
    imagePreview: { width: 80, height: 80, borderRadius: borderRadius.md },
    removeImageBtn: { position: 'absolute', top: -10, right: -10, backgroundColor: colors.background, borderRadius: 12 },
    uploadOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', borderRadius: borderRadius.md },
    inputContainer: { flexDirection: 'row', alignItems: 'flex-end' },
    attachButton: { padding: spacing.sm, marginBottom: 4 },
    input: { flex: 1, backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, color: colors.textPrimary, maxHeight: 100, borderWidth: 1, borderColor: colors.border },
    sendButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.accent, justifyContent: 'center', alignItems: 'center', marginLeft: spacing.sm },
    disabledButton: { opacity: 0.4 },
});
