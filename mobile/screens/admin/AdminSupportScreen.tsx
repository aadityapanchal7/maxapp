import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView, Alert, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function AdminSupportScreen() {
    const [targetUser, setTargetUser] = useState('');
    const [message, setMessage] = useState('');
    const [sending, setSending] = useState(false);
    const [isBroadcast, setIsBroadcast] = useState(false);

    const handleSend = async () => {
        if (!message.trim() || (!isBroadcast && !targetUser.trim())) {
            Alert.alert("Error", "Please fill in all fields");
            return;
        }

        setSending(true);
        try {
            if (isBroadcast) {
                await api.sendAdminBroadcast(message);
            } else {
                await api.sendAdminDirect(targetUser, message);
            }
            Alert.alert("Success", "Message sent successfully!");
            setMessage('');
            if (!isBroadcast) setTargetUser('');
        } catch (error) {
            console.error(error);
            Alert.alert("Error", "Failed to send message");
        } finally {
            setSending(false);
        }
    };

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
            <Text style={styles.title}>Dispatch Support</Text>
            <Text style={styles.subtitle}>Send messages as the Cannon Coach persona.</Text>

            <View style={styles.typeSelector}>
                <TouchableOpacity
                    style={[styles.typeBtn, !isBroadcast && styles.activeType]}
                    onPress={() => setIsBroadcast(false)}
                >
                    <Text style={[styles.typeText, !isBroadcast && styles.activeTypeText]}>Direct Message</Text>
                </TouchableOpacity>
                <TouchableOpacity
                    style={[styles.typeBtn, isBroadcast && styles.activeType]}
                    onPress={() => setIsBroadcast(true)}
                >
                    <Text style={[styles.typeText, isBroadcast && styles.activeTypeText]}>Broadcast</Text>
                </TouchableOpacity>
            </View>

            {!isBroadcast && (
                <View style={styles.inputGroup}>
                    <Text style={styles.label}>Target User ID</Text>
                    <TextInput
                        style={styles.input}
                        placeholder="User ID (e.g. 65db...)"
                        placeholderTextColor={colors.textMuted}
                        value={targetUser}
                        onChangeText={setTargetUser}
                    />
                </View>
            )}

            <View style={styles.inputGroup}>
                <Text style={styles.label}>Message Content</Text>
                <TextInput
                    style={[styles.input, styles.textArea]}
                    placeholder="Type your message here..."
                    placeholderTextColor={colors.textMuted}
                    value={message}
                    onChangeText={setMessage}
                    multiline
                    numberOfLines={6}
                />
            </View>

            <TouchableOpacity
                style={[styles.sendBtn, sending && styles.disabledBtn]}
                onPress={handleSend}
                disabled={sending}
            >
                {sending ? <ActivityIndicator color="#FFF" /> : (
                    <>
                        <Ionicons name="send" size={20} color="#FFF" />
                        <Text style={styles.sendBtnText}>{isBroadcast ? 'Broadcast to All' : 'Send to User'}</Text>
                    </>
                )}
            </TouchableOpacity>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg },
    title: { ...typography.h1, color: '#FFFFFF' },
    subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.xl },
    typeSelector: { flexDirection: 'row', backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: 4, marginBottom: spacing.xl },
    typeBtn: { flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 6 },
    activeType: { backgroundColor: colors.primary },
    typeText: { color: colors.textMuted, fontWeight: '600' },
    activeTypeText: { color: '#FFFFFF' },
    inputGroup: { marginBottom: spacing.lg },
    label: { color: '#FFFFFF', marginBottom: 8, fontWeight: '600' },
    input: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, color: '#FFFFFF', borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)' },
    textArea: { height: 120, textAlignVertical: 'top' },
    sendBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, height: 54, borderRadius: borderRadius.md, gap: 10, marginTop: spacing.md },
    sendBtnText: { color: '#FFFFFF', fontSize: 16, fontWeight: 'bold' },
    disabledBtn: { opacity: 0.5 },
});
