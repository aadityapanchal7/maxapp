import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

type UmaxMetric = { id: string; label: string; score: number; summary?: string };

function parseOverall(analysis: any): number | null {
    if (!analysis) return null;
    const o =
        analysis.overall_score ??
        analysis.scan_summary?.overall_score ??
        analysis.metrics?.overall_score;
    if (o === undefined || o === null) return null;
    const n = parseFloat(String(o));
    return Number.isNaN(n) ? null : n;
}

function getScoreColor(score: number) {
    if (score >= 7) return colors.foreground;
    if (score >= 5) return colors.warning;
    return colors.error;
}

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

    const a = scan?.analysis;
    const overallScore = parseOverall(a);
    const umaxMetrics: UmaxMetric[] = Array.isArray(a?.umax_metrics) ? a.umax_metrics : [];
    const blurb = typeof a?.preview_blurb === 'string' ? a.preview_blurb : '';
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
                    <TouchableOpacity
                        onPress={() =>
                            navigation.canGoBack() ? navigation.goBack() : navigation.navigate('FeaturesIntro')
                        }
                        style={styles.backButton}
                    >
                        <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.title}>Face scan</Text>
                    <View style={{ width: 40 }} />
                </View>

                <Text style={styles.umaxTag}>AI facial rating</Text>

                <Text style={styles.medicalDisclaimer}>
                    For general wellness only—not a medical device or diagnosis. Talk to a clinician about health concerns.
                </Text>

                <View style={styles.scoreRing}>
                    <Text style={styles.scoreLabel}>OVERALL</Text>
                    {isProcessing ? (
                        <>
                            <ActivityIndicator size="large" color={colors.foreground} style={{ marginVertical: spacing.lg }} />
                            <Text style={styles.processingText}>Analyzing your photos…</Text>
                        </>
                    ) : (
                        <>
                            <Text style={[styles.bigScore, overallScore != null ? { color: getScoreColor(overallScore) } : null]}>
                                {overallScore != null ? overallScore.toFixed(1) : '—'}
                            </Text>
                            <Text style={styles.outOf}>/ 10</Text>
                        </>
                    )}
                </View>

                {blurb ? <Text style={styles.blurb}>{blurb}</Text> : null}

                {!isProcessing && umaxMetrics.length > 0 && (
                    <View style={styles.metricsCard}>
                        <Text style={styles.metricsTitle}>Breakdown</Text>
                        {umaxMetrics.map((m) => {
                            const s = Math.max(0, Math.min(10, Number(m.score) || 0));
                            const pct = (s / 10) * 100;
                            return (
                                <View key={m.id} style={styles.metricRow}>
                                    <View style={styles.metricTop}>
                                        <Text style={styles.metricName}>{m.label}</Text>
                                        <Text style={[styles.metricNum, { color: getScoreColor(s) }]}>{s.toFixed(1)}</Text>
                                    </View>
                                    <View style={styles.metricTrack}>
                                        <View style={[styles.metricFill, { width: `${pct}%`, backgroundColor: getScoreColor(s) }]} />
                                    </View>
                                    {m.summary ? <Text style={styles.metricHint}>{m.summary}</Text> : null}
                                </View>
                            );
                        })}
                    </View>
                )}

                <View style={styles.lockedSection}>
                    {['Full written report', 'Improvement roadmap', 'Course matching', 'Progress over time'].map((item, i) => (
                        <View key={i} style={styles.lockedItem}>
                            <Ionicons name="lock-closed" size={18} color={colors.textMuted} />
                            <Text style={styles.lockedText}>{item}</Text>
                        </View>
                    ))}
                </View>

                <View style={styles.unlockCard}>
                    <Text style={styles.unlockTitle}>Unlock everything</Text>
                    <Text style={styles.unlockDesc}>
                        Subscribe for full analysis, personalized programs, and tracking — same membership as before.
                    </Text>
                    <TouchableOpacity style={styles.unlockButton} onPress={() => navigation.navigate('Payment')} activeOpacity={0.7}>
                        <Text style={styles.unlockButtonText}>Subscribe now</Text>
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
    content: { padding: spacing.lg, paddingTop: 56, paddingBottom: spacing.xxl },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm },
    backButton: { width: 40, height: 40, justifyContent: 'center' },
    title: { ...typography.h2, textAlign: 'center' },
    loadingText: { fontSize: 14, marginTop: spacing.md, color: colors.textSecondary },
    processingText: { fontSize: 13, color: colors.textSecondary },
    umaxTag: {
        alignSelf: 'center',
        ...typography.label,
        color: colors.textMuted,
        marginBottom: spacing.sm,
    },
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
    scoreRing: {
        alignSelf: 'center',
        width: 200,
        height: 200,
        borderRadius: 100,
        borderWidth: 4,
        borderColor: colors.borderLight,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: spacing.lg,
        backgroundColor: colors.card,
        ...shadows.md,
    },
    scoreLabel: { ...typography.label, marginBottom: spacing.xs },
    bigScore: { fontSize: 56, fontWeight: '800', color: colors.foreground },
    outOf: { fontSize: 16, color: colors.textMuted, fontWeight: '600' },
    blurb: {
        fontSize: 15,
        color: colors.textSecondary,
        textAlign: 'center',
        lineHeight: 22,
        marginBottom: spacing.xl,
        paddingHorizontal: spacing.sm,
    },
    metricsCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        marginBottom: spacing.xl,
        ...shadows.md,
    },
    metricsTitle: { ...typography.label, marginBottom: spacing.md },
    metricRow: { marginBottom: spacing.lg },
    metricTop: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
    metricName: { fontSize: 14, fontWeight: '600', color: colors.foreground, flex: 1 },
    metricNum: { fontSize: 14, fontWeight: '800' },
    metricTrack: {
        height: 8,
        borderRadius: 4,
        backgroundColor: colors.borderLight,
        overflow: 'hidden',
    },
    metricFill: { height: '100%', borderRadius: 4 },
    metricHint: { fontSize: 12, color: colors.textMuted, marginTop: 6 },
    lockedSection: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        gap: spacing.md,
        marginBottom: spacing.xl,
        ...shadows.sm,
    },
    lockedItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, opacity: 0.45 },
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
