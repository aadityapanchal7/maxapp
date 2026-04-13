import React, { useEffect, useState, useRef, useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, TextInput, Alert, ActivityIndicator, Animated, Pressable, Platform, useWindowDimensions, Keyboard } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { CachedImage } from '../../components/CachedImage';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { formatFaceRatingLabel } from '../../utils/faceRatingLabel';
import { useMaxxesQuery } from '../../hooks/useAppQueries';
import { getMaxxDisplayLabel } from '../../utils/maxxDisplay';
import { normalizeMaxxTintHex } from '../../components/MaxxProgramRow';
import { userHasSignupPhone } from '../../utils/userPhone';

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
    const insets = useSafeAreaInsets();
    const { width: winWidth } = useWindowDimensions();
    const imageModalWidth = getImageModalWidth(winWidth);
    const { user, refreshUser, isPaid, isPremium } = useAuth();
    const maxxesQuery = useMaxxesQuery();
    const activeMaxxes = useMemo(() => {
        const allMaxxes = maxxesQuery.data?.maxes ?? [];
        const userGoalIds = new Set(((user?.onboarding?.goals || []) as string[]).map((g: string) => g.toLowerCase()));
        if (userGoalIds.size === 0) return [];
        return allMaxxes.filter((m: any) => m.id && userGoalIds.has(m.id.toLowerCase()));
    }, [maxxesQuery.data, user?.onboarding?.goals]);
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
            const msg = 'Could not upload progress photo. Please try again.';
            Platform.OS === 'web' ? window.alert(msg) : Alert.alert('Error', msg);
        } finally {
            setUploadingProgress(false);
        }
    };

    const openProgressArchiveAt = (index: number) => {
        setSelectedPhotoIndex(index);
        setProgressModalVisible(true);
    };

    const deleteProgressPhoto = async (index: number) => {
        const photo = progressPhotos[index];
        if (!photo) return;

        const doDelete = async () => {
            try {
                await api.deleteProgressPhoto(photo.id);
                const updated = progressPhotos.filter((_, i) => i !== index);
                setProgressPhotos(updated);
                if (updated.length === 0) {
                    setProgressModalVisible(false);
                } else {
                    setSelectedPhotoIndex(Math.min(index, updated.length - 1));
                }
            } catch (e) {
                console.error(e);
                if (Platform.OS === 'web') {
                    window.alert('Could not delete photo. Please try again.');
                } else {
                    Alert.alert('Error', 'Could not delete photo. Please try again.');
                }
            }
        };

        if (Platform.OS === 'web') {
            if (window.confirm('Are you sure you want to delete this progress photo?')) {
                await doDelete();
            }
        } else {
            Alert.alert('Delete photo', 'Are you sure you want to delete this progress photo?', [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete', style: 'destructive', onPress: doDelete },
            ]);
        }
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
                }
            }

            try {
                await api.updateProfile({ bio: editBio, avatar_url: newAvatarUrl });
                console.log('Profile updated successfully');
            } catch (profileError: any) {
                console.error('Profile update error:', profileError);
                throw profileError;
            }

            const accountUpdates: any = {};
            const currentFirstName = user?.first_name || '';
            const currentLastName = user?.last_name || '';
            const currentUsername = user?.username || '';

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
                        const msg = 'Username must be at least 3 characters';
                        Platform.OS === 'web' ? window.alert(msg) : Alert.alert('Error', msg);
                        setSaveLoading(false);
                        return;
                    }
                    if (!/^[a-zA-Z0-9_]+$/.test(trimmedUsername)) {
                        const msg = 'Username can only contain letters, numbers, and underscores';
                        Platform.OS === 'web' ? window.alert(msg) : Alert.alert('Error', msg);
                        setSaveLoading(false);
                        return;
                    }
                }
                accountUpdates.username = trimmedUsername || null;
            }

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

            await refreshUser();
            setEditModalVisible(false);
        } catch (e: any) {
            console.error('Save profile error:', e);
            const errorMsg = e?.response?.data?.detail || e?.message || 'Failed to update profile';
            if (Platform.OS === 'web') {
                window.alert(errorMsg);
            } else {
                Alert.alert('Error', errorMsg);
            }
        }
        finally { setSaveLoading(false); }
    };

    const onFaceScansPress = () => {
        if (isPremium) {
            navigation.navigate('FaceScanArchive');
        } else {
            Alert.alert(
                'Face scans',
                'Face scans are not available on Basic. Upgrade to Premium for daily scans.',
                [
                    { text: 'OK', style: 'cancel' },
                    { text: 'Upgrade', onPress: () => navigation.navigate('ManageSubscription') },
                ],
            );
        }
    };

    const renderSkeleton = () => (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
            <View style={styles.topBarSkeletonPad} />
            <View style={styles.identitySkeletonSection}>
                <View style={styles.avatarRingSkeleton}>
                    <View style={[styles.avatarPlaceholder, styles.avatarSkeleton]} />
                </View>
                <View style={styles.skeletonHint} />
                <View style={styles.textSkeletonRow}>
                    <View style={styles.skeletonLine} />
                    <View style={[styles.skeletonLine, { width: '50%' }]} />
                </View>
                <View style={styles.textSkeletonBio} />
                <View style={styles.actionsColSkeleton}>
                    <View style={styles.pillSkeleton} />
                    <View style={styles.pillSkeleton} />
                </View>
            </View>
            <View style={styles.gridDivider} />
            <View style={styles.progressSkeletonSection}>
                <View style={styles.sectionEyebrowSkeleton} />
                <View style={styles.sectionTitleSkeleton} />
                <View style={styles.archiveSkeletonRow}>
                    <View style={styles.archiveSkeletonItem} />
                    <View style={styles.archiveSkeletonItem} />
                    <View style={styles.archiveSkeletonItem} />
                </View>
            </View>
            {isPaid ? (
                <>
                    <View style={styles.gridDivider} />
                    <View style={styles.toolsSkeletonSection}>
                        <View style={styles.listRowSkeleton} />
                    </View>
                </>
            ) : null}
        </ScrollView>
    );

    return (
        <View style={styles.container}>
            <View style={[styles.topBar, { paddingTop: Math.max(insets.top, 12) }]}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={styles.iconButton}
                    activeOpacity={0.7}
                    accessibilityRole="button"
                    accessibilityLabel="Go back"
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.topBarTitle} numberOfLines={1}>
                    {user?.username ? user.username : 'Profile'}
                </Text>
                <TouchableOpacity
                    onPress={() => navigation.navigate('Settings')}
                    style={styles.iconButton}
                    activeOpacity={0.7}
                    accessibilityLabel="Settings"
                    accessibilityRole="button"
                >
                    <Ionicons name="settings-outline" size={20} color={colors.foreground} />
                </TouchableOpacity>
            </View>

            {loading ? (
                renderSkeleton()
            ) : (
                <Animated.ScrollView showsVerticalScrollIndicator={false} style={{ opacity: fadeAnim }} contentContainerStyle={styles.scrollContent}>
                    {isPaid && !userHasSignupPhone(user) ? (
                        <TouchableOpacity
                            style={styles.smsAlertBanner}
                            onPress={() => navigation.navigate('SmsSetup')}
                            activeOpacity={0.85}
                        >
                            <View style={styles.smsAlertIconWrap}>
                                <Ionicons name="alert-circle" size={18} color={colors.warning} />
                            </View>
                            <View style={styles.smsAlertTextCol}>
                                <Text style={styles.smsAlertTitle}>Phone number missing</Text>
                                <Text style={styles.smsAlertSub}>Add one to enable SMS coaching</Text>
                            </View>
                            <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                        </TouchableOpacity>
                    ) : null}

                    <View style={styles.identitySection}>
                        <TouchableOpacity
                            onPress={handleEditPress}
                            activeOpacity={0.85}
                            accessibilityRole="button"
                            accessibilityLabel="Edit profile photo"
                        >
                            <View style={styles.avatarRing}>
                                {user?.profile?.avatar_url ? (
                                    <CachedImage uri={api.resolveAttachmentUrl(user.profile.avatar_url)} style={styles.avatarImage} />
                                ) : (
                                    <View style={styles.avatarPlaceholder}>
                                        <Ionicons name="person" size={36} color={colors.textMuted} />
                                    </View>
                                )}
                            </View>
                        </TouchableOpacity>

                        <Text style={styles.headerName}>
                            {user?.first_name ? `${user.first_name} ${user.last_name || ''}`.trim() : user?.email}
                        </Text>

                        {user?.username ? (
                            <Text style={styles.headerHandle}>@{user.username}</Text>
                        ) : null}

                        {user?.profile?.bio ? (
                            <Text style={styles.headerBio}>{user.profile.bio}</Text>
                        ) : null}

                        {activeMaxxes.length > 0 ? (
                            <View style={styles.maxxTagsRow}>
                                {activeMaxxes.map((m: any) => {
                                    const tint = normalizeMaxxTintHex(m.color);
                                    return (
                                        <TouchableOpacity
                                            key={m.id}
                                            style={styles.maxxTag}
                                            onPress={() => navigation.navigate('MaxxDetail', { maxxId: m.id })}
                                            activeOpacity={0.72}
                                        >
                                            <View style={[styles.maxxDot, { backgroundColor: tint }]} />
                                            <Text style={styles.maxxTagText}>{getMaxxDisplayLabel(m)}</Text>
                                        </TouchableOpacity>
                                    );
                                })}
                            </View>
                        ) : null}

                        <View style={styles.actionsRow}>
                            <TouchableOpacity
                                style={styles.actionBtn}
                                onPress={handleEditPress}
                                activeOpacity={0.75}
                                accessibilityRole="button"
                                accessibilityLabel="Edit profile"
                            >
                                <Ionicons name="create-outline" size={15} color={colors.foreground} />
                                <Text style={styles.actionBtnText}>Edit</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={[styles.actionBtn, styles.actionBtnFilled, uploadingProgress && styles.actionBtnDisabled]}
                                onPress={uploadProgressImage}
                                disabled={uploadingProgress}
                                activeOpacity={0.75}
                                accessibilityRole="button"
                                accessibilityLabel={uploadingProgress ? 'Uploading progress photo' : 'Add progress photo'}
                                accessibilityState={{ disabled: uploadingProgress }}
                            >
                                <Ionicons name="add" size={16} color={colors.card} />
                                <Text style={styles.actionBtnFilledText}>
                                    {uploadingProgress ? 'Uploading…' : 'Progress'}
                                </Text>
                            </TouchableOpacity>
                        </View>
                    </View>

                    <View style={styles.gridDivider} />

                    {progressPhotos.length === 0 ? (
                        <TouchableOpacity
                            style={styles.archiveEmpty}
                            onPress={uploadProgressImage}
                            activeOpacity={0.85}
                            accessibilityRole="button"
                            accessibilityLabel="Add your first progress photo"
                        >
                            <Ionicons name="images-outline" size={24} color={colors.textMuted} style={{ marginBottom: spacing.sm }} />
                            <Text style={styles.archiveEmptyTitle}>No progress photos yet</Text>
                            <Text style={styles.archiveEmptySub}>Tap to add your first shot</Text>
                        </TouchableOpacity>
                    ) : (
                        <View style={styles.photoGrid}>
                            {progressPhotos.map((item, index) => (
                                <TouchableOpacity
                                    key={item.id}
                                    style={styles.photoGridItem}
                                    onPress={() => openProgressArchiveAt(index)}
                                    activeOpacity={0.9}
                                    accessibilityRole="button"
                                    accessibilityLabel={`Progress photo ${index + 1}`}
                                >
                                    <CachedImage uri={api.resolveAttachmentUrl(item.image_url)} style={styles.photoGridImage} />
                                    {item.face_rating != null && Number.isFinite(Number(item.face_rating)) ? (
                                        <Text style={styles.progressRatingBadge}>
                                            {formatFaceRatingLabel(Number(item.face_rating))}
                                        </Text>
                                    ) : null}
                                </TouchableOpacity>
                            ))}
                        </View>
                    )}

                    <View style={{ height: spacing.xxxl }} />
                </Animated.ScrollView>
            )}

            <Modal animationType="fade" transparent visible={editModalVisible} onRequestClose={() => setEditModalVisible(false)}>
                <Pressable
                    style={styles.modalOverlay}
                    onPress={() => {
                        Keyboard.dismiss();
                        setEditModalVisible(false);
                    }}
                    accessibilityLabel="Close edit profile"
                    accessibilityRole="button"
                >
                    <Pressable style={styles.modalContent} onPress={(e) => e.stopPropagation()}>
                        <View style={styles.modalHeader}>
                            <Text style={styles.modalTitle}>Edit Profile</Text>
                            <TouchableOpacity onPress={() => setEditModalVisible(false)} style={styles.modalClose} activeOpacity={0.7}>
                                <Ionicons name="close" size={18} color={colors.textSecondary} />
                            </TouchableOpacity>
                        </View>
                        <ScrollView
                            showsVerticalScrollIndicator={false}
                            contentContainerStyle={styles.editModalScroll}
                            keyboardShouldPersistTaps="handled"
                            keyboardDismissMode="on-drag"
                        >
                            <TouchableOpacity onPress={pickImage} style={styles.modalAvatarContainer}>
                                {editAvatarUri ? <CachedImage uri={editAvatarUri} style={styles.modalAvatar} /> : user?.profile?.avatar_url ? <CachedImage uri={api.resolveAttachmentUrl(user.profile.avatar_url)} style={styles.modalAvatar} /> : <View style={styles.modalAvatarPlaceholder}><Ionicons name="camera" size={28} color={colors.textMuted} /></View>}
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
                    </Pressable>
                </Pressable>
            </Modal>
            <Modal
                animationType="fade"
                transparent
                visible={progressModalVisible}
                onRequestClose={() => setProgressModalVisible(false)}
            >
                <Pressable style={styles.modalOverlay} onPress={() => setProgressModalVisible(false)}>
                    <Pressable style={[styles.progressModalContent, { width: imageModalWidth + spacing.lg * 2 }]} onPress={(e) => e.stopPropagation()}>
                        <TouchableOpacity
                            style={styles.progressModalClose}
                            onPress={() => setProgressModalVisible(false)}
                            activeOpacity={0.7}
                        >
                            <Ionicons name="close" size={24} color={colors.foreground} />
                        </TouchableOpacity>
                        {progressPhotos[selectedPhotoIndex] && (
                            <View style={[styles.progressImageBox, { width: imageModalWidth, height: imageModalWidth * (4 / 3) }]}>
                                <CachedImage
                                    uri={api.resolveAttachmentUrl(progressPhotos[selectedPhotoIndex].image_url)}
                                    style={{ width: imageModalWidth, height: imageModalWidth * (4 / 3) }}
                                    contentFit="contain"
                                />
                                {progressPhotos[selectedPhotoIndex].face_rating != null &&
                                Number.isFinite(Number(progressPhotos[selectedPhotoIndex].face_rating)) ? (
                                    <Text style={styles.progressModalRatingBadge}>
                                        {formatFaceRatingLabel(Number(progressPhotos[selectedPhotoIndex].face_rating))}
                                    </Text>
                                ) : null}
                            </View>
                        )}
                        {progressPhotos[selectedPhotoIndex] && (
                            <Text style={styles.progressModalDate}>
                                {formatProgressDate(progressPhotos[selectedPhotoIndex].created_at)}
                            </Text>
                        )}
                        <TouchableOpacity
                            style={styles.progressDeleteBtn}
                            onPress={() => deleteProgressPhoto(selectedPhotoIndex)}
                            activeOpacity={0.7}
                        >
                            <Ionicons name="trash-outline" size={18} color={colors.error} />
                            <Text style={styles.progressDeleteText}>Delete</Text>
                        </TouchableOpacity>
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
    scrollContent: { paddingBottom: spacing.xxxl },

    // ── Top bar ──────────────────────────────────────────────────────────
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        backgroundColor: 'transparent',
    },
    topBarTitle: {
        flex: 1,
        fontFamily: fonts.serif,
        fontSize: 17,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.2,
        textAlign: 'center',
    },
    iconButton: {
        width: 40,
        height: 40,
        alignItems: 'center',
        justifyContent: 'center',
    },

    // ── Identity section ────────────────────────────────────────────────
    identitySection: {
        alignItems: 'center',
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.lg,
        paddingBottom: spacing.lg,
    },
    avatarRing: {
        padding: 3,
        borderRadius: borderRadius.full,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    avatarImage: { width: 88, height: 88, borderRadius: 44 },
    avatarPlaceholder: {
        width: 88,
        height: 88,
        borderRadius: 44,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
    },
    headerName: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.3,
        marginTop: spacing.md,
        textAlign: 'center',
    },
    headerHandle: {
        fontSize: 13,
        fontWeight: '400',
        color: colors.textMuted,
        marginTop: 3,
        textAlign: 'center',
    },
    headerBio: {
        fontSize: 13,
        fontWeight: '400',
        color: colors.textSecondary,
        lineHeight: 18,
        marginTop: spacing.sm,
        textAlign: 'center',
        paddingHorizontal: spacing.xl,
    },

    // ── Maxx tags (colored dot + label) ─────────────────────────────────
    maxxTagsRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap: 8,
        marginTop: spacing.md,
    },
    maxxTag: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        paddingVertical: 6,
        paddingHorizontal: 14,
    },
    maxxDot: {
        width: 7,
        height: 7,
        borderRadius: 4,
    },
    maxxTagText: {
        fontSize: 12,
        fontWeight: '500',
        color: colors.foreground,
    },

    // ── Actions ──────────────────────────────────────────────────────────
    actionsRow: {
        flexDirection: 'row',
        justifyContent: 'center',
        gap: 10,
        marginTop: spacing.lg,
    },
    actionBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 5,
        borderRadius: borderRadius.full,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        paddingVertical: 9,
        paddingHorizontal: 22,
    },
    actionBtnText: {
        fontSize: 13,
        fontWeight: '500',
        color: colors.foreground,
    },
    actionBtnFilled: {
        backgroundColor: colors.foreground,
        borderColor: colors.foreground,
    },
    actionBtnFilledText: {
        fontSize: 13,
        fontWeight: '500',
        color: colors.card,
    },
    actionBtnDisabled: {
        opacity: 0.45,
    },

    smsAlertBanner: {
        marginHorizontal: spacing.lg,
        marginTop: spacing.sm,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.warning + '44',
        backgroundColor: colors.warning + '0D',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    smsAlertIconWrap: {
        width: 28,
        height: 28,
        borderRadius: 14,
        backgroundColor: colors.warning + '1A',
        alignItems: 'center',
        justifyContent: 'center',
    },
    smsAlertTextCol: {
        flex: 1,
        minWidth: 0,
    },
    smsAlertTitle: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: -0.1,
    },
    smsAlertSub: {
        fontSize: 11,
        fontWeight: '400',
        color: colors.textSecondary,
        marginTop: 1,
    },

    // ── Grid divider ─────────────────────────────────────────────────────
    gridDivider: {
        height: StyleSheet.hairlineWidth,
        backgroundColor: colors.divider,
    },

    // ── Photo grid ───────────────────────────────────────────────────────
    photoGrid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
    },
    photoGridItem: {
        width: '33.33%',
        aspectRatio: 1,
        padding: 0.5,
        position: 'relative' as const,
    },
    photoGridImage: {
        width: '100%',
        height: '100%',
        backgroundColor: colors.surface,
    },
    progressRatingBadge: {
        position: 'absolute',
        bottom: 4,
        right: 4,
        fontSize: 10,
        fontWeight: '600',
        color: '#FFF',
        backgroundColor: 'rgba(10, 10, 10, 0.5)',
        paddingHorizontal: 5,
        paddingVertical: 2,
        borderRadius: 4,
        overflow: 'hidden',
    },
    archiveEmpty: {
        paddingVertical: spacing.xxxl,
        paddingHorizontal: spacing.xl,
        alignItems: 'center',
    },
    archiveEmptyTitle: {
        fontFamily: fonts.serif,
        fontSize: 18,
        fontWeight: '400',
        color: colors.textPrimary,
        marginBottom: 6,
    },
    archiveEmptySub: {
        fontSize: 13,
        color: colors.textMuted,
        textAlign: 'center',
        lineHeight: 18,
    },

    // ── Skeleton ─────────────────────────────────────────────────────────
    topBarSkeletonPad: {
        height: 56,
        marginHorizontal: spacing.lg,
        marginTop: spacing.sm,
    },
    identitySkeletonSection: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
        paddingBottom: spacing.md,
    },
    avatarRingSkeleton: {
        padding: 2,
        borderRadius: borderRadius.full,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
    },
    avatarSkeleton: { backgroundColor: colors.surfaceLight },
    skeletonHint: {
        width: 72,
        height: 11,
        borderRadius: 6,
        backgroundColor: colors.surfaceLight,
        marginTop: spacing.sm,
        marginBottom: spacing.xs,
    },
    textSkeletonRow: { width: '70%', alignItems: 'center', gap: spacing.sm, marginTop: spacing.md },
    textSkeletonBio: {
        height: 36,
        borderRadius: borderRadius.md,
        backgroundColor: colors.surfaceLight,
        width: '85%',
        marginTop: spacing.md,
    },
    actionsColSkeleton: {
        flexDirection: 'row',
        justifyContent: 'center',
        width: '100%',
        marginTop: spacing.lg,
        gap: spacing.sm,
    },
    pillSkeleton: {
        height: 36,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surfaceLight,
        width: 120,
    },
    skeletonLine: {
        height: 14,
        borderRadius: 7,
        backgroundColor: colors.surfaceLight,
        width: '100%',
    },
    progressSkeletonSection: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.xl,
        paddingBottom: spacing.lg,
    },
    sectionEyebrowSkeleton: {
        width: 100,
        height: 11,
        borderRadius: 6,
        backgroundColor: colors.surfaceLight,
        marginBottom: spacing.sm,
    },
    sectionTitleSkeleton: {
        width: 120,
        height: 22,
        borderRadius: 8,
        backgroundColor: colors.surfaceLight,
        marginBottom: spacing.md,
    },
    archiveSkeletonRow: {
        flexDirection: 'row',
        gap: spacing.sm,
    },
    archiveSkeletonItem: {
        flex: 1,
        aspectRatio: 1,
        borderRadius: borderRadius.sm,
        backgroundColor: colors.surfaceLight,
    },
    toolsSkeletonSection: {
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
    },
    listRowSkeleton: {
        height: 56,
        borderRadius: borderRadius.sm,
        backgroundColor: colors.surfaceLight,
    },

    // ── Edit modal ───────────────────────────────────────────────────────
    modalOverlay: {
        flex: 1,
        backgroundColor: colors.overlay,
        justifyContent: 'center',
        alignItems: 'center',
        padding: spacing.lg,
    },
    modalContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        paddingTop: spacing.lg,
        maxWidth: 440,
        width: '100%',
        maxHeight: '90%',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
    },
    editModalScroll: { paddingBottom: spacing.xl },
    modalHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.xl,
    },
    modalTitle: {
        fontFamily: 'PlayfairDisplay',
        fontSize: 20,
        fontWeight: '400',
        color: colors.textPrimary,
        letterSpacing: -0.2,
    },
    modalClose: {
        width: 32,
        height: 32,
        borderRadius: 16,
        alignItems: 'center',
        justifyContent: 'center',
    },
    modalAvatarContainer: { alignSelf: 'center', alignItems: 'center', marginBottom: spacing.xl },
    modalAvatar: { width: 80, height: 80, borderRadius: 40 },
    modalAvatarPlaceholder: {
        width: 80,
        height: 80,
        borderRadius: 40,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
    },
    changePhotoText: {
        fontSize: 12,
        color: colors.textSecondary,
        fontWeight: '500',
        marginTop: spacing.sm,
        letterSpacing: 0.2,
    },
    inputLabel: {
        ...typography.label,
        marginBottom: spacing.sm,
        marginLeft: 2,
        marginTop: spacing.md,
    },
    input: {
        backgroundColor: colors.background,
        borderRadius: borderRadius.md,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        color: colors.textPrimary,
        fontSize: 16,
        marginBottom: spacing.sm,
    },
    inputDisabled: {
        opacity: 0.6,
        backgroundColor: colors.card,
    },
    bioInput: {
        backgroundColor: colors.background,
        borderRadius: borderRadius.md,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        color: colors.textPrimary,
        fontSize: 16,
        textAlignVertical: 'top',
        minHeight: 100,
    },
    modalButtons: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        marginTop: spacing.xxl,
        gap: spacing.md,
    },
    cancelButton: { padding: spacing.md },
    cancelButtonText: { fontSize: 14, fontWeight: '500', color: colors.textMuted },
    saveButton: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingHorizontal: spacing.xl,
        paddingVertical: 10,
    },
    saveButtonText: { ...typography.button },

    // ── Progress modal ───────────────────────────────────────────────────
    progressModalContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        maxHeight: '90%',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
        alignItems: 'center',
    },
    progressModalClose: {
        position: 'absolute',
        top: spacing.md,
        right: spacing.md,
        zIndex: 10,
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
    },
    progressImageBox: {
        position: 'relative',
        borderRadius: borderRadius.md,
        backgroundColor: colors.surface,
        overflow: 'hidden',
        alignItems: 'center',
        justifyContent: 'center',
    },
    progressModalRatingBadge: {
        position: 'absolute',
        bottom: 10,
        right: 10,
        fontSize: 12,
        fontWeight: '600',
        color: colors.card,
        backgroundColor: 'rgba(10, 10, 10, 0.5)',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: borderRadius.sm,
        overflow: 'hidden',
    },
    progressModalDate: {
        marginTop: spacing.lg,
        fontFamily: 'PlayfairDisplay',
        fontSize: 18,
        fontWeight: '400',
        color: colors.foreground,
    },
    progressDeleteBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        marginTop: spacing.md,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
    },
    progressDeleteText: {
        fontSize: 14,
        fontWeight: '500',
        color: colors.error,
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
});
