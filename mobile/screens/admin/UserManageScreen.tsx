import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, TextInput, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function UserManageScreen({ navigation }: any) {
    const [users, setUsers] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');

    useEffect(() => {
        loadUsers();
    }, [search]);

    const loadUsers = async () => {
        try {
            const data = await api.getAdminUsers(search);
            setUsers(data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const renderUser = ({ item }: { item: any }) => (
        <TouchableOpacity
            style={styles.userCard}
            activeOpacity={0.7}
            onPress={() => navigation.navigate('AdminUserChat', { userId: item.id, userEmail: item.email })}
        >
            <View style={styles.userInfo}>
                <Text style={styles.userEmail}>{item.email}</Text>
                <View style={styles.tagRow}>
                    {item.is_admin && <View style={[styles.tag, { backgroundColor: colors.primary }]}><Text style={styles.tagText}>ADMIN</Text></View>}
                    {item.is_paid && <View style={[styles.tag, { backgroundColor: '#FFD700' }]}><Text style={[styles.tagText, { color: '#000' }]}>PAID</Text></View>}
                    <Text style={styles.dateText}>Joined {new Date(item.created_at).toLocaleDateString()}</Text>
                </View>
            </View>
            <View style={styles.actionBtn}>
                <Ionicons name="chatbubble-outline" size={20} color={colors.primaryLight} />
            </View>
        </TouchableOpacity>
    );

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Manage Users</Text>
                <View style={styles.searchBox}>
                    <Ionicons name="search" size={18} color={colors.textMuted} />
                    <TextInput
                        style={styles.input}
                        placeholder="Search users..."
                        placeholderTextColor={colors.textMuted}
                        value={search}
                        onChangeText={setSearch}
                    />
                </View>
            </View>

            {loading ? (
                <View style={styles.center}><ActivityIndicator color={colors.primaryLight} /></View>
            ) : (
                <FlatList
                    data={users}
                    renderItem={renderUser}
                    keyExtractor={(item) => item.id}
                    contentContainerStyle={styles.list}
                    ListEmptyComponent={<Text style={styles.emptyText}>No users found</Text>}
                />
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { padding: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
    title: { ...typography.h2, color: '#FFFFFF', marginBottom: spacing.md },
    searchBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: borderRadius.md, paddingHorizontal: spacing.sm, height: 40 },
    input: { flex: 1, color: '#FFFFFF', marginLeft: spacing.sm },
    list: { padding: spacing.md },
    userCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, marginBottom: spacing.sm, borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)' },
    userInfo: { flex: 1 },
    userEmail: { ...typography.body, fontWeight: '600', color: '#FFFFFF' },
    tagRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4, gap: 8 },
    tag: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
    tagText: { fontSize: 10, fontWeight: 'bold', color: '#FFF' },
    dateText: { fontSize: 11, color: colors.textMuted },
    actionBtn: { padding: 8 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    emptyText: { textAlign: 'center', color: colors.textMuted, marginTop: 40 },
});
