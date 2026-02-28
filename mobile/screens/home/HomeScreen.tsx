import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function HomeScreen() {
    const navigation = useNavigation<any>();
    const { user } = useAuth();
    const [progress, setProgress] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useFocusEffect(React.useCallback(() => { loadData(); }, []));

    const loadData = async () => {
        try { const progressRes = await api.getCourseProgress(); setProgress(progressRes.progress || []); }
        catch (error) { console.error(error); }
        finally { setLoading(false); }
    };

    const userName = user?.email?.split('@')[0] || 'Champion';

    return (
        <View style={styles.container}>
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
                <View style={styles.headerSection}>
                    <View style={styles.headerContent}>
                        <View>
                            <Text style={styles.greeting}>Welcome back,</Text>
                            <Text style={styles.userName}>{userName}</Text>
                        </View>
                        <TouchableOpacity style={styles.profileButton} onPress={() => navigation.navigate('Profile')} activeOpacity={0.8}>
                            <View style={styles.profileIconContainer}>
                                <Text style={styles.profileInitial}>{userName.charAt(0).toUpperCase()}</Text>
                            </View>
                        </TouchableOpacity>
                    </View>
                </View>

                <View style={styles.section}>
                    <View style={styles.sectionHeader}>
                        <Text style={styles.sectionTitle}>My Courses</Text>
                        <Text style={styles.sectionBadge}>{progress.length}</Text>
                    </View>

                    {progress.map((p, i) => (
                        <TouchableOpacity key={i} style={styles.courseCard} onPress={() => navigation.navigate('CourseDetail', { courseId: p.course_id })} activeOpacity={0.8}>
                            <View style={styles.courseRow}>
                                <View style={styles.courseIconBox}>
                                    <Ionicons name={i % 2 === 0 ? "book-outline" : "water-outline"} size={18} color={colors.accent} />
                                </View>
                                <View style={styles.courseContent}>
                                    <Text style={styles.courseTitle} numberOfLines={1}>{p.course_title || 'Course'}</Text>
                                    <View style={styles.progressRow}>
                                        <View style={styles.progressBar}>
                                            <View style={[styles.progressFill, { width: `${p.progress_percentage}%` }]} />
                                        </View>
                                        <Text style={styles.coursePercent}>{Math.round(p.progress_percentage)}%</Text>
                                    </View>
                                </View>
                                <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                            </View>
                        </TouchableOpacity>
                    ))}

                    {progress.length === 0 && (
                        <TouchableOpacity style={styles.emptyCard} onPress={() => navigation.navigate('CourseList')} activeOpacity={0.8}>
                            <Ionicons name="book-outline" size={32} color={colors.accent} />
                            <Text style={styles.emptyTitle}>No courses yet</Text>
                            <Text style={styles.emptyDesc}>Start your first course to begin your journey</Text>
                            <View style={styles.emptyButton}>
                                <Text style={styles.emptyButtonText}>Browse Courses</Text>
                            </View>
                        </TouchableOpacity>
                    )}
                </View>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    scrollContent: { paddingBottom: spacing.xxl },
    headerSection: { paddingHorizontal: spacing.lg, paddingTop: 56, paddingBottom: spacing.md },
    headerContent: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    greeting: { fontSize: 13, color: colors.textMuted, marginBottom: 2, letterSpacing: 0.3 },
    userName: { fontSize: 24, fontWeight: '700', color: colors.textPrimary, letterSpacing: -0.3 },
    profileButton: { padding: 2 },
    profileIconContainer: {
        width: 44, height: 44, borderRadius: 22,
        backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center',
    },
    profileInitial: { fontSize: 18, fontWeight: '700', color: colors.buttonText },
    section: { paddingHorizontal: spacing.lg, marginTop: spacing.sm },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
    sectionTitle: { fontSize: 18, fontWeight: '600', color: colors.textPrimary },
    sectionBadge: {
        fontSize: 11, fontWeight: '700', color: colors.accent,
        backgroundColor: colors.accentMuted,
        paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10,
    },
    courseCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.md,
        padding: spacing.md,
        marginBottom: spacing.sm,
        ...shadows.sm,
    },
    courseRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    courseIconBox: {
        width: 38, height: 38, borderRadius: borderRadius.sm,
        backgroundColor: colors.accentMuted,
        alignItems: 'center', justifyContent: 'center',
    },
    courseContent: { flex: 1 },
    courseTitle: { fontSize: 14, fontWeight: '600', color: colors.textPrimary, marginBottom: 6 },
    progressRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    progressBar: { flex: 1, height: 4, backgroundColor: colors.border, borderRadius: 2, overflow: 'hidden' },
    progressFill: { height: '100%', backgroundColor: colors.accent, borderRadius: 2 },
    coursePercent: { fontSize: 12, fontWeight: '600', color: colors.textMuted, width: 32, textAlign: 'right' },
    emptyCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.xl,
        alignItems: 'center',
        ...shadows.sm,
    },
    emptyTitle: { fontSize: 16, fontWeight: '600', color: colors.textPrimary, marginTop: spacing.md },
    emptyDesc: { fontSize: 13, color: colors.textMuted, textAlign: 'center', marginTop: spacing.xs, marginBottom: spacing.md },
    emptyButton: {
        backgroundColor: colors.accentMuted,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.sm,
        borderRadius: borderRadius.sm,
    },
    emptyButtonText: { fontSize: 13, fontWeight: '600', color: colors.accent },
});
