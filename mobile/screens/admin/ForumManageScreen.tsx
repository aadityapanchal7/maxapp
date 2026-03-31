import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import api from '../../services/api';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

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

    const renderChannel = ({ item }: { item: any }) => {
        const official = !!item.is_admin_only;
        return (
            <TouchableOpacity style={styles.card} onPress={() => handleChannelPress(item)} activeOpacity={0.72}>
                <View style={[styles.channelIcon, official ? styles.channelIconOfficial : styles.channelIconCommunity]}>
                    <Ionicons name={official ? 'megaphone-outline' : 'chatbubbles-outline'} size={22} color={official ? colors.info : colors.textSecondary} />
                </View>
                <View style={styles.info}>
                    <Text style={styles.name} numberOfLines={2}>{item.name}</Text>
                    {item.description ? (
                        <Text style={styles.desc} numberOfLines={2}>{item.description}</Text>
                    ) : null}
                    {official && (
                        <View style={styles.adminPill}>
                            <Text style={styles.adminText}>Official</Text>
                        </View>
                    )}
                </View>
                <TouchableOpacity onPress={() => handleDelete(item.id, item.name)} style={styles.btn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                </TouchableOpacity>
            </TouchableOpacity>
        );
    };

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Manage forums</Text>
                <TouchableOpacity style={styles.createBtn} activeOpacity={0.7}>
                    <Text style={styles.createBtnText}>New channel</Text>
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
    header: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.lg,
        paddingBottom: spacing.md,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.borderLight,
    },
    title: { fontSize: 28, fontWeight: '700', color: colors.foreground, letterSpacing: -0.8 },
    createBtn: {
        backgroundColor: colors.foreground,
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderRadius: borderRadius.lg,
    },
    createBtnText: { color: colors.buttonText, fontWeight: '700', fontSize: 13 },
    list: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
    card: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        marginBottom: 12,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: 'transparent',
        ...shadows.sm,
    },
    channelIcon: {
        width: 48,
        height: 48,
        borderRadius: borderRadius.lg,
        alignItems: 'center',
        justifyContent: 'center',
        marginRight: spacing.md,
    },
    channelIconOfficial: { backgroundColor: 'rgba(59, 130, 246, 0.1)' },
    channelIconCommunity: { backgroundColor: colors.surface },
    info: { flex: 1, minWidth: 0 },
    name: { fontSize: 16, fontWeight: '600', color: colors.foreground, letterSpacing: -0.3 },
    desc: { fontSize: 13, color: colors.textSecondary, marginTop: 4, lineHeight: 18 },
    adminPill: {
        alignSelf: 'flex-start',
        marginTop: 8,
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: borderRadius.full,
        backgroundColor: 'rgba(59, 130, 246, 0.12)',
    },
    adminText: { fontSize: 11, color: colors.info, fontWeight: '700' },
    btn: { padding: 8 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});
