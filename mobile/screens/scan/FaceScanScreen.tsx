import React, { useState, useRef, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert, Platform } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';
import AnalyzingScreen from './AnalyzingScreen';

const VIDEO_DURATION = 15;

const SCAN_PHASES = [
    { time: 0, label: 'Front View', instruction: 'Look straight at the camera' },
    { time: 4, label: 'Left Profile', instruction: 'Slowly turn your head to the left' },
    { time: 8, label: 'Back to Front', instruction: 'Turn back to the front' },
    { time: 11, label: 'Right Profile', instruction: 'Slowly turn your head to the right' },
];

function WebCameraView({ onReady }: { onReady: (api: any) => void }) {
    const videoRef = useRef<any>(null);
    const mediaRecorderRef = useRef<any>(null);
    const chunksRef = useRef<any[]>([]);
    const streamRef = useRef<any>(null);
    const resolveRecording = useRef<((blob: Blob) => void) | null>(null);
    const mountedRef = useRef(true);
    const onReadyRef = useRef(onReady);
    onReadyRef.current = onReady;
    const [cameraError, setCameraError] = useState<string | null>(null);

    const containerCallbackRef = useCallback((node: any) => {
        if (!node || videoRef.current) return;
        mountedRef.current = true;
        const initCamera = async () => {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
                    audio: true,
                });
                if (!mountedRef.current) { stream.getTracks().forEach((t: any) => t.stop()); return; }
                streamRef.current = stream;
                const video = document.createElement('video');
                video.srcObject = stream;
                video.autoplay = true;
                video.playsInline = true;
                video.muted = true;
                video.style.cssText = 'width:100%;height:100%;object-fit:cover;transform:scaleX(-1);position:absolute;top:0;left:0;';
                node.style.position = 'relative';
                node.appendChild(video);
                videoRef.current = video;
                onReadyRef.current({
                    startRecording: () => {
                        if (!streamRef.current) return;
                        chunksRef.current = [];
                        const mimeType = typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
                            ? 'video/webm;codecs=vp9' : 'video/webm';
                        const recorder = new MediaRecorder(streamRef.current, { mimeType });
                        recorder.ondataavailable = (e: any) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
                        recorder.onstop = () => {
                            const blob = new Blob(chunksRef.current, { type: mimeType });
                            if (resolveRecording.current) { resolveRecording.current(blob); resolveRecording.current = null; }
                        };
                        mediaRecorderRef.current = recorder;
                        recorder.start(500);
                    },
                    stopRecording: (): Promise<Blob> => new Promise((resolve) => {
                        resolveRecording.current = resolve;
                        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop();
                    }),
                });
            } catch (err: any) {
                console.error('Camera access error:', err);
                setCameraError(err?.message || 'Camera access denied');
            }
        };
        initCamera();
    }, []);

    useEffect(() => {
        return () => {
            mountedRef.current = false;
            streamRef.current?.getTracks().forEach((t: any) => t.stop());
            if (videoRef.current?.parentNode) videoRef.current.parentNode.removeChild(videoRef.current);
        };
    }, []);

    return (
        <View style={styles.cameraContainer} ref={containerCallbackRef as any}>
            {cameraError && (
                <View style={styles.cameraErrorContainer}>
                    <Text style={styles.cameraErrorText}>Camera error: {cameraError}</Text>
                    <Text style={styles.cameraErrorText}>Please allow camera access and reload.</Text>
                </View>
            )}
            <View style={styles.overlayAbsolute}>
                <View style={styles.faceGuide} />
            </View>
        </View>
    );
}

export default function FaceScanScreen() {
    const navigation = useNavigation<any>();
    const { isPaid, refreshUser } = useAuth();
    const cameraApiRef = useRef<any>(null);
    const [isRecording, setIsRecording] = useState(false);
    const [timer, setTimer] = useState(0);
    const [analyzing, setAnalyzing] = useState(false);
    const [analysisStep, setAnalysisStep] = useState(0);
    const [cameraReady, setCameraReady] = useState(false);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (isRecording && timer < VIDEO_DURATION) {
            interval = setInterval(() => setTimer((prev) => prev + 1), 1000);
        } else if (timer >= VIDEO_DURATION && isRecording) {
            handleStopRecording();
        }
        return () => clearInterval(interval);
    }, [isRecording, timer]);

    const handleCameraReady = useCallback((api: any) => {
        cameraApiRef.current = api;
        setCameraReady(true);
    }, []);

    const startRecording = async () => {
        if (!cameraApiRef.current || isRecording) return;
        try {
            setIsRecording(true);
            setTimer(0);
            if (Platform.OS === 'web') {
                cameraApiRef.current.startRecording();
            } else {
                const video = await cameraApiRef.current.recordAsync({ maxDuration: VIDEO_DURATION });
                if (video) await uploadNativeVideo(video.uri);
            }
        } catch (error) {
            console.error('Recording error:', error);
            setIsRecording(false);
            Alert.alert('Error', 'Failed to start recording');
        }
    };

    const handleStopRecording = async () => {
        if (!cameraApiRef.current) return;
        setIsRecording(false);
        if (Platform.OS === 'web') {
            try {
                const blob = await cameraApiRef.current.stopRecording();
                await uploadWebVideo(blob);
            } catch (error) {
                console.error('Stop recording error:', error);
                Alert.alert('Error', 'Failed to process recording');
            }
        } else {
            cameraApiRef.current.stopRecording();
        }
    };

    const uploadWebVideo = async (blob: Blob) => {
        setAnalyzing(true); setAnalysisStep(0);
        try {
            const uploadResult = await api.uploadScanVideoBlob(blob);
            setAnalysisStep(1);
            await api.analyzeScan(uploadResult.scan_id);
            setAnalysisStep(2);
            await refreshUser();
            await new Promise(resolve => setTimeout(resolve, 1000));
            navigation.navigate(isPaid ? 'FullResult' : 'BlurredResult');
        } catch (error) {
            console.error('Upload error:', error);
            Alert.alert('Error', 'Failed to analyze video. Please try again.');
            setAnalyzing(false);
        }
    };

    const uploadNativeVideo = async (videoUri: string) => {
        setAnalyzing(true); setAnalysisStep(0);
        try {
            const uploadResult = await api.uploadScanVideo(videoUri);
            setAnalysisStep(1);
            await api.analyzeScan(uploadResult.scan_id);
            setAnalysisStep(2);
            await refreshUser();
            await new Promise(resolve => setTimeout(resolve, 1000));
            navigation.navigate(isPaid ? 'FullResult' : 'BlurredResult');
        } catch (error) {
            console.error('Upload error:', error);
            Alert.alert('Error', 'Failed to analyze video. Please try again.');
            setAnalyzing(false);
        }
    };

    if (analyzing) return <AnalyzingScreen currentStep={analysisStep} />;

    const currentPhase = [...SCAN_PHASES].reverse().find(p => timer >= p.time) || SCAN_PHASES[0];

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>{currentPhase.label}</Text>
                <Text style={styles.instruction}>
                    {isRecording ? currentPhase.instruction : 'Prepare for a 15-second scan'}
                </Text>
                {isRecording && (
                    <View style={styles.timerContainer}>
                        <View style={[styles.timerBar, { width: `${(timer / VIDEO_DURATION) * 100}%` }]} />
                        <Text style={styles.timerText}>{VIDEO_DURATION - timer}s remaining</Text>
                    </View>
                )}
            </View>

            {Platform.OS === 'web' ? <WebCameraView onReady={handleCameraReady} /> : <NativeCameraWrapper cameraApiRef={cameraApiRef} onReady={() => setCameraReady(true)} />}

            <View style={styles.controls}>
                {!cameraReady ? (
                    <Text style={styles.loadingText}>Starting camera...</Text>
                ) : !isRecording ? (
                    <TouchableOpacity style={styles.recordButton} onPress={startRecording}>
                        <View style={styles.recordButtonInner} />
                    </TouchableOpacity>
                ) : (
                    <TouchableOpacity style={styles.stopButton} onPress={handleStopRecording}>
                        <Ionicons name="stop" size={32} color="#FF3B30" />
                    </TouchableOpacity>
                )}
            </View>
            <Text style={styles.hint}>
                {!cameraReady ? 'Initializing camera...' : !isRecording ? 'Tap to start 15s scan' : 'Keep your face within the guide'}
            </Text>
        </View>
    );
}

function NativeCameraWrapper({ cameraApiRef, onReady }: any) {
    const [hasPermission, setHasPermission] = useState<boolean | null>(null);
    const localRef = useRef<any>(null);
    useEffect(() => {
        (async () => {
            const { Camera } = require('expo-camera');
            const { status } = await Camera.requestCameraPermissionsAsync();
            const { status: audioStatus } = await Camera.requestMicrophonePermissionsAsync();
            const granted = status === 'granted' && audioStatus === 'granted';
            setHasPermission(granted);
            if (granted) { cameraApiRef.current = localRef.current; onReady(); }
        })();
    }, []);
    if (hasPermission === null) return <View style={styles.cameraContainer}><Text style={styles.centerText}>Requesting permissions...</Text></View>;
    if (hasPermission === false) return <View style={styles.cameraContainer}><Text style={styles.centerText}>Camera and Audio permissions required</Text></View>;
    const { CameraView } = require('expo-camera');
    return (
        <View style={styles.cameraContainer}>
            <CameraView ref={localRef} style={styles.camera} facing="front" mode="video">
                <View style={styles.overlayAbsolute}><View style={styles.faceGuide} /></View>
            </CameraView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: { paddingTop: 60, paddingHorizontal: spacing.lg, alignItems: 'center', height: 180 },
    title: { ...typography.h2 },
    instruction: { ...typography.bodySmall, marginTop: spacing.xs, textAlign: 'center' },
    timerContainer: { marginTop: spacing.md, width: '100%', alignItems: 'center' },
    timerBar: { height: 4, backgroundColor: colors.primary, position: 'absolute', bottom: -10, left: 0, borderRadius: 2 },
    timerText: { ...typography.bodySmall, color: colors.textPrimary, fontWeight: 'bold' },
    cameraContainer: { flex: 1, margin: spacing.lg, borderRadius: borderRadius.lg, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, backgroundColor: '#000', position: 'relative' },
    camera: { flex: 1 },
    overlayAbsolute: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center' },
    faceGuide: { width: 250, height: 320, borderRadius: 125, borderWidth: 2, borderColor: 'rgba(255,255,255,0.5)', borderStyle: 'dashed' },
    controls: { paddingBottom: spacing.xl, alignItems: 'center', minHeight: 100, justifyContent: 'center' },
    recordButton: { width: 80, height: 80, borderRadius: 40, borderWidth: 4, borderColor: colors.accent, justifyContent: 'center', alignItems: 'center' },
    recordButtonInner: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#FF3B30' },
    stopButton: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: colors.border },
    hint: { ...typography.bodySmall, textAlign: 'center', marginBottom: spacing.xl },
    centerText: { ...typography.body, textAlign: 'center', color: colors.buttonText, padding: 20 },
    cameraErrorContainer: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center', zIndex: 10, backgroundColor: 'rgba(0,0,0,0.7)' },
    cameraErrorText: { ...typography.body, textAlign: 'center', color: colors.buttonText, padding: 8 },
    loadingText: { ...typography.body, color: colors.textMuted },
});
