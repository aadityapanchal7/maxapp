import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function ForumsScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const [forums, setForums] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [activeChannelId, setActiveChannelId] = useState<string | null>(null);

    useFocusEffect(React.useCallback(() => { loadForums(); }, [searchQuery]));

    const loadForums = async () => {
        try { setLoading(true); const { forums: data } = await api.getChannels(searchQuery); setForums(data || []); if (data?.length > 0 && !activeChannelId) setActiveChannelId(data[0].id); }
        catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const handleChannelPress = (item: any) => {
        setActiveChannelId(item.id);
        navigation.navigate('ChannelChat', { channelId: item.id, channelName: item.name, isAdminOnly: item.is_admin_only });
    };

    const categorizedForums = [
        { title: 'OFFICIAL', channels: forums.filter(f => f.name.toLowerCase().includes('announce') || f.name.toLowerCase().includes('welcome')) },
        { title: 'COMMUNITY', channels: forums.filter(f => !f.name.toLowerCase().includes('announce') && !f.name.toLowerCase().includes('welcome')) },
    ];

    return (
        <View style={[styles.container, { paddingTop: insets.top }]}>
            <View style={styles.header}>
                <Text style={styles.headerTitle}>Forums</Text>
                <View style={styles.searchContainer}>
                    <Ionicons name="search" size={18} color={colors.textMuted} style={styles.searchIcon} />
                    <TextInput style={styles.searchInput} placeholder="Search channels..." placeholderTextColor={colors.textMuted} value={searchQuery} onChangeText={setSearchQuery} />
                    {searchQuery !== '' && <TouchableOpacity onPress={() => setSearchQuery('')}><Ionicons name="close-circle" size={18} color={colors.textMuted} /></TouchableOpacity>}
                </View>
            </View>

            {loading && forums.length === 0 ? (
                <View style={styles.center}><ActivityIndicator color={colors.primary} /></View>
            ) : (
                <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
                    {categorizedForums.map((category) => category.channels.length > 0 && (
                        <View key={category.title} style={styles.section}>
                            <Text style={styles.sectionTitle}>{category.title}</Text>
                            {category.channels.map(channel => (
                                <TouchableOpacity key={channel.id} style={[styles.card, activeChannelId === channel.id && styles.activeCard]} onPress={() => handleChannelPress(channel)}>
                                    <View style={styles.iconContainer}><Text style={styles.hash}>#</Text></View>
                                    <View style={styles.info}>
                                        <Text style={styles.channelName}>{channel.name}</Text>
                                        <Text style={styles.channelDesc} numberOfLines={1}>{channel.description}</Text>
                                    </View>
                                    <Ionicons name="chevron-forward" size={20} color={activeChannelId === channel.id ? colors.accent : colors.textMuted} />
                                </TouchableOpacity>
                            ))}
                        </View>
                    ))}
                    {forums.length === 0 && (
                        <View style={styles.empty}>
                            <Ionicons name="search-outline" size={48} color={colors.textMuted} />
                            <Text style={styles.emptyText}>No channels found</Text>
                        </View>
                    )}
                    <View style={{ height: insets.bottom + 20 }} />
                </ScrollView>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.md },
    headerTitle: { ...typography.h1, marginBottom: spacing.sm },
    searchContainer: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: borderRadius.md, paddingHorizontal: spacing.sm, height: 44, borderWidth: 1, borderColor: colors.border },
    searchIcon: { marginRight: spacing.xs },
    searchInput: { flex: 1, color: colors.textPrimary, fontSize: 16 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    list: { flex: 1, paddingHorizontal: spacing.md },
    section: { marginBottom: spacing.lg },
    sectionTitle: { ...typography.caption, color: colors.textMuted, fontWeight: 'bold', marginBottom: spacing.sm, letterSpacing: 1 },
    card: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md, marginBottom: spacing.sm, ...shadows.sm },
    activeCard: { borderWidth: 1, borderColor: colors.accent },
    iconContainer: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.background, justifyContent: 'center', alignItems: 'center', marginRight: spacing.md, borderWidth: 1, borderColor: colors.border },
    hash: { color: colors.textPrimary, fontSize: 18, fontWeight: 'bold' },
    info: { flex: 1 },
    channelName: { ...typography.body, fontWeight: '600' },
    channelDesc: { ...typography.caption, marginTop: 2 },
    empty: { alignItems: 'center', marginTop: 100 },
    emptyText: { ...typography.body, color: colors.textMuted, marginTop: spacing.md },
});
