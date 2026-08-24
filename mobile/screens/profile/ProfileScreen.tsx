import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, TextInput, ActivityIndicator, Animated, Pressable, Platform, useWindowDimensions, Keyboard } from 'react-native'
import { LinearGradient } from 'expo-linear-gradient';
import { Alert, InAppAlertHost } from '../../components/InAppAlert';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { CachedImage } from '../../components/CachedImage';
import SectionLabel from '../../components/SectionLabel';
import AchievementBadge from '../../components/achievements/AchievementBadge';
import { StreakMilestoneCallout } from '../../components/StreakMilestoneCallout';
import XpProgressCard from '../../components/XpProgressCard';
import GlassBar from '../../components/glass/GlassBar';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { formatFaceRatingLabel } from '../../utils/faceRatingLabel';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { useMaxxesQuery, useActiveSchedulesFullQuery } from '../../hooks/useAppQueries';
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

// Pull a clean ascending time-series of face scores out of the (untyped) scan
// history payload, defending against the several shapes the score can take.
function parseScanPoints(raw: any): { score: number; at?: string }[] {
    const list = raw?.scans ?? raw?.history ?? (Array.isArray(raw) ? raw : []) ?? [];
    const pts = (list as any[])
        .map((s) => {
            const score = Number(
                s?.overall_score ?? s?.rating ?? s?.score ?? s?.analysis?.psl_rating?.appeal ?? s?.psl_rating?.appeal,
            );
            return Number.isFinite(score) ? { score, at: s?.created_at as string | undefined } : null;
        })
        .filter(Boolean) as { score: number; at?: string }[];
    pts.sort((a, b) => new Date(a.at || 0).getTime() - new Date(b.at || 0).getTime());
    return pts;
}

// ── Onboarding light black/white palette (Cal AI × Stoic) ──────────────────────
const BG = '#F1F1EF';
const CARD = '#FFFFFF';
const INK = '#111113';
const ON_INK = '#FFFFFF';
const SUB = '#6B6B6B';
const MUTE = '#9A9A9A';
const TRACK = '#E4E3E0';
const SOFT = { shadowColor: '#000', shadowOpacity: 0.04, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 1 } as const;

const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function ProgressCalendar({
    progressPhotos,
    scanPts,
    onPhotoPress,
    onScanDay,
}: {
    progressPhotos: any[];
    scanPts: { score: number; at?: string }[];
    onPhotoPress: (photo: any) => void;
    onScanDay: () => void;
}) {
    const today = useMemo(() => new Date(), []);
    const [viewYear, setViewYear] = useState(today.getFullYear());
    const [viewMonth, setViewMonth] = useState(today.getMonth());

    const goBack = useCallback(() => {
        if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
        else setViewMonth(m => m - 1);
    }, [viewMonth]);

    const goForward = useCallback(() => {
        if (viewYear > today.getFullYear() || (viewYear === today.getFullYear() && viewMonth >= today.getMonth())) return;
        if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
        else setViewMonth(m => m + 1);
    }, [viewMonth, viewYear, today]);

    const isFuture = viewYear > today.getFullYear() || (viewYear === today.getFullYear() && viewMonth >= today.getMonth());

    const photoByDate = useMemo(() => {
        const map: Record<string, any> = {};
        progressPhotos.forEach(ph => {
            if (ph.created_at) {
                const d = ph.created_at.split('T')[0];
                if (!map[d]) map[d] = ph;
            }
        });
        return map;
    }, [progressPhotos]);

    const scanDateSet = useMemo(() => {
        const s = new Set<string>();
        scanPts.forEach(pt => { if (pt.at) s.add(pt.at.split('T')[0]); });
        return s;
    }, [scanPts]);

    const firstWeekday = new Date(viewYear, viewMonth, 1).getDay();
    const startOffset = (firstWeekday + 6) % 7;
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

    const cells: number[] = [];
    for (let i = 0; i < startOffset; i++) cells.push(0);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);
    while (cells.length % 7 !== 0) cells.push(0);

    return (
        <View>
            <View style={cal.header}>
                <TouchableOpacity onPress={goBack} hitSlop={8} style={cal.navBtn}>
                    <Ionicons name="chevron-back" size={18} color={INK} />
                </TouchableOpacity>
                <Text style={cal.monthLabel}>{MONTH_NAMES[viewMonth]} {viewYear}</Text>
                <TouchableOpacity onPress={goForward} hitSlop={8} style={cal.navBtn} disabled={isFuture}>
                    <Ionicons name="chevron-forward" size={18} color={isFuture ? TRACK : INK} />
                </TouchableOpacity>
            </View>
            <View style={cal.dayRow}>
                {['M','T','W','T','F','S','S'].map((d, i) => (
                    <Text key={i} style={cal.dayHead}>{d}</Text>
                ))}
            </View>
            <View style={cal.grid}>
                {cells.map((day, i) => {
                    if (!day) return <View key={`e${i}`} style={cal.cell} />;
                    const dateStr = `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                    const photo = photoByDate[dateStr];
                    const hasScan = scanDateSet.has(dateStr);
                    const isToday = dateStr === todayStr;
                    const hasContent = !!photo || hasScan;

                    return (
                        <TouchableOpacity
                            key={dateStr}
                            style={cal.cell}
                            onPress={() => {
                                if (photo) onPhotoPress(photo);
                                else if (isToday) onScanDay();
                            }}
                            activeOpacity={hasContent || isToday ? 0.7 : 1}
                        >
                            {photo ? (
                                <View style={[cal.thumb, isToday && cal.thumbToday]}>
                                    <CachedImage
                                        uri={api.resolveAttachmentUrl(photo.image_url)}
                                        style={{ width: '100%', height: '100%' }}
                                        contentFit="cover"
                                    />
                                </View>
                            ) : (
                                <View style={[cal.dayNum, isToday && cal.dayNumToday]}>
                                    <Text style={[cal.dayText, isToday && cal.dayTextToday]}>{day}</Text>
                                    {hasScan && !photo ? <View style={cal.scanDot} /> : null}
                                </View>
                            )}
                        </TouchableOpacity>
                    );
                })}
            </View>
        </View>
    );
}

const cal = StyleSheet.create({
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
    navBtn: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
    monthLabel: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: INK, letterSpacing: -0.2 },
    dayRow: { flexDirection: 'row', marginBottom: 4 },
    dayHead: { flex: 1, textAlign: 'center', fontFamily: 'Matter-Medium', fontSize: 10.5, color: MUTE, letterSpacing: 0.2 },
    grid: { flexDirection: 'row', flexWrap: 'wrap' },
    cell: { width: `${100 / 7}%` as any, aspectRatio: 1, padding: 1.5, alignItems: 'center', justifyContent: 'center' },
    thumb: { width: '92%', height: '92%', borderRadius: 5, overflow: 'hidden' },
    thumbToday: { borderWidth: 1.5, borderColor: INK },
    dayNum: { width: '80%', height: '80%', borderRadius: 5, alignItems: 'center', justifyContent: 'center' },
    dayNumToday: { backgroundColor: INK },
    dayText: { fontFamily: 'Matter-Regular', fontSize: 11.5, color: INK },
    dayTextToday: { color: ON_INK, fontFamily: 'Matter-SemiBold' },
    scanDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: '#2E7D52', marginTop: 1 },
});

const p = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    topBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingBottom: 2 },
    iconBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' },
    loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    scroll: { paddingHorizontal: 20, paddingBottom: 36 },

    identity: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4, marginBottom: 18 },
    idLeft: { flex: 1, paddingRight: 16 },
    name: { fontFamily: fonts.serif, fontSize: 27, color: INK, letterSpacing: -0.5, lineHeight: 31, textTransform: 'lowercase' },
    editPill: { alignSelf: 'flex-start', marginTop: 12, backgroundColor: INK, borderRadius: 999, paddingHorizontal: 15, paddingVertical: 7 },
    editPillText: { fontFamily: 'Matter-Medium', fontSize: 12.5, color: ON_INK, letterSpacing: 0.1 },
    avatar: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#E4E3E0' },
    avatarPlaceholder: { alignItems: 'center', justifyContent: 'center' },

    card: { backgroundColor: CARD, borderRadius: 20, paddingHorizontal: 18, paddingVertical: 16, marginBottom: 10, ...SOFT },
    cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
    cardTitle: { fontFamily: fonts.serif, fontSize: 17, color: INK, letterSpacing: -0.4, textTransform: 'lowercase' },
    seeAll: { fontFamily: 'Matter-Medium', fontSize: 13, color: MUTE },
    cheer: { fontFamily: 'Matter-Medium', fontSize: 12, color: SUB },
    eyebrow: { fontFamily: 'Matter-Medium', fontSize: 10, color: MUTE, letterSpacing: 0.7, textTransform: 'uppercase', marginBottom: 4 },

    journeyRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 },
    journeyNext: { fontFamily: 'Matter-SemiBold', fontSize: 15, color: INK, letterSpacing: -0.2 },
    journeyProg: { fontFamily: 'Matter-SemiBold', fontSize: 15, color: INK, letterSpacing: -0.2 },
    maxChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
    maxChip: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#F2F1EF', borderRadius: 999, paddingLeft: 8, paddingRight: 11, paddingVertical: 5 },
    maxChipDot: { width: 6, height: 6, borderRadius: 3 },
    maxChipText: { fontFamily: 'Matter-Medium', fontSize: 12.5, color: INK, letterSpacing: -0.1 },
    segRow: { flexDirection: 'row', gap: 5 },
    // 10pt, not the old 5: glass needs thickness to read — at 5pt the luminous
    // rims alone would consume half the bar and it would just look grey.
    seg: { flex: 1, height: 10, borderRadius: 5 },
    segOff: { backgroundColor: 'rgba(0,0,0,0.07)', borderRadius: 5 },

    daysRow: { flexDirection: 'row', gap: 7, marginBottom: 16 },
    dayPill: { flex: 1, height: 52, borderRadius: 16, backgroundColor: '#F2F1EF', alignItems: 'center', justifyContent: 'center', gap: 6 },
    dayPillToday: { backgroundColor: INK },
    dayDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: 'transparent' },
    dayDotOn: { backgroundColor: INK },
    dayDotToday: { backgroundColor: ON_INK },
    dayLetter: { fontFamily: 'Matter-Medium', fontSize: 12, color: SUB },
    dayLetterToday: { color: ON_INK, fontFamily: 'Matter-SemiBold' },

    weekStats: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' },
    weekVal: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: INK, letterSpacing: -0.3 },

    faceRow: { flexDirection: 'row', alignItems: 'flex-end' },
    faceNum: { fontFamily: 'Matter-SemiBold', fontSize: 30, color: INK, letterSpacing: -1, lineHeight: 32 },
    faceUnit: { fontFamily: 'Matter-Medium', fontSize: 13, color: MUTE, marginLeft: 2, marginBottom: 4 },
    faceDelta: { fontFamily: 'Matter-Medium', fontSize: 13, marginLeft: 9, marginBottom: 5 },
    faceArch: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: SUB, marginLeft: 'auto', marginBottom: 6 },
    faceLocked: { fontFamily: 'Matter-Medium', fontSize: 14.5, color: INK },

    trophyStrip: { gap: 14, paddingVertical: 2 },
    trophyItem: { alignItems: 'center', width: 62 },
    trophyLabel: { fontFamily: 'Matter-Medium', fontSize: 10.5, color: SUB, marginTop: 7, textAlign: 'center' },
    trophyEmpty: { fontFamily: 'Matter-Regular', fontSize: 13.5, color: MUTE, lineHeight: 20 },
});

export default function ProfileScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { width: winWidth } = useWindowDimensions();
    const imageModalWidth = getImageModalWidth(winWidth);
    const { user, refreshUser, isPaid, isPremium, isCreator } = useAuth();
    // Face-scan kill switch: hides the FACE SCORE card / scan entry points.
    const maxxesQuery = useMaxxesQuery();
    const schedulesFullQuery = useActiveSchedulesFullQuery();
    // Live weekly completion — same source as the Weekly Review screen — so the
    // card reflects real closed days this week instead of a stale profile field.
    const weeklyQuery = useQuery({
        queryKey: ['weeklyReview'],
        queryFn: () => api.getWeeklyReview(),
        staleTime: 60 * 1000,
    });
    const activeMaxxes = useMemo(() => {
        const allMaxxes = maxxesQuery.data?.maxes ?? [];
        const schedules = schedulesFullQuery.data?.schedules ?? [];
        const enrolledIds = new Set(
            schedules
                .filter((s: any) => s.maxx_id && s.maxx_id !== 'life')
                .map((s: any) => String(s.maxx_id).toLowerCase())
        );
        if (!enrolledIds.size) return [];
        return allMaxxes.filter((m: any) => m.id && enrolledIds.has(String(m.id).toLowerCase()));
    }, [maxxesQuery.data, schedulesFullQuery.data]);
    const queryClient = useQueryClient();
    // Photos / achievements / scan history via React Query (was manual
    // useState+useEffect that cold-refetched every mount and never revalidated).
    // Now cached, and focus/foreground revalidation comes free from the RQ config.
    const photosQuery = useQuery({
        queryKey: queryKeys.profileProgressPhotos,
        queryFn: () => api.getProgressPhotos(),
        select: (d: any) => d?.photos ?? [],
        staleTime: 60 * 1000,
    });
    const achievementsQuery = useQuery({
        queryKey: queryKeys.profileAchievements,
        queryFn: () => api.getAchievements(),
        staleTime: 60 * 1000,
    });
    const scanQuery = useQuery({
        queryKey: queryKeys.profileScanHistory,
        queryFn: () => api.getScanHistory(),
        select: (d: any) => parseScanPoints(d),
        staleTime: 60 * 1000,
    });
    const progressPhotos: any[] = photosQuery.data ?? [];
    const achievements = achievementsQuery.data ?? null;
    const scanPts = scanQuery.data ?? [];
    const loading = photosQuery.isLoading || achievementsQuery.isLoading || scanQuery.isLoading;
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
        Animated.timing(fadeAnim, { toValue: 1, duration: 400, useNativeDriver: true }).start();
    }, []);

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
            await queryClient.invalidateQueries({ queryKey: queryKeys.profileProgressPhotos });
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
                // Optimistically drop it from the cache (raw {photos} shape) for
                // instant UI, then reconcile with the server.
                queryClient.setQueryData(queryKeys.profileProgressPhotos, (old: any) => ({
                    ...(old || {}),
                    photos: ((old?.photos || []) as any[]).filter((p) => p.id !== photo.id),
                }));
                const remaining = progressPhotos.length - 1;
                if (remaining <= 0) {
                    setProgressModalVisible(false);
                } else {
                    setSelectedPhotoIndex(Math.min(index, remaining - 1));
                }
                queryClient.invalidateQueries({ queryKey: queryKeys.profileProgressPhotos });
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
        let avatarFailed = false;
        try {
            let newAvatarUrl = user?.profile?.avatar_url;
            if (editAvatarUri) {
                try {
                    const res = await api.uploadAvatar(editAvatarUri);
                    newAvatarUrl = res.avatar_url;
                } catch (avatarError: any) {
                    console.error('Avatar upload error:', avatarError);
                    // Don't pretend the new photo saved — flag it so we can tell
                    // the user after the rest of their changes go through.
                    avatarFailed = true;
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
            if (avatarFailed) {
                const photoMsg = 'We could not upload your new photo. Your other changes were saved.';
                if (Platform.OS === 'web') {
                    window.alert(photoMsg);
                } else {
                    Alert.alert('Photo not uploaded', photoMsg);
                }
            }
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

    const streak = user?.profile?.master_schedule_streak ?? user?.profile?.streak_days ?? 0;
    const achList: any[] = achievements?.achievements ?? [];
    const earnedAch = achList.filter((a) => a.earned);
    const nextAch = achList
        .filter((a) => !a.earned && a.progress)
        .sort((a, b) => (b.progress.current / b.progress.target) - (a.progress.current / a.progress.target))[0];
    // ── Derived values for the redesigned (pliability-style) layout ──
    const fullName = user?.first_name
        ? `${user.first_name} ${user.last_name || ''}`.trim()
        : (user?.username || (user?.email ? user.email.split('@')[0] : 'You'));
    // Maxes the user is actively running vs. the full catalog — the card tracks
    // how many they have right now.
    const allMaxes = maxxesQuery.data?.maxes ?? [];
    const totalMaxes = Math.max(allMaxes.length || 5, activeMaxxes.length);
    const maxesActive = Math.min(activeMaxxes.length, totalMaxes);
    const goExplore = () => navigation.navigate('Main', { screen: 'Explore' });
    const DAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
    const jsDay = new Date().getDay();          // 0=Sun … 6=Sat
    const todayIdx = (jsDay + 6) % 7;           // Mon=0 … Sun=6
    const streakClamped = Math.max(0, Math.min(streak, todayIdx + 1));
    // Prefer the live weekly review: real per-day closed state + this-week count.
    // Falls back to the streak-derived approximation while it's loading.
    const now = new Date();
    const localTodayISO = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const weekDays = weeklyQuery.data?.days ?? [];
    const weekPills =
        weekDays.length > 0
            ? weekDays.map((d) => ({
                  letter: (d.weekday || '').charAt(0).toUpperCase(),
                  closed: d.closed,
                  isToday: d.date === localTodayISO,
              }))
            : DAYS.map((d, i) => ({
                  letter: d,
                  closed: i !== todayIdx && i <= todayIdx && i >= todayIdx - streakClamped + 1,
                  isToday: i === todayIdx,
              }));
    const weekCount = weeklyQuery.data ? weeklyQuery.data.closed_count : streak;
    const achEarnedCount = achievements?.earned_count ?? earnedAch.length;
    const achTotal = achievements?.total ?? achList.length;

    return (
        <View style={p.root}>
            <View style={[p.topBar, { paddingTop: Math.max(insets.top, 10) }]}>
                {navigation.canGoBack() ? (
                    <TouchableOpacity onPress={() => navigation.goBack()} style={p.iconBtn} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel="Go back">
                        <Ionicons name="arrow-back" size={20} color={INK} />
                    </TouchableOpacity>
                ) : <View style={p.iconBtn} />}
                <View style={{ flex: 1 }} />
                <TouchableOpacity onPress={() => navigation.navigate('Settings')} style={p.iconBtn} activeOpacity={0.7} accessibilityLabel="Settings" accessibilityRole="button">
                    <Ionicons name="settings-outline" size={22} color={INK} />
                </TouchableOpacity>
            </View>

            {loading ? (
                <View style={p.loadingWrap}><ActivityIndicator color={INK} /></View>
            ) : (
                <Animated.ScrollView showsVerticalScrollIndicator={false} style={{ opacity: fadeAnim }} contentContainerStyle={p.scroll}>

                    {/* ── Identity ───────────────────────────────────── */}
                    <View style={p.identity}>
                        <View style={p.idLeft}>
                            <Text style={p.name} numberOfLines={2}>{fullName}</Text>
                            <TouchableOpacity style={p.editPill} onPress={handleEditPress} activeOpacity={0.85} accessibilityRole="button" accessibilityLabel="Edit profile">
                                <Text style={p.editPillText}>Edit Profile</Text>
                            </TouchableOpacity>
                        </View>
                        <TouchableOpacity onPress={handleEditPress} activeOpacity={0.85} accessibilityRole="button" accessibilityLabel="Edit profile photo">
                            {user?.profile?.avatar_url ? (
                                <CachedImage uri={api.resolveAttachmentUrl(user.profile.avatar_url)} style={p.avatar} />
                            ) : (
                                <View style={[p.avatar, p.avatarPlaceholder]}><Ionicons name="person" size={26} color={MUTE} /></View>
                            )}
                        </TouchableOpacity>
                    </View>

                    {/* ── Your Maxes — tracks how many you're running now ── */}
                    <View style={p.card}>
                        <View style={p.cardHead}>
                            <Text style={p.cardTitle}>Your Maxes</Text>
                            <TouchableOpacity onPress={goExplore} hitSlop={8} activeOpacity={0.7}>
                                <Text style={p.seeAll}>See all →</Text>
                            </TouchableOpacity>
                        </View>
                        <View style={p.journeyRow}>
                            <View style={{ flex: 1, paddingRight: 12 }}>
                                <Text style={p.eyebrow}>ACTIVE</Text>
                                {activeMaxxes.length ? (
                                    <View style={p.maxChips}>
                                        {activeMaxxes.map((m: any) => (
                                            <TouchableOpacity
                                                key={m.id}
                                                style={p.maxChip}
                                                onPress={() => navigation.navigate('MaxxDetail', { maxxId: m.id })}
                                                activeOpacity={0.7}
                                            >
                                                <View style={[p.maxChipDot, { backgroundColor: normalizeMaxxTintHex(m.color) }]} />
                                                <Text style={p.maxChipText}>{getMaxxDisplayLabel(m)}</Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>
                                ) : (
                                    <TouchableOpacity onPress={goExplore} activeOpacity={0.7}>
                                        <Text style={p.journeyNext}>Add your first max →</Text>
                                    </TouchableOpacity>
                                )}
                            </View>
                            <View style={{ alignItems: 'flex-end' }}>
                                <Text style={p.eyebrow}>TRACKING</Text>
                                <Text style={p.journeyProg}>{maxesActive}/{totalMaxes}</Text>
                            </View>
                        </View>
                        <View style={p.segRow}>
                            {Array.from({ length: totalMaxes }).map((_, i) =>
                                i < maxesActive ? (
                                    <GlassBar
                                        key={i}
                                        from={i / totalMaxes}
                                        to={(i + 1) / totalMaxes}
                                        style={p.seg}
                                        radius={5}
                                        // rising stagger → the reflection travels
                                        // the row as one light, left to right
                                        sweepDelayMs={i * 220}
                                    />
                                ) : (
                                    <View key={i} style={[p.seg, p.segOff]} />
                                )
                            )}
                        </View>
                    </View>

                    {/* ── XP / Rank ──────────────────────────────────── */}
                    <XpProgressCard data={schedulesFullQuery.data?.gamification} />

                    {/* ── Weekly Progress (streak) ───────────────────── */}
                    <View style={p.card}>
                        <View style={p.cardHead}>
                            <Text style={p.cardTitle}>Weekly Progress</Text>
                        </View>
                        <View style={p.daysRow}>
                            {weekPills.map((pill, i) => (
                                <View key={i} style={[p.dayPill, pill.isToday && p.dayPillToday]}>
                                    <View
                                        style={[
                                            p.dayDot,
                                            pill.closed && !pill.isToday && p.dayDotOn,
                                            pill.isToday && p.dayDotToday,
                                        ]}
                                    />
                                    <Text style={[p.dayLetter, pill.isToday && p.dayLetterToday]}>{pill.letter}</Text>
                                </View>
                            ))}
                        </View>
                        <View style={p.weekStats}>
                            <View>
                                <Text style={p.eyebrow}>THIS WEEK</Text>
                                <Text style={p.weekVal}>{weekCount} day{weekCount === 1 ? '' : 's'}</Text>
                            </View>
                            <TouchableOpacity onPress={() => navigation.navigate('Main', { screen: 'MasterScheduleTab' })} activeOpacity={0.7} style={{ alignItems: 'flex-end' }}>
                                <Text style={p.eyebrow}>SCHEDULE</Text>
                                <Text style={p.weekVal}>Open →</Text>
                            </TouchableOpacity>
                        </View>
                        <StreakMilestoneCallout />
                    </View>

                    {/* ── Progress Calendar ──────────────────────────── */}
                    <View style={p.card}>
                        <View style={p.cardHead}>
                            <Text style={p.cardTitle}>Progress</Text>
                            <TouchableOpacity onPress={() => navigation.navigate('FaceScanArchive')} hitSlop={8} activeOpacity={0.7}>
                                <Text style={p.seeAll}>All scans →</Text>
                            </TouchableOpacity>
                        </View>
                        <ProgressCalendar
                            progressPhotos={progressPhotos}
                            scanPts={scanPts}
                            onPhotoPress={(photo) => {
                                const idx = progressPhotos.findIndex(p => p.id === photo.id);
                                setSelectedPhotoIndex(idx >= 0 ? idx : 0);
                                setProgressModalVisible(true);
                            }}
                            onScanDay={() => navigation.navigate('FaceScan')}
                        />
                        {isPaid && !isPremium && (
                            <Text style={styles.chadliteNote}>
                                Snap photos any day, they track here. A daily face rating is a Chad feature.
                            </Text>
                        )}
                    </View>

                    {/* ── Trophy Case (achievements) ─────────────────── */}
                    <View style={p.card}>
                        <View style={p.cardHead}>
                            <Text style={p.cardTitle}>Trophy Case</Text>
                            <TouchableOpacity onPress={() => navigation.navigate('Achievements')} hitSlop={8} activeOpacity={0.7}>
                                <Text style={p.seeAll}>{achTotal ? `${achEarnedCount}/${achTotal}  →` : 'See all →'}</Text>
                            </TouchableOpacity>
                        </View>
                        {earnedAch.length ? (
                            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={p.trophyStrip}>
                                {earnedAch.slice(0, 12).map((a: any) => (
                                    <TouchableOpacity key={a.code || a.title} style={p.trophyItem} onPress={() => navigation.navigate('Achievements')} activeOpacity={0.85}>
                                        <AchievementBadge icon={a.icon} code={a.code} tier={a.tier} earned size={52} progress={null} />
                                        <Text style={p.trophyLabel} numberOfLines={1}>{a.title}</Text>
                                    </TouchableOpacity>
                                ))}
                            </ScrollView>
                        ) : (
                            <TouchableOpacity onPress={() => navigation.navigate('Achievements')} activeOpacity={0.7}>
                                <Text style={p.trophyEmpty}>Looks like you haven&apos;t earned a badge yet!</Text>
                            </TouchableOpacity>
                        )}
                    </View>

                    {isCreator ? (
                        <TouchableOpacity
                            onPress={() => navigation.navigate('CreatorStudio')}
                            activeOpacity={0.85}
                            style={{
                                flexDirection: 'row', alignItems: 'center', gap: 12,
                                marginHorizontal: spacing.lg, marginTop: spacing.md,
                                backgroundColor: '#111113', borderRadius: 18, padding: 16,
                            }}
                            accessibilityRole="button"
                            accessibilityLabel="Open Creator Studio"
                        >
                            <Ionicons name="star" size={20} color="#B8860B" />
                            <View style={{ flex: 1 }}>
                                <Text style={{ fontFamily: fonts.sansSemiBold, fontSize: 15.5, color: '#FFFFFF' }}>Creator Studio</Text>
                                <Text style={{ fontFamily: fonts.sans, fontSize: 12.5, color: 'rgba(255,255,255,0.6)', marginTop: 2 }}>Post updates, edit your course, see your subs</Text>
                            </View>
                            <Ionicons name="chevron-forward" size={18} color="rgba(255,255,255,0.6)" />
                        </TouchableOpacity>
                    ) : null}

                    <View style={{ height: 40 }} />
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
                                {/* Daily face rating is a Chad (premium) feature.
                                    ChadLite still keeps the photo, just no score. */}
                                {isPremium
                                    ? (progressPhotos[selectedPhotoIndex].face_rating != null &&
                                        Number.isFinite(Number(progressPhotos[selectedPhotoIndex].face_rating)) ? (
                                            <Text style={styles.progressModalRatingBadge}>
                                                {formatFaceRatingLabel(Number(progressPhotos[selectedPhotoIndex].face_rating))}
                                            </Text>
                                        ) : null)
                                    : (
                                        <Text style={styles.progressModalRatingLocked}>
                                            Daily rating · Chad only
                                        </Text>
                                    )}
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
                {/* Host an alert layer INSIDE this viewer modal so the delete-photo
                    confirm (Alert.alert in deleteProgressPhoto) renders ABOVE it — a
                    root-level host's modal would present BEHIND this one, making the
                    confirm dialog invisible and the Delete button appear dead. */}
                <InAppAlertHost />
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

    // ── Identity section (left-aligned, compact) ───────────────────────
    identitySection: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
        paddingBottom: spacing.lg,
    },
    idRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
    },
    idText: { flex: 1, minWidth: 0 },
    avatarImage: { width: 64, height: 64, borderRadius: 32 },
    avatarPlaceholder: {
        width: 64,
        height: 64,
        borderRadius: 32,
        backgroundColor: colors.surface,
        justifyContent: 'center',
        alignItems: 'center',
    },
    headerName: {
        fontFamily: fonts.serif,
        fontSize: 24,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.5,
    },
    headerMeta: {
        fontFamily: fonts.sans,
        fontSize: 13,
        color: colors.textMuted,
        marginTop: 3,
    },
    editBtn: {
        paddingVertical: 6,
        paddingHorizontal: 4,
    },
    headerBio: {
        fontSize: 14,
        fontWeight: '400',
        color: colors.textSecondary,
        lineHeight: 20,
        marginTop: spacing.md,
    },

    // ── Maxx tags (bare dot + label, no chrome) ─────────────────────────
    maxxTagsRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: spacing.md,
        marginTop: spacing.md,
    },
    maxxTag: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 2,
    },
    maxxDot: {
        width: 7,
        height: 7,
        borderRadius: 4,
    },
    maxxTagText: {
        fontSize: 13,
        fontWeight: '500',
        color: colors.textSecondary,
    },

    // ── Actions ──────────────────────────────────────────────────────────
    actionsRow: {
        flexDirection: 'row',
        justifyContent: 'center',
        gap: 10,
        marginTop: spacing.lg,
    },
    achievementsRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        marginTop: 12,
        paddingVertical: 14,
        paddingHorizontal: 16,
        borderRadius: borderRadius.lg,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        backgroundColor: colors.surfaceLight,
    },
    achievementsRowText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 15,
        color: colors.foreground,
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
        padding: 3,
        position: 'relative' as const,
    },
    photoGridImage: {
        width: '100%',
        height: '100%',
        borderRadius: borderRadius.md,
        backgroundColor: colors.surface,
    },
    progressRatingBadge: {
        position: 'absolute',
        bottom: 7,
        right: 7,
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

    // ── Redesign: identity extras ───────────────────────────────────────
    headerBioGhost: {
        fontFamily: fonts.sans,
        fontSize: 14,
        color: colors.textMuted,
        marginTop: spacing.md,
        textDecorationLine: 'underline',
    },
    editLink: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        color: colors.accent,
        letterSpacing: 0.1,
    },

    // ── Sections ─────────────────────────────────────────────────────────
    section: {
        paddingHorizontal: spacing.lg,
        marginBottom: spacing.xl,
    },
    sectionHead: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: spacing.md,
    },
    sectionLabelInline: { marginBottom: 0 },
    sectionCount: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        color: colors.textMuted,
        marginLeft: 8,
    },
    seeAll: {
        fontFamily: fonts.sansMedium,
        fontSize: 13,
        color: colors.accent,
    },
    chadliteNote: {
        fontFamily: fonts.sans,
        fontSize: 12.5,
        color: MUTE,
        lineHeight: 18,
        marginTop: 12,
        paddingHorizontal: 2,
    },

    // ── Score (flat, card-less) ──────────────────────────────────────────
    scoreRow: { flexDirection: 'row', alignItems: 'baseline', gap: 10 },
    scoreNum: {
        fontFamily: fonts.serif,
        fontSize: 44,
        color: colors.foreground,
        letterSpacing: -1.6,
    },
    scoreDelta: { fontFamily: fonts.sansSemiBold, fontSize: 14 },
    scoreDeltaMuted: { fontFamily: fonts.sansMedium, fontSize: 14, color: colors.textMuted },
    scoreSub: {
        fontFamily: fonts.sansMedium,
        fontSize: 13,
        color: colors.textSecondary,
        marginTop: 6,
    },
    scoreLockedFlat: {
        fontFamily: fonts.sansMedium,
        fontSize: 15,
        color: colors.accent,
        marginTop: spacing.sm,
    },

    // ── Add (ghost) + privacy ────────────────────────────────────────────
    addPill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 2,
        paddingVertical: 4,
        paddingHorizontal: 4,
    },
    addPillText: { fontFamily: fonts.sansSemiBold, fontSize: 13.5, color: colors.accent },
    privacyNote: { fontFamily: fonts.sans, fontSize: 11.5, color: colors.textMuted, marginTop: spacing.md },

    // ── Empty state ──────────────────────────────────────────────────────
    emptyState: {
        alignItems: 'center',
        paddingVertical: spacing.xxl,
        paddingHorizontal: spacing.lg,
        borderRadius: borderRadius.lg,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        borderStyle: 'dashed',
        backgroundColor: colors.surfaceLight,
    },
    emptyTitle: { fontFamily: fonts.serif, fontSize: 18, color: colors.foreground, marginBottom: 6 },
    emptySub: {
        fontFamily: fonts.sans,
        fontSize: 13,
        color: colors.textMuted,
        textAlign: 'center',
        lineHeight: 18,
    },

    // ── Achievements strip ───────────────────────────────────────────────
    achStrip: { gap: spacing.md, paddingRight: spacing.lg, paddingVertical: 2 },
    achItem: { alignItems: 'center', width: 68 },
    achItemLabel: {
        fontFamily: fonts.sansMedium,
        fontSize: 10.5,
        color: colors.textSecondary,
        textAlign: 'center',
        marginTop: 6,
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
    progressModalRatingLocked: {
        position: 'absolute',
        bottom: 10,
        right: 10,
        fontSize: 11,
        fontWeight: '600',
        color: 'rgba(255,255,255,0.82)',
        backgroundColor: 'rgba(10, 10, 10, 0.45)',
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
