/**
 * Blurred Result Screen - Paywall
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function BlurredResultScreen() {
    const navigation = useNavigation<any>();
    const [scan, setScan] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [processing, setProcessing] = useState(false);

    useEffect(() => {
        loadScan();
    }, []);

    useEffect(() => {
        if (scan?.processing_status === 'processing') {
            setProcessing(true);
            const interval = setInterval(async () => {
                try {
                    const result = await api.getLatestScan();
                    setScan(result);
                    if (result.processing_status !== 'processing') {
                        setProcessing(false);
                        clearInterval(interval);
                    }
                } catch (e) {
                    console.error(e);
                }
            }, 3000);
            return () => clearInterval(interval);
        }
    }, [scan?.processing_status]);

    const loadScan = async () => {
        try {
            const result = await api.getLatestScan();
            setScan(result);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const overallScore = scan?.analysis?.overall_score ?? scan?.analysis?.metrics?.overall_score ?? null;
    const isProcessing = processing || scan?.processing_status === 'processing';

    if (loading) {
        return (
            <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={[styles.container, styles.centerContent]}>
                <ActivityIndicator size="large" color="#FFFFFF" />
                <Text style={styles.loadingText}>Loading results...</Text>
            </LinearGradient>
        );
    }

    return (
        <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
            <ScrollView contentContainerStyle={styles.content}>
                <View style={styles.header}>
                    {navigation.canGoBack() ? (
                        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                            <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                        </TouchableOpacity>
                    ) : (
                        <View style={styles.backButton} />
                    )}
                    <Text style={styles.title}>Scan Complete!</Text>
                    <View style={{ width: 40 }} />
                </View>

                <View style={styles.scoreCard}>
                    <Text style={styles.scoreLabel}>Your Score</Text>
                    {isProcessing ? (
                        <>
                            <ActivityIndicator size="large" color="#FFFFFF" style={{ marginVertical: spacing.lg }} />
                            <Text style={styles.processingText}>Analyzing your photos...</Text>
                        </>
                    ) : (
                        <>
                            <Text style={styles.score}>{overallScore !== null ? parseFloat(overallScore).toFixed(1) : '?'}</Text>
                            <Text style={styles.scoreMax}>/10</Text>
                        </>
                    )}
                </View>

                <View style={styles.lockedSection}>
                    <View style={styles.lockedItem}>
                        <Ionicons name="lock-closed" size={20} color="rgba(255,255,255,0.5)" />
                        <Text style={styles.lockedText}>Detailed Metrics</Text>
                    </View>
                    <View style={styles.lockedItem}>
                        <Ionicons name="lock-closed" size={20} color="rgba(255,255,255,0.5)" />
                        <Text style={styles.lockedText}>Improvement Suggestions</Text>
                    </View>
                    <View style={styles.lockedItem}>
                        <Ionicons name="lock-closed" size={20} color="rgba(255,255,255,0.5)" />
                        <Text style={styles.lockedText}>Course Recommendations</Text>
                    </View>
                    <View style={styles.lockedItem}>
                        <Ionicons name="lock-closed" size={20} color="rgba(255,255,255,0.5)" />
                        <Text style={styles.lockedText}>Progress Tracking</Text>
                    </View>
                </View>

                <View style={styles.unlockCard}>
                    <Ionicons name="star" size={32} color="#FFD700" />
                    <Text style={styles.unlockTitle}>Unlock Full Results</Text>
                    <Text style={styles.unlockDesc}>Get access to detailed analysis, personalized courses, live events, and progress tracking</Text>

                    <TouchableOpacity style={styles.unlockButton} onPress={() => navigation.navigate('Payment')}>
                        <Text style={styles.unlockButtonText}>Subscribe Now</Text>
                    </TouchableOpacity>

                    <Text style={styles.price}>$9.99/month</Text>
                </View>

                <TouchableOpacity style={styles.skipButton} onPress={() => navigation.navigate('Payment')}>
                    <Text style={styles.skipText}>Continue to see pricing options</Text>
                    <Ionicons name="arrow-forward" size={16} color="rgba(255,255,255,0.6)" />
                </TouchableOpacity>
            </ScrollView>
        </LinearGradient>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1 },
    centerContent: { justifyContent: 'center', alignItems: 'center' },
    content: { padding: spacing.lg, paddingTop: 60 },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.lg },
    backButton: { width: 40, height: 40, justifyContent: 'center' },
    title: { ...typography.h1, textAlign: 'center', color: '#FFFFFF' },
    loadingText: { ...typography.body, marginTop: spacing.md, color: 'rgba(255,255,255,0.7)' },
    processingText: { ...typography.bodySmall, color: 'rgba(255,255,255,0.7)' },
    scoreCard: { backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: borderRadius.lg, padding: spacing.xl, alignItems: 'center', marginBottom: spacing.xl, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
    scoreLabel: { ...typography.bodySmall, color: 'rgba(255,255,255,0.7)' },
    score: { fontSize: 80, fontFamily: 'Matter-Medium', fontWeight: '500', color: '#FFFFFF', lineHeight: 90 },
    scoreMax: { ...typography.h3, color: 'rgba(255,255,255,0.5)' },
    lockedSection: { backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: borderRadius.lg, padding: spacing.lg, gap: spacing.md, marginBottom: spacing.xl, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
    lockedItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, opacity: 0.6 },
    lockedText: { ...typography.body, color: 'rgba(255,255,255,0.7)' },
    unlockCard: { backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: borderRadius.lg, padding: spacing.xl, alignItems: 'center', borderWidth: 2, borderColor: 'rgba(255,255,255,0.3)' },
    unlockTitle: { ...typography.h2, marginTop: spacing.md, color: '#FFFFFF' },
    unlockDesc: { ...typography.bodySmall, textAlign: 'center', marginTop: spacing.sm, color: 'rgba(255,255,255,0.7)' },
    unlockButton: { backgroundColor: '#FFFFFF', borderRadius: borderRadius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl, marginTop: spacing.lg },
    unlockButtonText: { ...typography.button, color: '#000000' },
    price: { ...typography.caption, marginTop: spacing.sm, color: 'rgba(255,255,255,0.6)' },
    skipButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, paddingVertical: spacing.lg },
    skipText: { ...typography.bodySmall, color: 'rgba(255,255,255,0.6)' },
});


