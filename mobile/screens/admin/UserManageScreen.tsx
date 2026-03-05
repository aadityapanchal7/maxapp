import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, TextInput, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function UserManageScreen({ navigation }: any) {
    const [users, setUsers] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');

    useEffect(() => { loadUsers(); }, [search]);

    const loadUsers = async () => {
        try { const data = await api.getAdminUsers(search); setUsers(data); }
        catch (error) { console.error(error); }
        finally { setLoading(false); }
    };

    const renderUser = ({ item }: { item: any }) => (
        <TouchableOpacity style={styles.userCard} activeOpacity={0.7} onPress={() => navigation.navigate('AdminUserChat', { userId: item.id, userEmail: item.email })}>
            <View style={styles.userInfo}>
                <Text style={styles.userEmail}>{item.email}</Text>
                <View style={styles.tagRow}>
                    {item.is_admin && <View style={styles.tag}><Text style={styles.tagText}>ADMIN</Text></View>}
                    {item.is_paid && <View style={styles.tag}><Text style={styles.tagText}>PAID</Text></View>}
                    <Text style={styles.dateText}>Joined {new Date(item.created_at).toLocaleDateString()}</Text>
                </View>
            </View>
            <Ionicons name="chatbubble-outline" size={18} color={colors.textMuted} />
        </TouchableOpacity>
    );

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Manage Users</Text>
                <View style={styles.searchBox}>
                    <Ionicons name="search" size={16} color={colors.textMuted} />
                    <TextInput style={styles.input} placeholder="Search users..." placeholderTextColor={colors.textMuted} value={search} onChangeText={setSearch} />
                </View>
            </View>
            {loading ? (
                <View style={styles.center}><ActivityIndicator color={colors.foreground} /></View>
            ) : (
                <FlatList data={users} renderItem={renderUser} keyExtractor={(item) => item.id} contentContainerStyle={styles.list} ListEmptyComponent={<Text style={styles.emptyText}>No users found</Text>} />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.lg, borderBottomWidth: 1, borderBottomColor: colors.borderLight },
    title: { ...typography.h2, marginBottom: spacing.md },
    searchBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.card, borderRadius: borderRadius.md, paddingHorizontal: spacing.sm, height: 42, ...shadows.sm },
    input: { flex: 1, color: colors.textPrimary, marginLeft: spacing.sm, fontSize: 14 },
    list: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
    userCard: {
        flexDirection: 'row', alignItems: 'center',
        backgroundColor: colors.card, borderRadius: borderRadius.lg,
        padding: spacing.md, marginBottom: spacing.sm,
        ...shadows.sm,
    },
    userInfo: { flex: 1 },
    userEmail: { fontSize: 14, fontWeight: '600', color: colors.foreground },
    tagRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4, gap: 8 },
    tag: { backgroundColor: colors.foreground, paddingHorizontal: 6, paddingVertical: 2, borderRadius: borderRadius.full },
    tagText: { fontSize: 9, fontWeight: '700', color: colors.buttonText },
    dateText: { fontSize: 11, color: colors.textMuted },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    emptyText: { textAlign: 'center', color: colors.textMuted, marginTop: 40, fontSize: 14 },
});
