import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function ScanDetailScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { scanId } = route.params;
    const [scan, setScan] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadScan(); }, []);
    const loadScan = async () => { try { setScan(await api.getScanById(scanId)); } catch (e) { console.error(e); } finally { setLoading(false); } };

    const safeToFixed = (val: any, digits: number = 1): string => { const num = parseFloat(val); return isNaN(num) ? '0.0' : num.toFixed(digits); };
    const getScoreColor = (score: number) => { const s = parseFloat(String(score)) || 0; if (s >= 7) return colors.accent; if (s >= 5) return colors.warning; return colors.error; };

    const a = scan?.analysis || {};
    const overallScore = parseFloat(a.scan_summary?.overall_score) || parseFloat(a.metrics?.overall_score) || parseFloat(a.overall_score) || 0;

    let recommendations: any[] = [];
    if (a.ai_recommendations?.recommendations) { recommendations = a.ai_recommendations.recommendations.map((r: any) => ({ area: r.title || 'General', suggestion: r.description || r.suggestion || '' })); }
    else { recommendations = a.improvements || a.recommendations || []; }

    const getMetricValue = (key: string): number => {
        if (a.measurements) { const f = a.measurements.front_view || {}; const p = a.measurements.profile_view || {};
            switch (key) { case 'midface_ratio': return f.midface_ratio?.score ?? 0; case 'canthal_tilt': return f.canthal_tilt_left?.score ?? 0; case 'jaw_cheek_ratio': return f.jaw_cheek_ratio?.score ?? 0; case 'nose_width_ratio': return f.nose_width_ratio?.score ?? 0; case 'gonial_angle': return p.gonial_angle?.score ?? 0; case 'nasolabial_angle': return p.nasolabial_angle?.score ?? 0; case 'mentolabial_angle': return p.mentolabial_angle?.score ?? 0; case 'facial_convexity': return p.facial_convexity?.score ?? 0; } }
        const m = a.metrics || a;
        switch (key) { case 'facial_symmetry': return m.proportions?.overall_symmetry ?? m.harmony_score ?? 0; case 'jawline_definition': return m.jawline?.definition_score ?? 0; case 'skin_quality': return m.skin?.overall_quality ?? 0; case 'facial_fat': return m.body_fat?.facial_leanness ?? 0; case 'eye_area': return m.eye_area?.symmetry_score ?? 0; case 'nose_proportion': return m.nose?.overall_harmony ?? 0; case 'lip_ratio': return m.lips?.lip_symmetry ?? 0; default: return 0; }
    };

    const metricItems = a.measurements ? [
        { key: 'midface_ratio', label: 'Midface Ratio', icon: 'resize' }, { key: 'canthal_tilt', label: 'Canthal Tilt', icon: 'eye' }, { key: 'jaw_cheek_ratio', label: 'Jaw-Cheek Ratio', icon: 'fitness' }, { key: 'nose_width_ratio', label: 'Nose Proportion', icon: 'water' }, { key: 'gonial_angle', label: 'Gonial Angle', icon: 'analytics' }, { key: 'nasolabial_angle', label: 'Nasolabial Angle', icon: 'git-merge' }, { key: 'mentolabial_angle', label: 'Mentolabial Angle', icon: 'git-commit' }, { key: 'facial_convexity', label: 'Facial Convexity', icon: 'person' },
    ] : [
        { key: 'facial_symmetry', label: 'Facial Symmetry', icon: 'grid' }, { key: 'jawline_definition', label: 'Jawline Definition', icon: 'fitness' }, { key: 'skin_quality', label: 'Skin Quality', icon: 'sparkles' }, { key: 'facial_fat', label: 'Facial Leanness', icon: 'body' }, { key: 'eye_area', label: 'Eye Area', icon: 'eye' }, { key: 'nose_proportion', label: 'Nose Harmony', icon: 'resize' }, { key: 'lip_ratio', label: 'Lip Balance', icon: 'ellipse' },
    ];

    if (loading) return <View style={[styles.container, styles.centerContent]}><ActivityIndicator size="large" color={colors.primary} /><Text style={styles.loadingText}>Loading scan...</Text></View>;
    if (!scan) return <View style={[styles.container, styles.centerContent]}><Text style={styles.errorText}>Scan not found</Text><TouchableOpacity onPress={() => navigation.goBack()}><Text style={{ color: colors.primary }}>Go Back</Text></TouchableOpacity></View>;

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}><Ionicons name="arrow-back" size={24} color={colors.textPrimary} /></TouchableOpacity>
                <Text style={styles.title}>Scan Details</Text>
                <View style={{ width: 40 }} />
            </View>
            <Text style={styles.dateText}>{new Date(scan.created_at).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</Text>

            <View style={styles.scoreCard}>
                <Text style={styles.scoreLabel}>Overall Score</Text>
                <Text style={[styles.score, { color: getScoreColor(overallScore) }]}>{safeToFixed(overallScore)}</Text>
                <Text style={styles.scoreMax}>/10</Text>
            </View>

            <Text style={styles.sectionTitle}>Detailed Analysis</Text>
            <View style={styles.metricsCard}>
                {metricItems.map((item) => { const value = getMetricValue(item.key); return (
                    <View key={item.key} style={styles.metricItem}>
                        <View style={styles.metricLeft}><Ionicons name={item.icon as any} size={20} color={colors.textSecondary} /><Text style={styles.metricLabel}>{item.label}</Text></View>
                        <View style={styles.metricRight}><View style={styles.metricBar}><View style={[styles.metricFill, { width: `${value * 10}%`, backgroundColor: getScoreColor(value) }]} /></View><Text style={[styles.metricValue, { color: getScoreColor(value) }]}>{safeToFixed(value)}</Text></View>
                    </View>
                ); })}
            </View>

            {recommendations.length > 0 && (<>
                <Text style={styles.sectionTitle}>Recommendations</Text>
                <View style={styles.recommendationsCard}>
                    {recommendations.map((rec: any, index: number) => (
                        <View key={index} style={styles.recItem}>
                            <Ionicons name="checkmark-circle" size={20} color={colors.primary} />
                            <View style={styles.recContent}><Text style={styles.recArea}>{rec.area}</Text><Text style={styles.recSuggestion}>{rec.suggestion}</Text></View>
                        </View>
                    ))}
                </View>
            </>)}
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    centerContent: { justifyContent: 'center', alignItems: 'center' },
    content: { paddingBottom: spacing.xxl },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
    backButton: { width: 40, height: 40, justifyContent: 'center' },
    title: { ...typography.h2 },
    dateText: { ...typography.bodySmall, textAlign: 'center', color: colors.textMuted, marginBottom: spacing.md },
    loadingText: { ...typography.body, marginTop: spacing.md, color: colors.textSecondary },
    errorText: { ...typography.body, color: colors.error, marginBottom: spacing.md },
    scoreCard: { margin: spacing.lg, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.xl, alignItems: 'center', ...shadows.sm },
    scoreLabel: { ...typography.bodySmall },
    score: { fontSize: 80, fontWeight: '800', lineHeight: 90 },
    scoreMax: { ...typography.h3, color: colors.textMuted },
    sectionTitle: { ...typography.h3, marginHorizontal: spacing.lg, marginTop: spacing.lg, marginBottom: spacing.md },
    metricsCard: { marginHorizontal: spacing.lg, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.lg, ...shadows.sm },
    metricItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
    metricLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1 },
    metricLabel: { ...typography.bodySmall },
    metricRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, flex: 1 },
    metricBar: { flex: 1, height: 8, backgroundColor: colors.border, borderRadius: 4 },
    metricFill: { height: '100%', borderRadius: 4 },
    metricValue: { ...typography.body, fontWeight: '700', width: 35, textAlign: 'right' },
    recommendationsCard: { marginHorizontal: spacing.lg, backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.lg, gap: spacing.md, ...shadows.sm },
    recItem: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
    recContent: { flex: 1 },
    recArea: { ...typography.body, fontWeight: '600' },
    recSuggestion: { ...typography.bodySmall, marginTop: 2 },
});
