import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Alert,
    AppState,
    ActivityIndicator,
    Platform,
    type AppStateStatus,
} from 'react-native';
import { CommonActions, useFocusEffect, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { CameraView, useCameraPermissions } from 'expo-camera';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { CachedImage } from '../../components/CachedImage';
import AnalyzingScreen from './AnalyzingScreen';
import {
    saveFaceScanDraft,
    loadFaceScanDraft,
    clearFaceScanDraft,
    setPendingFaceScanSubmit,
    clearPendingFaceScanSubmit,
    getPendingFaceScanSubmit,
} from '../../lib/faceScanDraft';

const STEPS = [
    {
        key: 'front',
        title: 'Front',
        instruction: 'Straight on, neutral expression.',
    },
    {
        key: 'left',
        title: 'Left profile',
        instruction: 'Left cheek toward camera, ~90°.',
    },
    {
        key: 'right',
        title: 'Right profile',
        instruction: 'Right cheek toward camera, ~90°.',
    },
] as const;

export default function FaceScanScreen() {
    const navigation = useNavigation<any>();
    const { user, isPaid, isPremium, refreshUser } = useAuth();
    const [permission, requestPermission] = useCameraPermissions();
    const cameraRef = useRef<CameraView>(null);

    const [stepIndex, setStepIndex] = useState(0);
    const [uris, setUris] = useState<(string | null)[]>([null, null, null]);
    const [analyzing, setAnalyzing] = useState(false);
    const [analysisStep, setAnalysisStep] = useState(0);
    const [bootstrapped, setBootstrapped] = useState(false);
    const [cameraSession, setCameraSession] = useState(0);
    const [appActive, setAppActive] = useState(() => AppState.currentState === 'active');
    const appStateRef = useRef<AppStateStatus>(AppState.currentState);
    const analyzingRef = useRef(false);
    analyzingRef.current = analyzing;

    const navigateToResults = useCallback(() => {
        navigation.dispatch(
            CommonActions.reset({
                index: 1,
                routes: [{ name: 'FeaturesIntro' }, { name: 'FaceScanResults' }],
            }),
        );
    }, [navigation]);

    const runAnalyzingRecovery = useCallback(
        async (fromForeground: boolean) => {
            const delays = [0, 1500, 3000, 4500];
            for (const ms of delays) {
                if (ms > 0) await new Promise((r) => setTimeout(r, ms));
                try {
                    const u = await refreshUser();
                    if (u?.first_scan_completed) {
                        await clearPendingFaceScanSubmit();
                        await clearFaceScanDraft();
                        navigateToResults();
                        return;
                    }
                } catch {
                    /* continue */
                }
                try {
                    const latest = await api.getLatestScan();
                    const st = (latest as { processing_status?: string })?.processing_status;
                    if (st === 'completed' || st === 'processing') {
                        if (st === 'completed') {
                            await refreshUser();
                            await clearPendingFaceScanSubmit();
                            await clearFaceScanDraft();
                            navigateToResults();
                            return;
                        }
                        continue;
                    }
                    if (st === 'failed') {
                        await clearPendingFaceScanSubmit();
                        setAnalyzing(false);
                        Alert.alert(
                            'Try again',
                            'Your photos need another pass. Tap Analyze again — and don\'t worry, closing the app next time won\'t interrupt it. Enable SMS coaching in Profile for a more integrated experience.',
                        );
                        return;
                    }
                } catch {
                    /* 404 = no scan row yet */
                }
            }
            try {
                const latest = await api.getLatestScan();
                const st = (latest as { processing_status?: string })?.processing_status;
                if (st === 'processing') {
                    await clearPendingFaceScanSubmit();
                    navigateToResults();
                    return;
                }
            } catch {
                /* no scan */
            }
            await clearPendingFaceScanSubmit();
            setAnalyzing(false);
            if (fromForeground) {
                Alert.alert(
                    'Pick up where you left off',
                    'Don\'t worry — you can close the app anytime, your analysis keeps running. Open Results from your profile, or tap Analyze again. For a more integrated experience, enable SMS coaching in Profile.',
                );
            }
        },
        [navigateToResults, refreshUser],
    );

    useEffect(() => {
        if (!user?.id) {
            setBootstrapped(true);
            return;
        }
        let cancelled = false;
        void (async () => {
            try {
                const pending = await getPendingFaceScanSubmit();
                if (cancelled) return;
                if (pending?.userId === user.id) {
                    setAnalyzing(true);
                    setAnalysisStep(1);
                    await runAnalyzingRecovery(false);
                    return;
                }
                const draft = await loadFaceScanDraft(user.id);
                if (!cancelled && draft) {
                    setStepIndex(draft.stepIndex);
                    setUris(draft.uris);
                }
            } catch (e) {
                console.warn('face scan bootstrap', e);
            } finally {
                if (!cancelled) setBootstrapped(true);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [user?.id, runAnalyzingRecovery]);

    useFocusEffect(
        useCallback(() => {
            if (Platform.OS === 'web') return;
            setCameraSession((s) => s + 1);
        }, []),
    );

    useEffect(() => {
        if (!user?.id || analyzing || !bootstrapped) return;
        const hasAny = uris.some(Boolean);
        if (!hasAny && stepIndex === 0) {
            void clearFaceScanDraft().catch(() => undefined);
            return;
        }
        const t = setTimeout(() => {
            void saveFaceScanDraft(user.id, stepIndex, uris).catch((e) => console.warn('face scan draft save', e));
        }, 450);
        return () => clearTimeout(t);
    }, [user?.id, stepIndex, uris, analyzing, bootstrapped]);

    const step = STEPS[stepIndex];
    const currentUri = uris[stepIndex];
    const hasCurrent = !!currentUri;

    useEffect(() => {
        if (!permission?.granted && permission?.canAskAgain !== false) {
            requestPermission();
        }
    }, [permission?.granted, permission?.canAskAgain, requestPermission]);

    /** One face scan per account — block repeat visits to this screen. */
    useLayoutEffect(() => {
        if (user?.first_scan_completed && !isPaid) {
            navigation.dispatch(
                CommonActions.reset({
                    index: 0,
                    routes: [{ name: 'FaceScanResults' }],
                }),
            );
        }
    }, [user?.first_scan_completed, isPaid, navigation]);

    // Premium: one scan per calendar day. Basic can scan multiple days until server enforces the lifetime cap.
    useEffect(() => {
        const run = async () => {
            if (!isPaid || !isPremium) return;
            try {
                const latest = await api.getLatestScan();
                const ts = latest?.created_at ? new Date(latest.created_at) : null;
                if (!ts || Number.isNaN(ts.getTime())) return;
                const now = new Date();
                const sameDay =
                    ts.getFullYear() === now.getFullYear() &&
                    ts.getMonth() === now.getMonth() &&
                    ts.getDate() === now.getDate();
                if (sameDay) {
                    Alert.alert('Daily face scan', 'You already did your face scan today. Come back tomorrow.');
                    if (navigation.canGoBack()) {
                        navigation.goBack();
                    }
                }
            } catch {
                // ignore
            }
        };
        void run();
    }, [isPaid, isPremium, navigation]);

    /**
     * Resume camera cleanly after background; recover analyzing flow from server when user returns.
     */
    useEffect(() => {
        const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
            const prev = appStateRef.current;
            appStateRef.current = next;
            setAppActive(next === 'active');
            if (prev.match(/inactive|background/) && next === 'active') {
                setCameraSession((s) => s + 1);
            }
            if (!analyzingRef.current) return;
            if (!prev.match(/inactive|background/) || next !== 'active') return;
            void runAnalyzingRecovery(true);
        });
        return () => sub.remove();
    }, [runAnalyzingRecovery]);

    const capture = async () => {
        try {
            const photo = await cameraRef.current?.takePictureAsync({
                quality: 0.85,
                skipProcessing: true,
            });
            if (!photo?.uri) {
                Alert.alert('Error', 'Could not capture photo');
                return;
            }
            setUris((prev) => {
                const next = [...prev];
                next[stepIndex] = photo.uri;
                return next;
            });
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Capture failed');
        }
    };

    const retake = () => {
        setUris((prev) => {
            const next = [...prev];
            next[stepIndex] = null;
            return next;
        });
    };

    const pickFromLibrary = async () => {
        try {
            const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
            if (status !== 'granted') {
                Alert.alert('Photos', 'Allow photo library access to upload a picture.');
                return;
            }
            const result = await ImagePicker.launchImageLibraryAsync({
                mediaTypes: ImagePicker.MediaTypeOptions.Images,
                allowsEditing: false,
                quality: 0.85,
            });
            if (result.canceled || !result.assets?.[0]?.uri) return;
            const uri = result.assets[0].uri;
            setUris((prev) => {
                const next = [...prev];
                next[stepIndex] = uri;
                return next;
            });
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not open photo library.');
        }
    };

    const goNext = () => {
        if (stepIndex < STEPS.length - 1) setStepIndex((s) => s + 1);
    };

    const goBackStep = () => {
        if (stepIndex > 0) setStepIndex((s) => s - 1);
    };

    const submitScans = async () => {
        const f = uris[0];
        const l = uris[1];
        const r = uris[2];
        if (!f || !l || !r) {
            Alert.alert('Missing photos', 'Capture all three angles first.');
            return;
        }
        setAnalyzing(true);
        setAnalysisStep(0);
        let didLeaveScan = false;
        if (user?.id) {
            try {
                await setPendingFaceScanSubmit(user.id);
            } catch (e) {
                console.warn('pending submit flag', e);
            }
        }
        try {
            setAnalysisStep(1);
            const scanRes = (await api.uploadScanTriple(f, l, r)) as { analysis?: { overall_score?: number } };
            setAnalysisStep(2);
            const os = scanRes?.analysis?.overall_score;
            const rating =
                typeof os === 'number' && Number.isFinite(os) ? Math.round(os * 10) / 10 : undefined;
            try {
                await api.uploadProgressPhoto(f, { faceRating: rating });
            } catch (pe) {
                console.warn('Progress photo from face scan', pe);
            }
            await refreshUser();
            await clearPendingFaceScanSubmit();
            await clearFaceScanDraft();
            navigateToResults();
            didLeaveScan = true;
        } catch (err: unknown) {
            console.error(err);
            await clearPendingFaceScanSubmit().catch(() => undefined);
            const ax = err as { response?: { data?: { detail?: string } } };
            const detail = ax?.response?.data?.detail;
            Alert.alert(
                'Error',
                typeof detail === 'string' && detail.trim()
                    ? detail
                    : 'Could not analyze photos. Check connection and try again.',
            );
        } finally {
            if (!didLeaveScan) setAnalyzing(false);
        }
    };

    if (analyzing) {
        return <AnalyzingScreen currentStep={analysisStep} />;
    }

    if (!bootstrapped) {
        return (
            <View style={[styles.container, styles.bootstrapRoot]}>
                <ActivityIndicator size="large" color={colors.foreground} />
                <Text style={styles.bootstrapHint}>Restoring your scan…</Text>
            </View>
        );
    }

    if (!permission?.granted) {
        return (
            <View style={[styles.container, styles.permWrap]}>
                <Text style={styles.permText}>Camera access is needed for your face scan.</Text>
                <TouchableOpacity style={styles.permBtn} onPress={() => requestPermission()}>
                    <Text style={styles.permBtnText}>Allow camera</Text>
                </TouchableOpacity>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.headerIcon} hitSlop={12}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.progressLabel}>
                    Photo {stepIndex + 1} of {STEPS.length}
                </Text>
                <View style={styles.headerIcon} />
            </View>

            <Text style={styles.medicalDisclaimer}>
                For general wellness only — not medical advice.
            </Text>

            {isPaid && !isPremium ? (
                <Text style={styles.basicScanCap}>
                    Basic: one scan only. Upgrade to Premium for daily scans.
                </Text>
            ) : null}

            <Text style={styles.title}>{step.title}</Text>
            <Text style={styles.instruction}>{step.instruction}</Text>

            <View style={styles.cameraContainer}>
                {hasCurrent ? (
                    <CachedImage uri={currentUri!} style={styles.preview} />
                ) : appActive ? (
                    <CameraView
                        key={cameraSession}
                        ref={cameraRef}
                        style={styles.camera}
                        facing="front"
                        mode="picture"
                    />
                ) : (
                    <View style={[styles.camera, styles.cameraPaused]}>
                        <Text style={styles.cameraPausedText}>Camera paused</Text>
                    </View>
                )}
            </View>

            <View style={styles.actions}>
                {!hasCurrent && (
                    <View style={styles.row}>
                        <TouchableOpacity style={styles.primaryBtn} onPress={capture} activeOpacity={0.85}>
                            <Ionicons name="camera" size={22} color={colors.background} style={{ marginRight: 8 }} />
                            <Text style={styles.primaryBtnText}>Capture</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={styles.uploadBtn} onPress={pickFromLibrary} activeOpacity={0.85}>
                            <Ionicons name="images-outline" size={22} color={colors.foreground} style={{ marginRight: 8 }} />
                            <Text style={styles.uploadBtnText}>Upload</Text>
                        </TouchableOpacity>
                    </View>
                )}

                {hasCurrent && (
                    <View style={styles.row}>
                        <TouchableOpacity style={styles.secondaryBtn} onPress={retake}>
                            <Text style={styles.secondaryBtnText}>Retake</Text>
                        </TouchableOpacity>
                        {stepIndex < STEPS.length - 1 ? (
                            <TouchableOpacity style={styles.primaryBtn} onPress={goNext}>
                                <Text style={styles.primaryBtnText}>Next angle</Text>
                            </TouchableOpacity>
                        ) : (
                            <TouchableOpacity style={styles.primaryBtn} onPress={submitScans}>
                                <Text style={styles.primaryBtnText}>Analyze</Text>
                            </TouchableOpacity>
                        )}
                    </View>
                )}

                {stepIndex > 0 && !hasCurrent && (
                    <TouchableOpacity style={styles.linkBack} onPress={goBackStep}>
                        <Text style={styles.linkBackText}>← Previous angle</Text>
                    </TouchableOpacity>
                )}
            </View>

            <Text style={styles.hint}>
                {isPremium
                    ? 'Premium: one three-photo scan per calendar day.'
                    : isPaid
                      ? 'Basic: one scan only (no extras on this plan).'
                      : 'One free preview — three angles, then Analyze.'}
            </Text>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    bootstrapRoot: { justifyContent: 'center', alignItems: 'center', gap: spacing.md },
    bootstrapHint: { ...typography.body, color: colors.textMuted },
    permWrap: { justifyContent: 'center', alignItems: 'center', padding: spacing.xl },
    permText: { ...typography.body, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.lg },
    permBtn: {
        backgroundColor: colors.foreground,
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.md,
        borderRadius: borderRadius.full,
    },
    permBtnText: { ...typography.button, color: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: 56,
        paddingHorizontal: spacing.md,
    },
    headerIcon: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
    progressLabel: { ...typography.label, color: colors.textMuted },
    medicalDisclaimer: {
        fontSize: 11,
        color: colors.textMuted,
        textAlign: 'center',
        marginHorizontal: spacing.md,
        marginTop: spacing.xs,
        lineHeight: 16,
    },
    basicScanCap: {
        fontSize: 12,
        fontWeight: '600',
        color: colors.foreground,
        textAlign: 'center',
        marginHorizontal: spacing.md,
        marginTop: spacing.sm,
        lineHeight: 18,
    },
    title: { ...typography.h2, textAlign: 'center', marginTop: spacing.md },
    instruction: {
        fontSize: 14,
        color: colors.textSecondary,
        textAlign: 'center',
        marginHorizontal: spacing.lg,
        marginTop: spacing.sm,
        lineHeight: 21,
    },
    cameraContainer: {
        flex: 1,
        margin: spacing.lg,
        borderRadius: borderRadius['2xl'],
        overflow: 'hidden',
        backgroundColor: '#000',
        minHeight: 360,
        ...shadows.lg,
    },
    camera: { flex: 1, width: '100%', minHeight: 360 },
    cameraPaused: { backgroundColor: '#111', justifyContent: 'center', alignItems: 'center' },
    cameraPausedText: { color: '#fff', fontSize: 15, opacity: 0.85 },
    preview: { flex: 1, width: '100%', minHeight: 360 },
    actions: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md },
    row: { flexDirection: 'row', gap: spacing.md, justifyContent: 'center', flexWrap: 'wrap' },
    primaryBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        paddingHorizontal: spacing.xl,
        borderRadius: borderRadius.full,
        flexGrow: 1,
        minWidth: 140,
    },
    primaryBtnText: { ...typography.button, color: colors.background },
    uploadBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 14,
        paddingHorizontal: spacing.xl,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        minWidth: 140,
    },
    uploadBtnText: { ...typography.button, color: colors.foreground },
    secondaryBtn: {
        paddingVertical: 14,
        paddingHorizontal: spacing.xl,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.borderLight,
        justifyContent: 'center',
    },
    secondaryBtnText: { ...typography.button, color: colors.foreground },
    linkBack: { alignItems: 'center', paddingVertical: spacing.sm },
    linkBackText: { color: colors.textMuted, fontSize: 14 },
    hint: {
        fontSize: 12,
        color: colors.textMuted,
        textAlign: 'center',
        paddingHorizontal: spacing.lg,
        marginBottom: spacing.md,
    },
});
