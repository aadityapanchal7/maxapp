/**
 * Face Scan Screen - 15-second video capture
 */

import React, { useState, useRef, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { Camera, CameraView } from 'expo-camera';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';
import AnalyzingScreen from './AnalyzingScreen';

const VIDEO_DURATION = 15; // seconds

const SCAN_PHASES = [
    { time: 0, label: 'Front View', instruction: 'Look straight at the camera' },
    { time: 4, label: 'Left Profile', instruction: 'Slowly turn your head to the left' },
    { time: 8, label: 'Back to Front', instruction: 'Turn back to the front' },
    { time: 11, label: 'Right Profile', instruction: 'Slowly turn your head to the right' },
];

export default function FaceScanScreen() {
    const navigation = useNavigation<any>();
    const { isPaid, refreshUser } = useAuth();
    const cameraRef = useRef<CameraView>(null);
    const [hasPermission, setHasPermission] = useState<boolean | null>(null);
    const [isRecording, setIsRecording] = useState<boolean>(false);
    const [timer, setTimer] = useState<number>(0);
    const [analyzing, setAnalyzing] = useState<boolean>(false);
    const [analysisStep, setAnalysisStep] = useState<number>(0);

    useEffect(() => {
        (async () => {
            const { status } = await Camera.requestCameraPermissionsAsync();
            const { status: audioStatus } = await Camera.requestMicrophonePermissionsAsync();
            setHasPermission(status === 'granted' && audioStatus === 'granted');
        })();
    }, []);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (isRecording && timer < VIDEO_DURATION) {
            interval = setInterval(() => {
                setTimer((prev) => prev + 1);
            }, 1000);
        } else if (timer >= VIDEO_DURATION && isRecording) {
            stopRecording();
        }
        return () => clearInterval(interval);
    }, [isRecording, timer]);

    const startRecording = async () => {
        if (!cameraRef.current || isRecording) return;

        try {
            setIsRecording(true);
            setTimer(0);

            const video = await cameraRef.current.recordAsync({
                maxDuration: VIDEO_DURATION,
            });

            if (video) {
                await uploadVideo(video.uri);
            }
        } catch (error) {
            console.error("Recording error:", error);
            setIsRecording(false);
            Alert.alert('Error', 'Failed to start recording');
        }
    };

    const stopRecording = () => {
        if (cameraRef.current && isRecording) {
            cameraRef.current.stopRecording();
            setIsRecording(false);
        }
    };

    const uploadVideo = async (videoUri: string) => {
        setAnalyzing(true);
        setAnalysisStep(0);

        try {
            // Step 1: Uploading video
            setAnalysisStep(0);
            const uploadResult = await api.uploadScanVideo(videoUri);

            // Step 2: Extracting features & Analyzing
            setAnalysisStep(1);
            await api.analyzeScan(uploadResult.scan_id);

            // Step 3: Generating results
            setAnalysisStep(2);
            await refreshUser();

            // Small delay to show completion
            await new Promise(resolve => setTimeout(resolve, 1000));

            // Route based on payment status
            if (isPaid) {
                navigation.navigate('FullResult');
            } else {
                navigation.navigate('BlurredResult');
            }
        } catch (error) {
            console.error("Upload error:", error);
            Alert.alert('Error', 'Failed to analyze video');
            setAnalyzing(false);
        }
    };

    // Show analyzing screen during processing
    if (analyzing) {
        return <AnalyzingScreen currentStep={analysisStep} />;
    }

    if (hasPermission === null) {
        return (
            <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
                <Text style={styles.text}>Requesting permissions...</Text>
            </LinearGradient>
        );
    }
    if (hasPermission === false) {
        return (
            <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
                <Text style={styles.text}>Camera and Audio permissions required</Text>
            </LinearGradient>
        );
    }

    const currentPhase = [...SCAN_PHASES].reverse().find(p => timer >= p.time) || SCAN_PHASES[0];

    return (
        <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>{currentPhase.label}</Text>
                <Text style={styles.instruction}>{isRecording ? currentPhase.instruction : 'Prepare for a 15-second scan'}</Text>

                {isRecording && (
                    <View style={styles.timerContainer}>
                        <View style={[styles.timerBar, { width: `${(timer / VIDEO_DURATION) * 100}%` }]} />
                        <Text style={styles.timerText}>{VIDEO_DURATION - timer}s remaining</Text>
                    </View>
                )}
            </View>

            <View style={styles.cameraContainer}>
                <CameraView
                    ref={cameraRef}
                    style={styles.camera}
                    facing="front"
                    mode="video"
                >
                    <View style={styles.overlay}>
                        <View style={styles.faceGuide} />
                    </View>
                </CameraView>
            </View>

            <View style={styles.controls}>
                {!isRecording ? (
                    <TouchableOpacity style={styles.recordButton} onPress={startRecording}>
                        <View style={styles.recordButtonInner} />
                    </TouchableOpacity>
                ) : (
                    <TouchableOpacity style={styles.stopButton} onPress={stopRecording}>
                        <Ionicons name="stop" size={32} color="#FF3B30" />
                    </TouchableOpacity>
                )}
            </View>

            <Text style={styles.hint}>
                {!isRecording ? 'Tap to start 15s scan' : 'Keep your face within the guide'}
            </Text>
        </LinearGradient>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1 },
    header: { paddingTop: 60, paddingHorizontal: spacing.lg, alignItems: 'center', height: 180 },
    title: { ...typography.h2, color: '#FFFFFF' },
    instruction: { ...typography.bodySmall, marginTop: spacing.xs, color: 'rgba(255,255,255,0.7)', textAlign: 'center' },
    timerContainer: { marginTop: spacing.md, width: '100%', alignItems: 'center' },
    timerBar: { height: 4, backgroundColor: '#FFFFFF', position: 'absolute', bottom: -10, left: 0, borderRadius: 2 },
    timerText: { ...typography.bodySmall, color: '#FFFFFF', fontWeight: 'bold' },
    cameraContainer: { flex: 1, margin: spacing.lg, borderRadius: borderRadius.lg, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
    camera: { flex: 1 },
    overlay: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    faceGuide: { width: 250, height: 320, borderRadius: 125, borderWidth: 2, borderColor: 'rgba(255,255,255,0.5)', borderStyle: 'dashed' },
    controls: { paddingBottom: spacing.xl, alignItems: 'center' },
    recordButton: { width: 80, height: 80, borderRadius: 40, borderWidth: 4, borderColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center' },
    recordButtonInner: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#FF3B30' },
    stopButton: { width: 80, height: 80, borderRadius: 40, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center' },
    hint: { ...typography.bodySmall, textAlign: 'center', marginBottom: spacing.xl, color: 'rgba(255,255,255,0.7)' },
    text: { ...typography.body, textAlign: 'center', marginTop: 100, color: '#FFFFFF' },
});

