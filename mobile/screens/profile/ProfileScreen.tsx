import React, { useEffect, useState, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, Modal, TextInput, Alert, ActivityIndicator, Animated, Dimensions, Pressable, Platform, useWindowDimensions } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const getImageModalWidth = (width: number) =>
    Platform.OS === 'web' && width > 600
        ? Math.min(width - 80, 320)
        : Math.min(width - 64, 300);

function formatProgressDate(dateStr: string): string {
    const d = new Date(dateStr);
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    const day = d.getDate();
    const suffix = day === 1 || day === 21 || day === 31 ? 'st' : day === 2 || day === 22 ? 'nd' : day === 3 || day === 23 ? 'rd' : 'th';
    return `${months[d.getMonth()]} ${day}${suffix} ${d.getFullYear()}`;
}

export default function ProfileScreen() {
    const navigation = useNavigation<any>();
    const { width: winWidth } = useWindowDimensions();
    const isDesktop = Platform.OS === 'web' && winWidth > 480;
    const gridColumns = Platform.OS === 'web' ? (winWidth > 800 ? 3 : winWidth > 500 ? 2 : 3) : 3;
    const gridItemWidth = `${100 / gridColumns}%` as any;
    const imageModalWidth = getImageModalWidth(winWidth);
    const { user, logout, refreshUser } = useAuth();
    const [loading, setLoading] = useState(true);
    const [progressPhotos, setProgressPhotos] = useState<any[]>([]);
    const [progressModalVisible, setProgressModalVisible] = useState(false);
    const [selectedPhotoIndex, setSelectedPhotoIndex] = useState<number>(0);
    const [uploadingProgress, setUploadingProgress] = useState(false);
    const [editModalVisible, setEditModalVisible] = useState(false);
    const [editBio, setEditBio] = useState('');
    const [editFirstName, setEditFirstName] = useState('');
    const [editLastName, setEditLastName] = useState('');
    const [editUsername, setEditUsername] = useState('');
    const [editAvatarUri, setEditAvatarUri] = useState<string | null>(null);
    const [saveLoading, setSaveLoading] = useState(false);
    const fadeAnim = useRef(new Animated.Value(0)).current;

    useEffect(() => {
        loadData();
        Animated.timing(fadeAnim, { toValue: 1, duration: 400, useNativeDriver: true }).start();
    }, []);

    const loadData = async () => {
        try {
            const progressRes = await api.getProgressPhotos().catch(() => ({ photos: [] }));
            setProgressPhotos(progressRes.photos || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleEditPress = () => { 
        setEditBio(user?.profile?.bio || ''); 
        setEditFirstName(user?.first_name || ''); 
        setEditLastName(user?.last_name || ''); 
        setEditUsername(user?.username || ''); 
        setEditAvatarUri(null); 
        setEditModalVisible(true); 
    };
    const pickImage = async () => { const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.8 }); if (!result.canceled) setEditAvatarUri(result.assets[0].uri); };

    const uploadProgressImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ['images'],
            allowsEditing: true,
            aspect: [3, 4],
            quality: 0.9,
            base64: true,
        });
        if (result.canceled) return;

        const base64 = result.assets[0].base64;
        const uri = result.assets[0].uri;
        setUploadingProgress(true);
        try {
            if (base64) {
                await api.uploadProgressPhotoBase64(base64);
            } else {
                await api.uploadProgressPhoto(uri);
            }
            const progressRes = await api.getProgressPhotos().catch(() => ({ photos: [] }));
            setProgressPhotos(progressRes.photos || []);
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not upload progress photo. Please try again.');
        } finally {
            setUploadingProgress(false);
        }
    };

    const openProgressArchiveAt = (index: number) => {
        setSelectedPhotoIndex(index);
        setProgressModalVisible(true);
    };

    const saveProfile = async () => {
        setSaveLoading(true);
        try {
            let newAvatarUrl = user?.profile?.avatar_url;
            if (editAvatarUri) { 
                try {
                    const res = await api.uploadAvatar(editAvatarUri); 
                    newAvatarUrl = res.avatar_url; 
                } catch (avatarError: any) {
                    console.error('Avatar upload error:', avatarError);
                    // Continue with profile update even if avatar fails
                }
            }
            
            // Update profile (bio, avatar)
            try {
                await api.updateProfile({ bio: editBio, avatar_url: newAvatarUrl });
                console.log('Profile updated successfully');
            } catch (profileError: any) {
                console.error('Profile update error:', profileError);
                throw profileError;
            }
            
            // Update account info (first_name, last_name, username)
            const accountUpdates: any = {};
            const currentFirstName = user?.first_name || '';
            const currentLastName = user?.last_name || '';
            const currentUsername = user?.username || '';
            
            // Always include fields that have changed or are being set for the first time
            if (editFirstName.trim() !== currentFirstName) {
                accountUpdates.first_name = editFirstName.trim() || null;
            }
            if (editLastName.trim() !== currentLastName) {
                accountUpdates.last_name = editLastName.trim() || null;
            }
            if (editUsername.trim() !== currentUsername) {
                const trimmedUsername = editUsername.trim();
                if (trimmedUsername) {
                    if (trimmedUsername.length < 3) {
                        Alert.alert('Error', 'Username must be at least 3 characters');
                        setSaveLoading(false);
                        return;
                    }
                    if (!/^[a-zA-Z0-9_]+$/.test(trimmedUsername)) {
                        Alert.alert('Error', 'Username can only contain letters, numbers, and underscores');
                        setSaveLoading(false);
                        return;
                    }
                }
                accountUpdates.username = trimmedUsername || null;
            }
            
            // Always call updateAccount if there are any changes
            if (Object.keys(accountUpdates).length > 0) {
                console.log('Updating account with:', accountUpdates);
                try {
                    await api.updateAccount(accountUpdates);
                    console.log('Account updated successfully');
                } catch (accountError: any) {
                    console.error('Account update error:', accountError);
                    throw accountError;
                }
            } else {
                console.log('No account fields to update');
            }
            
            // Refresh user data to get latest changes
            await refreshUser(); 
            setEditModalVisible(false); 
            Alert.alert('Success', 'Profile updated!');
        } catch (e: any) { 
            console.error('Save profile error:', e); 
            console.error('Error response:', e?.response);
            console.error('Error response data:', e?.response?.data);
            const errorMsg = e?.response?.data?.detail || e?.message || 'Failed to update profile';
            Alert.alert('Error', errorMsg); 
        }
        finally { setSaveLoading(false); }
    };

    const renderSkeleton = () => (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
            <View style={styles.header}>
                <View style={[styles.avatarPlaceholder, styles.avatarSkeleton]} />
                <View style={styles.textSkeletonRow}>
                    <View style={styles.skeletonLine} />
                    <View style={[styles.skeletonLine, { width: '70%' }]} />
                </View>
                <View style={styles.textSkeletonBio} />
                <View style={styles.headerActionsRow}>
                    <View style={styles.pillSkeleton} />
                    <View style={styles.pillSkeleton} />
                </View>
            </View>
            <View style={styles.section}>
                <View style={[styles.skeletonLine, { width: 80, height: 18, marginBottom: 12 }]} />
                <View style={styles.archiveSkeletonRow}>
                    <View style={styles.archiveSkeletonItem} />
                    <View style={styles.archiveSkeletonItem} />
                    <View style={styles.archiveSkeletonItem} />
                </View>
            </View>
            <View style={styles.section}>
                <View style={[styles.skeletonLine, { height: 52, borderRadius: 12 }]} />
            </View>
        </ScrollView>
    );

    return (
        <View style={styles.container}>
            <View style={styles.topBar}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.topBarTitle}>Profile</Text>
                <View style={{ width: 40 }} />
            </View>

            {loading ? (
                renderSkeleton()
            ) : (
                <Animated.ScrollView showsVerticalScrollIndicator={false} style={{ opacity: fadeAnim }} contentContainerStyle={styles.scrollContent}>
                    <View style={styles.header}>
                        <TouchableOpacity onPress={handleEditPress} style={styles.avatarContainer} activeOpacity={0.8}>
                            {user?.profile?.avatar_url ? (
                                <Image source={{ uri: api.resolveAttachmentUrl(user.profile.avatar_url) }} style={styles.avatarImage} />
                            ) : (
                                <View style={styles.avatarPlaceholder}><Ionicons name="person" size={40} color={colors.textMuted} /></View>
                            )}
                        </TouchableOpacity>
                        <Text style={styles.headerName}>{user?.first_name ? `${user.first_name} ${user.last_name || ''}`.trim() : user?.email}</Text>
                        {user?.username && <Text style={styles.headerUsername}>@{user.username}</Text>}
                        {user?.profile?.bio ? <Text style={styles.headerBio}>{user.profile.bio}</Text> : null}
                        <View style={styles.headerActionsRow}>
                            <TouchableOpacity style={styles.editPill} onPress={handleEditPress} activeOpacity={0.7}>
                                <Text style={styles.editPillText}>Edit Profile</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={[styles.editPill, styles.progressPill]}
                                onPress={uploadProgressImage}
                                disabled={uploadingProgress}
                                activeOpacity={0.7}
                            >
                                <Ionicons name="camera-outline" size={14} color={colors.textSecondary} />
                                <Text style={[styles.editPillText, { marginLeft: 6 }]}>
                                    {uploadingProgress ? 'Uploading...' : 'Add progress'}
                                </Text>
                            </TouchableOpacity>
                        </View>
                    </View>

                    {/* Progress archive - grid like IG */}
                    <View style={[styles.section, isDesktop && styles.progressSectionDesktop]}>
                        <View style={styles.sectionHeader}>
                            <Text style={styles.sectionTitle}>Progress</Text>
                        </View>
                        {progressPhotos.length === 0 ? (
                            <TouchableOpacity style={styles.archiveEmpty} onPress={uploadProgressImage} activeOpacity={0.8}>
                                <View style={styles.archiveEmptyIcon}>
                                    <Ionicons name="images-outline" size={40} color={colors.textMuted} />
                                </View>
                                <Text style={styles.archiveEmptyTitle}>No photos yet</Text>
                                <Text style={styles.archiveEmptySub}>Add progress photos to your private archive</Text>
                            </TouchableOpacity>
                        ) : (
                            <>
                                <View style={[styles.archiveGrid, isDesktop && styles.archiveGridDesktop]}>
                                    {(progressPhotos.length > 3 ? progressPhotos.slice(0, 3) : progressPhotos).map((item, index) => (
                                        <TouchableOpacity
                                            key={item.id}
                                            style={[styles.archiveGridItem, isDesktop && styles.archiveGridItemDesktop, Platform.OS === 'web' && { width: gridItemWidth, padding: 6 }]}
                                            onPress={() => openProgressArchiveAt(index)}
                                            activeOpacity={0.9}
                                        >
                                            <Image source={{ uri: api.resolveAttachmentUrl(item.image_url) }} style={styles.archiveGridImage} />
                                        </TouchableOpacity>
                                    ))}
                                </View>
                                {progressPhotos.length > 3 && (
                                    <TouchableOpacity
                                        style={styles.viewMoreButton}
                                        onPress={() => navigation.navigate('ProgressArchive')}
                                        activeOpacity={0.7}
                                    >
                                        <Text style={styles.viewMoreText}>View more</Text>
                                        <Ionicons name="chevron-forward" size={18} color={colors.foreground} />
                                    </TouchableOpacity>
                                )}
                            </>
                        )}
                    </View>

                    {/* Settings - minimal list */}
                    <View style={styles.section}>
                        <TouchableOpacity style={styles.menuRow} onPress={() => navigation.navigate('EditPersonal')} activeOpacity={0.7}>
                            <Ionicons name="person-outline" size={22} color={colors.foreground} />
                            <Text style={styles.menuRowText}>Edit personal info</Text>
                            <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                        </TouchableOpacity>
                    </View>

                    <TouchableOpacity style={styles.logoutButton} onPress={logout} activeOpacity={0.7}>
                        <Text style={styles.logoutText}>Sign out</Text>
                    </TouchableOpacity>
                    <View style={{ height: 40 }} />
                </Animated.ScrollView>
            )}

            <Modal animationType="fade" transparent visible={editModalVisible} onRequestClose={() => setEditModalVisible(false)}>
                <View style={styles.modalOverlay}>
                    <View style={styles.modalContent}>
                        <View style={styles.modalHeader}>
                            <Text style={styles.modalTitle}>Edit Profile</Text>
                            <TouchableOpacity onPress={() => setEditModalVisible(false)} style={styles.modalClose} activeOpacity={0.7}>
                                <Ionicons name="close" size={18} color={colors.textSecondary} />
                            </TouchableOpacity>
                        </View>
                        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.editModalScroll}>
                            <TouchableOpacity onPress={pickImage} style={styles.modalAvatarContainer}>
                                {editAvatarUri ? <Image source={{ uri: editAvatarUri }} style={styles.modalAvatar} /> : user?.profile?.avatar_url ? <Image source={{ uri: api.resolveAttachmentUrl(user.profile.avatar_url) }} style={styles.modalAvatar} /> : <View style={styles.modalAvatarPlaceholder}><Ionicons name="camera" size={28} color={colors.textMuted} /></View>}
                                <Text style={styles.changePhotoText}>Change Photo</Text>
                            </TouchableOpacity>
                            <Text style={styles.inputLabel}>FIRST NAME</Text>
                            <TextInput style={styles.input} value={editFirstName} onChangeText={setEditFirstName} placeholder="First name" placeholderTextColor={colors.textMuted} autoCapitalize="words" />
                            <Text style={styles.inputLabel}>LAST NAME</Text>
                            <TextInput style={styles.input} value={editLastName} onChangeText={setEditLastName} placeholder="Last name" placeholderTextColor={colors.textMuted} autoCapitalize="words" />
                            <Text style={styles.inputLabel}>USERNAME</Text>
                            <TextInput style={styles.input} value={editUsername} onChangeText={setEditUsername} placeholder="username" placeholderTextColor={colors.textMuted} autoCapitalize="none" />
                            <Text style={styles.inputLabel}>EMAIL (Cannot be changed)</Text>
                            <TextInput style={[styles.input, styles.inputDisabled]} value={user?.email || ''} editable={false} placeholderTextColor={colors.textMuted} />
                            <Text style={styles.inputLabel}>BIO</Text>
                            <TextInput style={styles.bioInput} value={editBio} onChangeText={setEditBio} multiline numberOfLines={3} placeholder="Tell us about yourself..." placeholderTextColor={colors.textMuted} />
                            <View style={styles.modalButtons}>
                                <TouchableOpacity style={styles.cancelButton} onPress={() => setEditModalVisible(false)}><Text style={styles.cancelButtonText}>Cancel</Text></TouchableOpacity>
                                <TouchableOpacity style={styles.saveButton} onPress={saveProfile} disabled={saveLoading} activeOpacity={0.7}>{saveLoading ? <ActivityIndicator color={colors.buttonText} /> : <Text style={styles.saveButtonText}>Save</Text>}</TouchableOpacity>
                            </View>
                        </ScrollView>
                    </View>
                </View>
            </Modal>
            <Modal
                animationType="fade"
                transparent
                visible={progressModalVisible}
                onRequestClose={() => setProgressModalVisible(false)}
            >
                <Pressable style={styles.modalOverlay} onPress={() => setProgressModalVisible(false)}>
                    <Pressable style={[styles.progressModalContent, { width: imageModalWidth + spacing.lg * 2 }]} onPress={() => {}}>
                        <TouchableOpacity
                            style={styles.progressModalClose}
                            onPress={() => setProgressModalVisible(false)}
                            activeOpacity={0.7}
                        >
                            <Ionicons name="close" size={24} color={colors.foreground} />
                        </TouchableOpacity>
                        {progressPhotos[selectedPhotoIndex] && (
                            <View style={[styles.progressImageBox, { width: imageModalWidth, height: imageModalWidth * (4 / 3) }]}>
                                <Image
                                    source={{ uri: api.resolveAttachmentUrl(progressPhotos[selectedPhotoIndex].image_url) }}
                                    style={{ width: imageModalWidth, height: imageModalWidth * (4 / 3) }}
                                    resizeMode="contain"
                                />
                            </View>
                        )}
                        {progressPhotos[selectedPhotoIndex] && (
                            <Text style={styles.progressModalDate}>
                                {formatProgressDate(progressPhotos[selectedPhotoIndex].created_at)}
                            </Text>
                        )}
                        {progressPhotos.length > 1 && (
                            <View style={[styles.progressModalNav, { width: imageModalWidth }]}>
                                <TouchableOpacity
                                    style={[styles.progressNavButton, selectedPhotoIndex === 0 && styles.progressNavButtonDisabled]}
                                    onPress={() => setSelectedPhotoIndex(prev => Math.max(0, prev - 1))}
                                    disabled={selectedPhotoIndex === 0}
                                    activeOpacity={0.7}
                                >
                                    <Ionicons name="chevron-back" size={20} color={selectedPhotoIndex === 0 ? colors.textMuted : colors.foreground} />
                                    <Text style={[styles.progressNavText, selectedPhotoIndex === 0 && styles.progressNavTextDisabled]}>Prev</Text>
                                </TouchableOpacity>
                                <Text style={styles.progressModalCounter}>
                                    {selectedPhotoIndex + 1} / {progressPhotos.length}
                                </Text>
                                <TouchableOpacity
                                    style={[styles.progressNavButton, selectedPhotoIndex >= progressPhotos.length - 1 && styles.progressNavButtonDisabled]}
                                    onPress={() => setSelectedPhotoIndex(prev => Math.min(progressPhotos.length - 1, prev + 1))}
                                    disabled={selectedPhotoIndex >= progressPhotos.length - 1}
                                    activeOpacity={0.7}
                                >
                                    <Text style={[styles.progressNavText, selectedPhotoIndex >= progressPhotos.length - 1 && styles.progressNavTextDisabled]}>Next</Text>
                                    <Ionicons name="chevron-forward" size={20} color={selectedPhotoIndex >= progressPhotos.length - 1 ? colors.textMuted : colors.foreground} />
                                </TouchableOpacity>
                            </View>
                        )}
                    </Pressable>
                </Pressable>
            </Modal>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    scrollContent: { paddingBottom: spacing.xxl },
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: 56,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.sm,
    },
    backButton: {
        width: 36,
        height: 36,
        borderRadius: 18,
        backgroundColor: colors.card,
        alignItems: 'center',
        justifyContent: 'center',
        ...shadows.sm,
    },
    topBarTitle: { fontSize: 15, fontWeight: '600', color: colors.foreground },
    header: {
        alignItems: 'center',
        paddingTop: spacing.lg,
        paddingBottom: spacing.xl,
    },
    avatarContainer: { position: 'relative' },
    avatarImage: { width: 88, height: 88, borderRadius: 44, ...shadows.md },
    avatarPlaceholder: {
        width: 88,
        height: 88,
        borderRadius: 44,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
        ...shadows.sm,
    },
    avatarSkeleton: { backgroundColor: colors.surfaceLight },
    headerName: { fontSize: 15, fontWeight: '600', color: colors.foreground, marginTop: spacing.md },
    headerUsername: { fontSize: 13, color: colors.textMuted, marginTop: 2 },
    headerBio: { fontSize: 13, color: colors.textSecondary, marginTop: 4, textAlign: 'center', paddingHorizontal: spacing.xxl },
    textSkeletonRow: { width: '60%', alignItems: 'center', gap: spacing.xs, marginTop: spacing.sm, marginBottom: spacing.sm },
    textSkeletonBio: {
        height: 32,
        borderRadius: borderRadius.md,
        backgroundColor: colors.surfaceLight,
        width: '80%',
        marginTop: spacing.sm,
        marginBottom: spacing.lg,
    },
    headerActionsRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        marginTop: spacing.md,
    },
    editPill: { paddingHorizontal: spacing.lg, paddingVertical: 8, borderRadius: borderRadius.full, backgroundColor: colors.card, ...shadows.sm },
    progressPill: { flexDirection: 'row', alignItems: 'center' },
    editPillText: { fontSize: 12, fontWeight: '500', color: colors.textSecondary },
    pillSkeleton: {
        flex: 1,
        height: 32,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surfaceLight,
    },
    section: {
        paddingHorizontal: spacing.lg,
        marginTop: spacing.xl,
    },
    sectionHeader: { marginBottom: spacing.md },
    sectionTitle: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
    },
    archiveEmpty: {
        backgroundColor: colors.card,
        borderRadius: 16,
        paddingVertical: spacing.xxl,
        paddingHorizontal: spacing.lg,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        borderStyle: 'dashed',
    },
    archiveEmptyIcon: {
        width: 72,
        height: 72,
        borderRadius: 36,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: spacing.md,
    },
    archiveEmptyTitle: {
        fontSize: 16,
        fontWeight: '600',
        color: colors.foreground,
        marginBottom: 4,
    },
    archiveEmptySub: {
        fontSize: 13,
        color: colors.textMuted,
    },
    progressSectionDesktop: {
        maxWidth: 900,
        width: '100%',
        alignSelf: 'center',
    },
    archiveGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        marginHorizontal: -2,
    },
    archiveGridDesktop: {
        marginHorizontal: -3,
    },
    archiveGridItem: {
        width: '33.33%',
        padding: 2,
        aspectRatio: 1,
    },
    archiveGridItemDesktop: {
        width: '33.33%',
        padding: 8,
    },
    archiveGridImage: {
        width: '100%',
        height: '100%',
        borderRadius: 4,
        backgroundColor: colors.surface,
    },
    viewMoreButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        marginTop: spacing.md,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.lg,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
    },
    viewMoreText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
    },
    archiveSkeletonRow: {
        flexDirection: 'row',
        gap: 4,
    },
    archiveSkeletonItem: {
        flex: 1,
        aspectRatio: 1,
        borderRadius: 4,
        backgroundColor: colors.surfaceLight,
    },
    skeletonLine: {
        height: 14,
        borderRadius: 7,
        backgroundColor: colors.surfaceLight,
        width: '100%',
    },
    menuRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.lg,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: colors.border,
        gap: spacing.md,
    },
    menuRowText: {
        flex: 1,
        fontSize: 16,
        fontWeight: '500',
        color: colors.foreground,
    },
    logoutButton: {
        alignItems: 'center',
        marginTop: spacing.xl,
        paddingVertical: spacing.md,
    },
    logoutText: {
        fontSize: 15,
        fontWeight: '500',
        color: colors.textMuted,
    },
    modalOverlay: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center', padding: spacing.lg },
    modalContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        maxWidth: 440,
        width: '100%',
        maxHeight: '90%',
        ...shadows.xl,
    },
    editModalScroll: { paddingBottom: spacing.xl },
    modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.xl },
    modalTitle: { ...typography.h3 },
    modalClose: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
    modalAvatarContainer: { alignSelf: 'center', alignItems: 'center', marginBottom: spacing.xl },
    modalAvatar: { width: 80, height: 80, borderRadius: 40 },
    modalAvatarPlaceholder: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center' },
    changePhotoText: { fontSize: 13, color: colors.info, fontWeight: '500', marginTop: spacing.sm },
    inputLabel: { ...typography.label, marginBottom: spacing.sm, marginLeft: 2, marginTop: spacing.md },
    input: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        padding: spacing.lg,
        color: colors.textPrimary,
        fontSize: 16,
        marginBottom: spacing.sm,
    },
    inputDisabled: {
        opacity: 0.6,
        backgroundColor: colors.card,
    },
    bioInput: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        padding: spacing.lg,
        color: colors.textPrimary,
        fontSize: 16,
        textAlignVertical: 'top',
        minHeight: 100,
    },
    progressModalContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        maxHeight: '90%',
        ...shadows.lg,
        alignItems: 'center',
    },
    progressModalClose: {
        position: 'absolute',
        top: spacing.md,
        right: spacing.md,
        zIndex: 10,
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: colors.card,
        alignItems: 'center',
        justifyContent: 'center',
        ...shadows.md,
    },
    progressImageBox: {
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border || colors.surfaceLight,
        backgroundColor: colors.surface,
        overflow: 'hidden',
        alignItems: 'center',
        justifyContent: 'center',
    },
    progressModalDate: {
        marginTop: spacing.md,
        fontSize: 18,
        fontWeight: '600',
        color: colors.foreground,
    },
    progressModalNav: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginTop: spacing.md,
        width: '100%',
        maxWidth: 280,
    },
    progressNavButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
    },
    progressNavButtonDisabled: {
        opacity: 0.5,
    },
    progressNavText: {
        fontSize: 14,
        fontWeight: '500',
        color: colors.foreground,
    },
    progressNavTextDisabled: {
        color: colors.textMuted,
    },
    progressModalCounter: {
        fontSize: 13,
        color: colors.textMuted,
    },
    modalButtons: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: spacing.xl, gap: spacing.md },
    cancelButton: { padding: spacing.md },
    cancelButtonText: { fontSize: 14, fontWeight: '500', color: colors.textMuted },
    saveButton: { backgroundColor: colors.foreground, borderRadius: borderRadius.full, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, ...shadows.sm },
    saveButtonText: { ...typography.button },
});
