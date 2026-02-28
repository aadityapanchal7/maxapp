import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, Modal, TextInput, Alert, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function ProfileScreen() {
    const navigation = useNavigation<any>();
    const { user, logout, refreshUser } = useAuth();
    const [scans, setScans] = useState<any[]>([]);
    const [myRank, setMyRank] = useState<any>(null);
    const [editModalVisible, setEditModalVisible] = useState(false);
    const [editBio, setEditBio] = useState('');
    const [editAvatarUri, setEditAvatarUri] = useState<string | null>(null);
    const [saveLoading, setSaveLoading] = useState(false);

    useEffect(() => { loadData(); }, []);

    const loadData = async () => {
        try { const scanHistory = await api.getScanHistory().catch(() => ({ scans: [] })); setScans(scanHistory.scans || []); const rank = await api.getMyRank().catch(() => null); setMyRank(rank); } catch (e) { console.error(e); }
    };

    const handleEditPress = () => { setEditBio(user?.profile?.bio || ''); setEditAvatarUri(null); setEditModalVisible(true); };
    const pickImage = async () => { const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, aspect: [1, 1], quality: 0.8 }); if (!result.canceled) setEditAvatarUri(result.assets[0].uri); };

    const saveProfile = async () => {
        setSaveLoading(true);
        try {
            let newAvatarUrl = user?.profile?.avatar_url;
            if (editAvatarUri) { const res = await api.uploadAvatar(editAvatarUri); newAvatarUrl = res.avatar_url; }
            await api.updateProfile({ bio: editBio, avatar_url: newAvatarUrl });
            await refreshUser(); setEditModalVisible(false); Alert.alert('Success', 'Profile updated!');
        } catch (e) { console.error(e); Alert.alert('Error', 'Failed to update profile'); }
        finally { setSaveLoading(false); }
    };

    const safeNumber = (val: any, fallback: string = '-'): string => { const num = parseFloat(val); return isNaN(num) ? fallback : num.toFixed(1); };

    return (
        <View style={styles.container}>
            <View style={styles.topBar}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={22} color={colors.textPrimary} />
                </TouchableOpacity>
                <Text style={styles.topBarTitle}>Profile</Text>
                <View style={{ width: 40 }} />
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={handleEditPress} style={styles.avatarContainer}>
                        {user?.profile?.avatar_url ? (
                            <Image source={{ uri: user.profile.avatar_url }} style={styles.avatarImage} />
                        ) : (
                            <View style={styles.avatarPlaceholder}><Ionicons name="person" size={48} color={colors.textMuted} /></View>
                        )}
                        <View style={styles.editIcon}><Ionicons name="pencil" size={12} color={colors.buttonText} /></View>
                    </TouchableOpacity>
                    <Text style={styles.email}>{user?.email}</Text>
                    {user?.profile?.bio ? <Text style={styles.bio}>{user.profile.bio}</Text> : null}
                    <TouchableOpacity style={styles.editButtonSmall} onPress={handleEditPress}><Text style={styles.editButtonText}>Edit Profile</Text></TouchableOpacity>
                </View>

                <View style={styles.statsCard}>
                    <View style={styles.statItem}><Text style={styles.statValue}>{safeNumber(user?.profile?.current_level)}</Text><Text style={styles.statLabel}>Level</Text></View>
                    <View style={styles.divider} />
                    <View style={styles.statItem}><Text style={styles.statValue}>{myRank?.rank !== null ? `#${myRank?.rank}` : '-'}</Text><Text style={styles.statLabel}>Rank</Text></View>
                    <View style={styles.divider} />
                    <View style={styles.statItem}><Text style={styles.statValue}>{scans.length}</Text><Text style={styles.statLabel}>Scans</Text></View>
                </View>

                <Text style={styles.sectionTitle}>Scan History</Text>
                <View style={styles.scanList}>
                    {scans.length > 0 ? scans.map((scan, i) => (
                        <TouchableOpacity key={i} style={styles.scanItem} onPress={() => navigation.navigate('ScanDetail', { scanId: scan.id })}>
                            <Ionicons name="scan" size={20} color={colors.textSecondary} />
                            <View style={styles.scanInfo}><Text style={styles.scanDate}>{new Date(scan.created_at).toLocaleDateString()}</Text></View>
                            <Text style={styles.scanScore}>{safeNumber(scan.overall_score)}</Text>
                            <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                        </TouchableOpacity>
                    )) : <Text style={styles.emptyText}>No scans yet. Start your first scan!</Text>}
                </View>

                <TouchableOpacity style={styles.logoutButton} onPress={logout}>
                    <Ionicons name="log-out" size={20} color={colors.error} />
                    <Text style={styles.logoutText}>Logout</Text>
                </TouchableOpacity>
            </ScrollView>

            <Modal animationType="slide" transparent visible={editModalVisible} onRequestClose={() => setEditModalVisible(false)}>
                <View style={styles.modalOverlay}>
                    <View style={styles.modalContent}>
                        <View style={styles.modalHeader}>
                            <Text style={styles.modalTitle}>Edit Profile</Text>
                            <TouchableOpacity onPress={() => setEditModalVisible(false)} style={styles.modalClose} activeOpacity={0.7}>
                                <Ionicons name="close" size={20} color={colors.textSecondary} />
                            </TouchableOpacity>
                        </View>
                        <TouchableOpacity onPress={pickImage} style={styles.modalAvatarContainer}>
                            {editAvatarUri ? <Image source={{ uri: editAvatarUri }} style={styles.modalAvatar} /> : user?.profile?.avatar_url ? <Image source={{ uri: user.profile.avatar_url }} style={styles.modalAvatar} /> : <View style={styles.modalAvatarPlaceholder}><Ionicons name="camera" size={32} color={colors.textMuted} /></View>}
                            <Text style={styles.changePhotoText}>Change Photo</Text>
                        </TouchableOpacity>
                        <Text style={styles.inputLabel}>Bio</Text>
                        <TextInput style={styles.bioInput} value={editBio} onChangeText={setEditBio} multiline numberOfLines={3} placeholder="Tell us about yourself..." placeholderTextColor={colors.textMuted} />
                        <View style={styles.modalButtons}>
                            <TouchableOpacity style={styles.cancelButton} onPress={() => setEditModalVisible(false)}><Text style={styles.cancelButtonText}>Cancel</Text></TouchableOpacity>
                            <TouchableOpacity style={styles.saveButton} onPress={saveProfile} disabled={saveLoading}>{saveLoading ? <ActivityIndicator color="#FFF" /> : <Text style={styles.saveButtonText}>Save</Text>}</TouchableOpacity>
                        </View>
                    </View>
                </View>
            </Modal>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    topBar: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        paddingTop: 52, paddingHorizontal: spacing.md, paddingBottom: spacing.sm,
    },
    backButton: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
    topBarTitle: { fontSize: 16, fontWeight: '600', color: colors.textPrimary },
    header: { alignItems: 'center', paddingTop: spacing.md, paddingBottom: spacing.xl },
    avatarContainer: { position: 'relative' },
    avatarImage: { width: 100, height: 100, borderRadius: 50, borderWidth: 2, borderColor: colors.border },
    avatarPlaceholder: { width: 100, height: 100, borderRadius: 50, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: colors.border },
    editIcon: { position: 'absolute', bottom: 0, right: 0, backgroundColor: colors.accent, borderRadius: 12, width: 24, height: 24, justifyContent: 'center', alignItems: 'center' },
    email: { ...typography.body, marginTop: spacing.md, fontWeight: '600' },
    bio: { ...typography.bodySmall, marginTop: 4, textAlign: 'center', paddingHorizontal: spacing.xl },
    editButtonSmall: { marginTop: spacing.md, paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
    editButtonText: { ...typography.caption },
    statsCard: { flexDirection: 'row', marginHorizontal: spacing.lg, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.lg, ...shadows.sm },
    statItem: { flex: 1, alignItems: 'center' },
    statValue: { fontSize: 28, fontFamily: 'Matter-Medium', fontWeight: '500', color: colors.accent },
    statLabel: { ...typography.caption, marginTop: 4 },
    divider: { width: 1, backgroundColor: colors.border },
    sectionTitle: { ...typography.h3, marginHorizontal: spacing.lg, marginTop: spacing.xl, marginBottom: spacing.md },
    scanList: { marginHorizontal: spacing.lg, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.md, ...shadows.sm },
    scanItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
    scanInfo: { flex: 1, marginLeft: spacing.md },
    scanDate: { ...typography.bodySmall },
    scanScore: { ...typography.h3, marginRight: spacing.sm },
    emptyText: { ...typography.bodySmall, textAlign: 'center', padding: spacing.lg },
    logoutButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginTop: spacing.xl, marginBottom: spacing.xxl, gap: spacing.sm },
    logoutText: { ...typography.body, color: colors.error },
    modalOverlay: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', padding: spacing.lg },
    modalContent: { backgroundColor: colors.background, borderRadius: borderRadius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, ...shadows.lg },
    modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.lg },
    modalTitle: { ...typography.h3 },
    modalClose: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
    modalAvatarContainer: { alignSelf: 'center', alignItems: 'center', marginBottom: spacing.lg },
    modalAvatar: { width: 80, height: 80, borderRadius: 40 },
    modalAvatarPlaceholder: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center' },
    changePhotoText: { ...typography.caption, color: colors.info, marginTop: spacing.sm },
    inputLabel: { ...typography.caption, marginBottom: spacing.xs, marginLeft: 4 },
    bioInput: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, color: colors.textPrimary, fontSize: 14, textAlignVertical: 'top', minHeight: 80, borderWidth: 1, borderColor: colors.border },
    modalButtons: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: spacing.lg, gap: spacing.md },
    cancelButton: { padding: spacing.md },
    cancelButtonText: { ...typography.button, color: colors.textMuted },
    saveButton: { backgroundColor: colors.primary, borderRadius: borderRadius.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
    saveButtonText: { ...typography.button },
});
