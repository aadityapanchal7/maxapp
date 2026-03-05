import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Animated } from 'react-native';
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

    const fadeAnim = useRef(new Animated.Value(0)).current;
    const slideAnim = useRef(new Animated.Value(20)).current;

    useFocusEffect(React.useCallback(() => { loadData(); }, []));

    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
            Animated.timing(slideAnim, { toValue: 0, duration: 500, useNativeDriver: true }),
        ]).start();
    }, []);

    const loadData = async () => {
        try { const progressRes = await api.getCourseProgress(); setProgress(progressRes.progress || []); }
        catch (error) { console.error(error); }
        finally { setLoading(false); }
    };

    const userName = user?.email?.split('@')[0] || 'there';

    return (
        <View style={styles.container}>
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
                <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>
                    <View style={styles.hero}>
                        <View style={styles.heroTop}>
                            <View>
                                <Text style={styles.greeting}>Welcome back,</Text>
                                <Text style={styles.userName}>{userName}</Text>
                            </View>
                            <TouchableOpacity style={styles.profileButton} onPress={() => navigation.navigate('Profile')} activeOpacity={0.7}>
                                <View style={styles.profileIcon}>
                                    <Text style={styles.profileInitial}>{userName.charAt(0).toUpperCase()}</Text>
                                </View>
                            </TouchableOpacity>
                        </View>
                    </View>

                    <View style={styles.section}>
                        <View style={styles.sectionHeader}>
                            <Text style={styles.sectionLabel}>MY COURSES</Text>
                            {progress.length > 0 && <Text style={styles.sectionCount}>{progress.length}</Text>}
                        </View>

                        {progress.map((p, i) => (
                            <TouchableOpacity key={i} style={styles.courseCard} onPress={() => navigation.navigate('CourseDetail', { courseId: p.course_id })} activeOpacity={0.7}>
                                <View style={styles.courseRow}>
                                    <View style={styles.courseIcon}>
                                        <Ionicons name={i % 2 === 0 ? "book-outline" : "water-outline"} size={16} color={colors.textSecondary} />
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
                            <TouchableOpacity style={styles.emptyCard} onPress={() => navigation.navigate('CourseList')} activeOpacity={0.7}>
                                <Text style={styles.emptyTitle}>No courses yet</Text>
                                <Text style={styles.emptyDesc}>Start your first course to begin your journey</Text>
                                <View style={styles.emptyButton}>
                                    <Text style={styles.emptyButtonText}>Browse Courses</Text>
                                </View>
                            </TouchableOpacity>
                        )}
                    </View>
                </Animated.View>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    scrollContent: { paddingBottom: spacing.xxxl },
    hero: { paddingHorizontal: spacing.lg, paddingTop: 64, paddingBottom: spacing.lg },
    heroTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    greeting: { fontSize: 13, color: colors.textMuted, marginBottom: 2, letterSpacing: 0.3 },
    userName: { fontSize: 28, fontWeight: '700', color: colors.foreground, letterSpacing: -0.5 },
    profileButton: { padding: 2 },
    profileIcon: {
        width: 40, height: 40, borderRadius: 20,
        backgroundColor: colors.foreground, alignItems: 'center', justifyContent: 'center',
        ...shadows.sm,
    },
    profileInitial: { fontSize: 16, fontWeight: '600', color: colors.buttonText },
    section: { paddingHorizontal: spacing.lg, marginTop: spacing.sm },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
    sectionLabel: { ...typography.label },
    sectionCount: {
        fontSize: 11, fontWeight: '600', color: colors.textSecondary,
        backgroundColor: colors.surface,
        paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10,
    },
    courseCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        marginBottom: spacing.sm,
        ...shadows.sm,
    },
    courseRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    courseIcon: {
        width: 36, height: 36, borderRadius: borderRadius.sm,
        backgroundColor: colors.surface,
        alignItems: 'center', justifyContent: 'center',
    },
    courseContent: { flex: 1 },
    courseTitle: { fontSize: 14, fontWeight: '600', color: colors.foreground, marginBottom: 6 },
    progressRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    progressBar: { flex: 1, height: 3, backgroundColor: colors.borderLight, borderRadius: 2, overflow: 'hidden' },
    progressFill: { height: '100%', backgroundColor: colors.foreground, borderRadius: 2 },
    coursePercent: { fontSize: 12, fontWeight: '500', color: colors.textMuted, width: 32, textAlign: 'right' },
    emptyCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xxl,
        alignItems: 'center',
        ...shadows.md,
    },
    emptyTitle: { fontSize: 17, fontWeight: '600', color: colors.foreground, marginBottom: spacing.xs },
    emptyDesc: { fontSize: 13, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.lg },
    emptyButton: {
        backgroundColor: colors.foreground,
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.sm + 2,
        borderRadius: borderRadius.full,
        ...shadows.sm,
    },
    emptyButtonText: { fontSize: 13, fontWeight: '600', color: colors.buttonText },
});
