import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert, Image } from 'react-native';
import { CommonActions, useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import AnalyzingScreen from './AnalyzingScreen';

const STEPS = [
    {
        key: 'front',
        title: 'Front',
        instruction: 'Face the camera straight on. Neutral expression, good lighting.',
    },
    {
        key: 'left',
        title: 'Left profile',
        instruction: 'Turn so your LEFT cheek and jaw face the camera (about 90°).',
    },
    {
        key: 'right',
        title: 'Right profile',
        instruction: 'Turn so your RIGHT cheek and jaw face the camera (about 90°).',
    },
] as const;

export default function FaceScanScreen() {
    const navigation = useNavigation<any>();
    const { user, isPaid, refreshUser } = useAuth();
    const [permission, requestPermission] = useCameraPermissions();
    const cameraRef = useRef<CameraView>(null);

    const [stepIndex, setStepIndex] = useState(0);
    const [uris, setUris] = useState<(string | null)[]>([null, null, null]);
    const [analyzing, setAnalyzing] = useState(false);
    const [analysisStep, setAnalysisStep] = useState(0);

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
        if (user?.first_scan_completed) {
            const target = isPaid ? 'FullResult' : 'BlurredResult';
            navigation.dispatch(
                CommonActions.reset({
                    index: 0,
                    routes: [{ name: target }],
                }),
            );
        }
    }, [user?.first_scan_completed, isPaid, navigation]);

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
        try {
            setAnalysisStep(1);
            await api.uploadScanTriple(f, l, r);
            setAnalysisStep(2);
            await refreshUser();
            const target = isPaid ? 'FullResult' : 'BlurredResult';
            // Reset stack so a stable initial route + auth refresh can't pop us back to FaceScan.
            navigation.dispatch(
                CommonActions.reset({
                    index: 1,
                    routes: [{ name: 'FeaturesIntro' }, { name: target }],
                }),
            );
            didLeaveScan = true;
        } catch (err) {
            console.error(err);
            Alert.alert('Error', 'Could not analyze photos. Check connection and try again.');
        } finally {
            if (!didLeaveScan) setAnalyzing(false);
        }
    };

    if (analyzing) {
        return <AnalyzingScreen currentStep={analysisStep} />;
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

            <Text style={styles.title}>{step.title}</Text>
            <Text style={styles.instruction}>{step.instruction}</Text>

            <View style={styles.cameraContainer}>
                {hasCurrent ? (
                    <Image source={{ uri: currentUri }} style={styles.preview} resizeMode="cover" />
                ) : (
                    <CameraView ref={cameraRef} style={styles.camera} facing="front" mode="picture" />
                )}
            </View>

            <View style={styles.actions}>
                {!hasCurrent && (
                    <TouchableOpacity style={styles.primaryBtn} onPress={capture} activeOpacity={0.85}>
                        <Ionicons name="camera" size={22} color={colors.background} style={{ marginRight: 8 }} />
                        <Text style={styles.primaryBtnText}>Capture</Text>
                    </TouchableOpacity>
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
                We use three photos once to build your facial rating and breakdown. You can’t submit a second scan.
            </Text>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
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
