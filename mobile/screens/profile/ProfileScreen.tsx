import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, Modal, TextInput, Alert, ActivityIndicator } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function ProfileScreen() {
    const navigation = useNavigation<any>();
    const { user, logout, refreshUser } = useAuth();
    const [scans, setScans] = useState<any[]>([]);
    const [myRank, setMyRank] = useState<any>(null);

    // Edit Mode State
    const [editModalVisible, setEditModalVisible] = useState(false);
    const [editBio, setEditBio] = useState('');
    const [editAvatarUri, setEditAvatarUri] = useState<string | null>(null);
    const [saveLoading, setSaveLoading] = useState(false);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const scanHistory = await api.getScanHistory().catch(() => ({ scans: [] }));
            setScans(scanHistory.scans || []);
            const rank = await api.getMyRank().catch(() => null);
            setMyRank(rank);
        } catch (error) {
            console.error(error);
        }
    };

    const handleEditPress = () => {
        setEditBio(user?.profile?.bio || '');
        setEditAvatarUri(null); // Reset new avatar choice
        setEditModalVisible(true);
    };

    const pickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ImagePicker.MediaTypeOptions.Images,
            allowsEditing: true,
            aspect: [1, 1],
            quality: 0.8,
        });

        if (!result.canceled) {
            setEditAvatarUri(result.assets[0].uri);
        }
    };

    const saveProfile = async () => {
        setSaveLoading(true);
        try {
            // 1. Upload new avatar if selected
            let newAvatarUrl = user?.profile?.avatar_url;
            if (editAvatarUri) {
                const res = await api.uploadAvatar(editAvatarUri);
                newAvatarUrl = res.avatar_url;
            }

            // 2. Update profile (bio + avatar_url if changed)
            await api.updateProfile({
                bio: editBio,
                avatar_url: newAvatarUrl
            });

            await refreshUser(); // Reload user context
            setEditModalVisible(false);
            Alert.alert('Success', 'Profile updated!');
        } catch (error) {
            console.error(error);
            Alert.alert('Error', 'Failed to update profile');
        } finally {
            setSaveLoading(false);
        }
    };

    const safeNumber = (val: any, fallback: string = '-'): string => {
        const num = parseFloat(val);
        return isNaN(num) ? fallback : num.toFixed(1);
    };

    return (
        <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
            <ScrollView showsVerticalScrollIndicator={false}>
                <View style={styles.header}>
                    <TouchableOpacity onPress={handleEditPress} style={styles.avatarContainer}>
                        {user?.profile?.avatar_url ? (
                            <Image source={{ uri: user.profile.avatar_url }} style={styles.avatarImage} />
                        ) : (
                            <View style={styles.avatarPlaceholder}>
                                <Ionicons name="person" size={48} color="rgba(255,255,255,0.6)" />
                            </View>
                        )}
                        <View style={styles.editIcon}>
                            <Ionicons name="pencil" size={12} color="#FFFFFF" />
                        </View>
                    </TouchableOpacity>

                    <Text style={styles.email}>{user?.email}</Text>
                    {user?.profile?.bio ? (
                        <Text style={styles.bio}>{user.profile.bio}</Text>
                    ) : null}

                    <TouchableOpacity style={styles.editButtonSmall} onPress={handleEditPress}>
                        <Text style={styles.editButtonText}>Edit Profile</Text>
                    </TouchableOpacity>
                </View>

                {/* Stats Card */}
                <View style={styles.statsCard}>
                    <View style={styles.statItem}>
                        <Text style={styles.statValue}>{safeNumber(user?.profile?.current_level)}</Text>
                        <Text style={styles.statLabel}>Level</Text>
                    </View>
                    <View style={styles.divider} />
                    <View style={styles.statItem}>
                        <Text style={styles.statValue}>{myRank?.rank !== null ? `#${myRank?.rank}` : '-'}</Text>
                        <Text style={styles.statLabel}>Rank</Text>
                    </View>
                    <View style={styles.divider} />
                    <View style={styles.statItem}>
                        <Text style={styles.statValue}>{scans.length}</Text>
                        <Text style={styles.statLabel}>Scans</Text>
                    </View>
                </View>

                {/* Scan History */}
                <Text style={styles.sectionTitle}>Scan History</Text>
                <View style={styles.scanList}>
                    {scans.length > 0 ? scans.map((scan, i) => (
                        <TouchableOpacity
                            key={i}
                            style={styles.scanItem}
                            onPress={() => navigation.navigate('ScanDetail', { scanId: scan.id })}
                        >
                            <Ionicons name="scan" size={20} color="#FFFFFF" />
                            <View style={styles.scanInfo}>
                                <Text style={styles.scanDate}>{new Date(scan.created_at).toLocaleDateString()}</Text>
                            </View>
                            <Text style={styles.scanScore}>{safeNumber(scan.overall_score)}</Text>
                            <Ionicons name="chevron-forward" size={16} color="rgba(255,255,255,0.5)" />
                        </TouchableOpacity>
                    )) : (
                        <Text style={styles.emptyText}>No scans yet. Start your first scan!</Text>
                    )}
                </View>

                {/* Logout */}
                <TouchableOpacity style={styles.logoutButton} onPress={logout}>
                    <Ionicons name="log-out" size={20} color="#FF4757" />
                    <Text style={styles.logoutText}>Logout</Text>
                </TouchableOpacity>
            </ScrollView>

            {/* Edit Profile Modal */}
            <Modal
                animationType="slide"
                transparent={true}
                visible={editModalVisible}
                onRequestClose={() => setEditModalVisible(false)}
            >
                <View style={styles.modalOverlay}>
                    <View style={styles.modalContent}>
                        <Text style={styles.modalTitle}>Edit Profile</Text>

                        <TouchableOpacity onPress={pickImage} style={styles.modalAvatarContainer}>
                            {editAvatarUri ? (
                                <Image source={{ uri: editAvatarUri }} style={styles.modalAvatar} />
                            ) : user?.profile?.avatar_url ? (
                                <Image source={{ uri: user.profile.avatar_url }} style={styles.modalAvatar} />
                            ) : (
                                <View style={styles.modalAvatarPlaceholder}>
                                    <Ionicons name="camera" size={32} color="rgba(255,255,255,0.5)" />
                                </View>
                            )}
                            <Text style={styles.changePhotoText}>Change Photo</Text>
                        </TouchableOpacity>

                        <Text style={styles.inputLabel}>Bio</Text>
                        <TextInput
                            style={styles.bioInput}
                            value={editBio}
                            onChangeText={setEditBio}
                            multiline
                            numberOfLines={3}
                            placeholder="Tell us about yourself..."
                            placeholderTextColor="rgba(255,255,255,0.3)"
                        />

                        <View style={styles.modalButtons}>
                            <TouchableOpacity style={styles.cancelButton} onPress={() => setEditModalVisible(false)}>
                                <Text style={styles.cancelButtonText}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={styles.saveButton}
                                onPress={saveProfile}
                                disabled={saveLoading}
                            >
                                {saveLoading ? (
                                    <ActivityIndicator color="#000" />
                                ) : (
                                    <Text style={styles.saveButtonText}>Save</Text>
                                )}
                            </TouchableOpacity>
                        </View>
                    </View>
                </View>
            </Modal>
        </LinearGradient>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1 },
    header: { alignItems: 'center', paddingTop: 80, paddingBottom: spacing.xl },

    avatarContainer: { position: 'relative' },
    avatarImage: { width: 100, height: 100, borderRadius: 50, borderWidth: 2, borderColor: 'rgba(255,255,255,0.3)' },
    avatarPlaceholder: { width: 100, height: 100, borderRadius: 50, backgroundColor: 'rgba(255,255,255,0.1)', justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: 'rgba(255,255,255,0.3)' },
    editIcon: { position: 'absolute', bottom: 0, right: 0, backgroundColor: '#000000', borderRadius: 12, width: 24, height: 24, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: '#FFFFFF' },

    email: { ...typography.body, marginTop: spacing.md, color: '#FFFFFF', fontWeight: '600' },
    bio: { ...typography.bodySmall, marginTop: 4, color: 'rgba(255,255,255,0.7)', textAlign: 'center', paddingHorizontal: spacing.xl },
    editButtonSmall: { marginTop: spacing.md, paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
    editButtonText: { ...typography.caption, color: '#FFFFFF' },

    statsCard: { flexDirection: 'row', marginHorizontal: spacing.lg, backgroundColor: '#FFFFFF', borderRadius: borderRadius.lg, padding: spacing.lg },
    statItem: { flex: 1, alignItems: 'center' },
    statValue: { fontSize: 28, fontFamily: 'Matter-Medium', fontWeight: '500', color: '#000000' },
    statLabel: { ...typography.caption, marginTop: 4, color: 'rgba(0,0,0,0.5)' },
    divider: { width: 1, backgroundColor: 'rgba(0,0,0,0.1)' },
    sectionTitle: { ...typography.h3, marginHorizontal: spacing.lg, marginTop: spacing.xl, marginBottom: spacing.md, color: '#FFFFFF' },
    scanList: { marginHorizontal: spacing.lg, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: borderRadius.lg, padding: spacing.md, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
    scanItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.1)' },
    scanInfo: { flex: 1, marginLeft: spacing.md },
    scanDate: { ...typography.bodySmall, color: 'rgba(255,255,255,0.7)' },
    scanScore: { ...typography.h3, color: '#FFFFFF', marginRight: spacing.sm },
    emptyText: { ...typography.bodySmall, color: 'rgba(255,255,255,0.6)', textAlign: 'center', padding: spacing.lg },
    logoutButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginTop: spacing.xl, marginBottom: spacing.xxl, gap: spacing.sm },
    logoutText: { ...typography.body, color: '#FF4757' },

    // Modal Styles
    modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', padding: spacing.lg },
    modalContent: { backgroundColor: '#1A1A1A', borderRadius: borderRadius.lg, padding: spacing.lg, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
    modalTitle: { ...typography.h3, color: '#FFFFFF', marginBottom: spacing.lg, textAlign: 'center' },
    modalAvatarContainer: { alignSelf: 'center', alignItems: 'center', marginBottom: spacing.lg },
    modalAvatar: { width: 80, height: 80, borderRadius: 40 },
    modalAvatarPlaceholder: { width: 80, height: 80, borderRadius: 40, backgroundColor: 'rgba(255,255,255,0.1)', justifyContent: 'center', alignItems: 'center' },
    changePhotoText: { ...typography.caption, color: '#3498db', marginTop: spacing.sm },
    inputLabel: { ...typography.caption, color: 'rgba(255,255,255,0.5)', marginBottom: spacing.xs, marginLeft: 4 },
    bioInput: { backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: borderRadius.md, padding: spacing.md, color: '#FFFFFF', fontSize: 14, textAlignVertical: 'top', minHeight: 80, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
    modalButtons: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: spacing.lg, gap: spacing.md },
    cancelButton: { padding: spacing.md },
    cancelButtonText: { ...typography.button, color: 'rgba(255,255,255,0.5)' },
    saveButton: { backgroundColor: '#FFFFFF', borderRadius: borderRadius.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
    saveButtonText: { ...typography.button, color: '#000000' },
});

