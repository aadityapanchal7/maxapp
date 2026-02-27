import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function ForumManageScreen() {
    const navigation = useNavigation<any>();
    const [channels, setChannels] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadChannels();
    }, []);

    const loadChannels = async () => {
        try {
            const { forums } = await api.getChannels();
            setChannels(forums || []);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const handleChannelPress = (item: any) => {
        navigation.navigate('ChannelChat', {
            channelId: item.id,
            channelName: item.name,
            isAdminOnly: item.is_admin_only
        });
    };

    const handleDelete = (id: string, name: string) => {
        Alert.alert(
            "Delete Channel",
            `Are you sure you want to delete #${name}? This cannot be undone.`,
            [
                { text: "Cancel", style: "cancel" },
                { text: "Delete", style: "destructive", onPress: () => { } } // TODO: Implement delete API
            ]
        );
    };

    const renderChannel = ({ item }: { item: any }) => (
        <TouchableOpacity style={styles.card} onPress={() => handleChannelPress(item)} activeOpacity={0.7}>
            <View style={styles.info}>
                <Text style={styles.name}>#{item.name}</Text>
                <Text style={styles.desc} numberOfLines={1}>{item.description}</Text>
                {item.is_admin_only && (
                    <View style={styles.adminBadge}>
                        <Ionicons name="shield-checkmark" size={12} color={colors.primaryLight} />
                        <Text style={styles.adminText}>Admin Only</Text>
                    </View>
                )}
            </View>
            <View style={styles.actions}>
                <TouchableOpacity onPress={() => handleDelete(item.id, item.name)} style={styles.btn}>
                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                </TouchableOpacity>
            </View>
        </TouchableOpacity>
    );

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Manage Forums</Text>
                <TouchableOpacity style={styles.createBtn}>
                    <Ionicons name="add" size={20} color="#FFF" />
                    <Text style={styles.createBtnText}>New Channel</Text>
                </TouchableOpacity>
            </View>

            {loading ? (
                <View style={styles.center}><ActivityIndicator color={colors.primaryLight} /></View>
            ) : (
                <FlatList
                    data={channels}
                    renderItem={renderChannel}
                    keyExtractor={(item) => item.id}
                    contentContainerStyle={styles.list}
                />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.md, backgroundColor: colors.surface, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    title: { ...typography.h2, color: '#FFFFFF' },
    createBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: borderRadius.md },
    createBtnText: { color: '#FFF', fontWeight: '600', marginLeft: 4 },
    list: { padding: spacing.md },
    card: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.sm },
    info: { flex: 1 },
    name: { ...typography.body, fontWeight: 'bold', color: '#FFFFFF' },
    desc: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
    adminBadge: { flexDirection: 'row', alignItems: 'center', marginTop: 4, gap: 4 },
    adminText: { fontSize: 10, color: colors.primaryLight, fontWeight: 'bold' },
    actions: { flexDirection: 'row', gap: 8 },
    btn: { padding: 8 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});
