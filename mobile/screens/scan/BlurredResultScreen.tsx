import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

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
            <View style={[styles.container, styles.centerContent]}>
                <ActivityIndicator size="large" color={colors.foreground} />
                <Text style={styles.loadingText}>Loading results...</Text>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            <ScrollView contentContainerStyle={styles.content}>
                <View style={styles.header}>
                    {navigation.canGoBack() ? (
                        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                            <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                        </TouchableOpacity>
                    ) : (
                        <View style={styles.backButton} />
                    )}
                    <Text style={styles.title}>Scan Complete</Text>
                    <View style={{ width: 40 }} />
                </View>

                <Text style={styles.medicalDisclaimer}>
                    For general wellness only—not a medical device or diagnosis. Talk to a clinician about health concerns.
                </Text>

                <View style={styles.scoreCard}>
                    <Text style={styles.scoreLabel}>YOUR SCORE</Text>
                    {isProcessing ? (
                        <>
                            <ActivityIndicator size="large" color={colors.foreground} style={{ marginVertical: spacing.lg }} />
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
                    {['Detailed Metrics', 'Improvement Suggestions', 'Course Recommendations', 'Progress Tracking'].map((item, i) => (
                        <View key={i} style={styles.lockedItem}>
                            <Ionicons name="lock-closed" size={18} color={colors.textMuted} />
                            <Text style={styles.lockedText}>{item}</Text>
                        </View>
                    ))}
                </View>

                <View style={styles.unlockCard}>
                    <Text style={styles.unlockTitle}>Unlock Full Results</Text>
                    <Text style={styles.unlockDesc}>
                        Get access to detailed analysis, personalized courses, live events, and progress tracking
                    </Text>
                    <TouchableOpacity style={styles.unlockButton} onPress={() => navigation.navigate('Payment')} activeOpacity={0.7}>
                        <Text style={styles.unlockButtonText}>Subscribe Now</Text>
                    </TouchableOpacity>
                    <Text style={styles.price}>$9.99/month</Text>
                </View>

                <TouchableOpacity onPress={() => navigation.navigate('LegalAndSafety')} style={styles.legalLink} activeOpacity={0.7}>
                    <Text style={styles.legalLinkText}>Privacy, support & delete account</Text>
                </TouchableOpacity>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    centerContent: { justifyContent: 'center', alignItems: 'center' },
    content: { padding: spacing.lg, paddingTop: 64, paddingBottom: spacing.xxl },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.lg },
    backButton: { width: 40, height: 40, justifyContent: 'center' },
    title: { ...typography.h2, textAlign: 'center' },
    loadingText: { fontSize: 14, marginTop: spacing.md, color: colors.textSecondary },
    processingText: { fontSize: 13, color: colors.textSecondary },
    medicalDisclaimer: {
        fontSize: 11,
        color: colors.textMuted,
        textAlign: 'center',
        lineHeight: 16,
        marginBottom: spacing.md,
        paddingHorizontal: spacing.sm,
    },
    legalLink: { alignItems: 'center', marginTop: spacing.lg, paddingVertical: spacing.md },
    legalLinkText: { fontSize: 13, color: colors.info, fontWeight: '600' },
    scoreCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        alignItems: 'center',
        marginBottom: spacing.xl,
        ...shadows.md,
    },
    scoreLabel: { ...typography.label, marginBottom: spacing.sm },
    score: { fontSize: 72, fontWeight: '700', color: colors.foreground, lineHeight: 82 },
    scoreMax: { fontSize: 18, fontWeight: '500', color: colors.textMuted },
    lockedSection: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        gap: spacing.md,
        marginBottom: spacing.xl,
        ...shadows.sm,
    },
    lockedItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, opacity: 0.4 },
    lockedText: { fontSize: 14, color: colors.textSecondary },
    unlockCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        alignItems: 'center',
        ...shadows.lg,
    },
    unlockTitle: { ...typography.h2, marginBottom: spacing.sm },
    unlockDesc: { fontSize: 13, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.lg, lineHeight: 19 },
    unlockButton: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.xxl,
        ...shadows.md,
    },
    unlockButtonText: { ...typography.button },
    price: { fontSize: 12, color: colors.textMuted, marginTop: spacing.sm },
});
