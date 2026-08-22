import React, { useCallback, useState } from 'react';
import { FlatList, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { LiquidGlass } from '../../components/glass/LiquidGlass';
import api, { type InboxMessage } from '../../services/api';

export default function InAppNotificationsScreen() {
    const insets = useSafeAreaInsets();
    const navigation = useNavigation();
    const [messages, setMessages] = useState<InboxMessage[]>([]);

    const load = useCallback(async () => {
        try {
            const { messages: rows } = await api.getInboxMessages();
            setMessages(rows);
        } catch { /* best-effort */ }
    }, []);

    useFocusEffect(useCallback(() => { void load(); }, [load]));

    const open = async (m: InboxMessage) => {
        if (!m.read_at) await api.markInboxRead(m.id).catch(() => {});
        setMessages((prev) => prev.map((x) => (x.id === m.id ? { ...x, read_at: new Date().toISOString() } : x)));
    };

    return (
        <View style={[s.root, { paddingTop: insets.top }]}>
            <View style={s.topBar}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={s.back} accessibilityLabel="Back">
                    <Ionicons name="chevron-back" size={24} color="#111" />
                </TouchableOpacity>
                <Text style={s.title}>Notifications</Text>
                <TouchableOpacity onPress={() => api.markAllInboxRead().then(load).catch(() => undefined)} hitSlop={12}>
                    <Text style={s.markAll}>Mark all read</Text>
                </TouchableOpacity>
            </View>

            <FlatList
                data={messages}
                keyExtractor={(m) => m.id}
                contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 24, gap: 12 }}
                ListEmptyComponent={
                    <View style={s.empty}>
                        <Ionicons name="notifications-off-outline" size={40} color="#999" />
                        <Text style={s.emptyText}>No notifications yet</Text>
                    </View>
                }
                renderItem={({ item }) => (
                    <TouchableOpacity activeOpacity={0.85} onPress={() => void open(item)}>
                        <LiquidGlass radius={18} intensity={60} style={{ width: '100%' }} contentStyle={s.card}>
                            {!item.read_at ? <View style={s.unreadDot} /> : null}
                            <Text style={[s.cardTitle, !item.read_at && s.unreadTitle]}>{item.title}</Text>
                            <Text style={s.cardBody}>{item.body}</Text>
                            {item.created_at ? (
                                <Text style={s.cardTime}>{new Date(item.created_at).toLocaleDateString()}</Text>
                            ) : null}
                        </LiquidGlass>
                    </TouchableOpacity>
                )}
            />
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: '#F1F1EF' },
    topBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingBottom: 8, gap: 8 },
    back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
    title: { flex: 1, fontFamily: 'Matter-Bold', fontSize: 22, color: '#111', letterSpacing: -0.4 },
    markAll: { fontFamily: 'Matter-Medium', fontSize: 13, color: '#666' },
    card: { padding: 16, gap: 6 },
    cardTitle: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: '#333' },
    unreadTitle: { color: '#111' },
    cardBody: { fontFamily: 'Matter-Regular', fontSize: 14, color: '#555', lineHeight: 20 },
    cardTime: { fontFamily: 'Matter-Regular', fontSize: 12, color: '#999', marginTop: 4 },
    unreadDot: { position: 'absolute', top: 14, right: 14, width: 8, height: 8, borderRadius: 4, backgroundColor: '#EF4444' },
    empty: { alignItems: 'center', paddingTop: 80, gap: 12 },
    emptyText: { fontFamily: 'Matter-Regular', fontSize: 15, color: '#888' },
});
