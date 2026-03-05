import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function ForumManageScreen() {
    const navigation = useNavigation<any>();
    const [channels, setChannels] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadChannels(); }, []);

    const loadChannels = async () => {
        try { const { forums } = await api.getChannels(); setChannels(forums || []); }
        catch (error) { console.error(error); }
        finally { setLoading(false); }
    };

    const handleChannelPress = (item: any) => {
        navigation.navigate('ChannelChat', { channelId: item.id, channelName: item.name, isAdminOnly: item.is_admin_only });
    };

    const handleDelete = (id: string, name: string) => {
        Alert.alert("Delete Channel", `Are you sure you want to delete #${name}?`, [
            { text: "Cancel", style: "cancel" },
            { text: "Delete", style: "destructive", onPress: () => { } }
        ]);
    };

    const renderChannel = ({ item }: { item: any }) => (
        <TouchableOpacity style={styles.card} onPress={() => handleChannelPress(item)} activeOpacity={0.7}>
            <View style={styles.info}>
                <Text style={styles.name}>#{item.name}</Text>
                <Text style={styles.desc} numberOfLines={1}>{item.description}</Text>
                {item.is_admin_only && (
                    <View style={styles.adminBadge}><Text style={styles.adminText}>Admin Only</Text></View>
                )}
            </View>
            <TouchableOpacity onPress={() => handleDelete(item.id, item.name)} style={styles.btn}>
                <Ionicons name="trash-outline" size={18} color={colors.error} />
            </TouchableOpacity>
        </TouchableOpacity>
    );

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Manage Forums</Text>
                <TouchableOpacity style={styles.createBtn} activeOpacity={0.7}>
                    <Text style={styles.createBtnText}>New Channel</Text>
                </TouchableOpacity>
            </View>
            {loading ? (
                <View style={styles.center}><ActivityIndicator color={colors.foreground} /></View>
            ) : (
                <FlatList data={channels} renderItem={renderChannel} keyExtractor={(item) => item.id} contentContainerStyle={styles.list} />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.lg, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    title: { ...typography.h2 },
    createBtn: { backgroundColor: colors.foreground, paddingHorizontal: 14, paddingVertical: 8, borderRadius: borderRadius.full, ...shadows.sm },
    createBtnText: { color: colors.buttonText, fontWeight: '600', fontSize: 13 },
    list: { paddingHorizontal: spacing.lg },
    card: {
        flexDirection: 'row', alignItems: 'center',
        backgroundColor: colors.card, borderRadius: borderRadius.lg,
        padding: spacing.md, marginBottom: spacing.sm,
        ...shadows.sm,
    },
    info: { flex: 1 },
    name: { fontSize: 14, fontWeight: '600', color: colors.foreground },
    desc: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
    adminBadge: { marginTop: 4 },
    adminText: { fontSize: 10, color: colors.textSecondary, fontWeight: '600' },
    btn: { padding: 8 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});
