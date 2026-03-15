import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Animated, Image } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function HomeScreen() {
    const navigation = useNavigation<any>();
    const { user } = useAuth();
    const [progress, setProgress] = useState<any[]>([]);
    const [courses, setCourses] = useState<any[]>([]);
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
        try {
            const [progressRes, coursesRes] = await Promise.all([
                api.getCourseProgress(),
                api.getCourses()
            ]);
            setProgress(progressRes.progress || []);
            setCourses(coursesRes.courses || []);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const userName = user?.first_name || user?.email?.split('@')[0] || 'there';

    // Determine which maxxes to show based on user's onboarded goals
    const selectedGoals: string[] = user?.onboarding?.goals || [];

    // Dummy module lists per maxx goal
    const MODULES_BY_GOAL: Record<string, string[]> = {
        fitmax: ['Workout plan', 'Nutrition basics', 'Cardio protocol'],
        bonemax: ['Mewing fundamentals', 'Jawline exercises', 'Posture stack'],
        heightmax: ['Spine decompression', 'Stretch routine', 'Growth safety'],
        skinmax: ['Morning routine', 'Night routine', 'Acne protocol'],
        hairmax: ['Wash routine', 'Topicals & meds', 'Microneedling plan'],
    };

    // Map goal IDs to possible course categories (RDS may use different names)
    const GOAL_TO_CATEGORIES: Record<string, string[]> = {
        bonemax: ['bonemax', 'mewing', 'jawline', 'posture'],
        fitmax: ['fitmax', 'fat_loss'],
        heightmax: ['heightmax'],
        skinmax: ['skinmax', 'skincare'],
        hairmax: ['hairmax', 'hair'],
    };

    // Map each goal to its corresponding course and find progress if any
    const activeMaxxes = selectedGoals.map(goalId => {
        const categories = GOAL_TO_CATEGORIES[goalId?.toLowerCase()] || [goalId?.toLowerCase()];
        const course = courses.find(c => {
            const cat = (c.category || '').toLowerCase();
            return categories.includes(cat) || c.id === goalId;
        });
        if (!course) return null;
        const prog = progress.find(p => p.course_id === course.id);
        return { course, progress: prog, goalId };
    }).filter(Boolean) as { course: any, progress: any, goalId: string }[];

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
                                    {user?.profile?.avatar_url ? (
                                        <Image
                                            source={{ uri: api.resolveAttachmentUrl(user.profile.avatar_url) }}
                                            style={styles.profileAvatar}
                                        />
                                    ) : (
                                        <Text style={styles.profileInitial}>{(user?.first_name?.charAt(0) || user?.email?.charAt(0) || 'U').toUpperCase()}</Text>
                                    )}
                                </View>
                            </TouchableOpacity>
                        </View>
                    </View>

                    <View style={styles.section}>
                        <View style={styles.sectionHeader}>
                            <Text style={styles.sectionLabel}>MY ACTIVE MAXXES</Text>
                            {activeMaxxes.length > 0 && <Text style={styles.sectionCount}>{activeMaxxes.length}</Text>}
                        </View>

                        {activeMaxxes.map((item, i) => {
                            const p = item.progress;
                            const c = item.course;
                            const modules = MODULES_BY_GOAL[item.goalId?.toLowerCase()] || [];
                            return (
                                <TouchableOpacity key={c.id} style={styles.courseCard} onPress={() => navigation.navigate('CourseDetail', { courseId: c.id })} activeOpacity={0.7}>
                                    <View style={styles.courseRow}>
                                        <View style={styles.courseIcon}>
                                            <Ionicons name={i % 2 === 0 ? "book-outline" : "water-outline"} size={16} color={colors.textSecondary} />
                                        </View>
                                        <View style={styles.courseContent}>
                                            <Text style={styles.courseTitle} numberOfLines={1}>{c.title}</Text>

                                            {p ? (
                                                <View style={styles.progressRow}>
                                                    <View style={styles.progressBar}>
                                                        <View style={[styles.progressFill, { width: `${Math.round(p.progress_percentage || 0)}%` }]} />
                                                    </View>
                                                    <Text style={styles.coursePercent}>{Math.round(p.progress_percentage || 0)}%</Text>
                                                </View>
                                            ) : (
                                                <Text style={[styles.emptyDesc, { fontSize: 12, marginBottom: 0, textAlign: 'left' }]}>Tap to start maxxing</Text>
                                            )}

                                            {modules.length > 0 && (
                                                <View style={styles.moduleRow}>
                                                    {modules.map((m) => (
                                                        <View key={m} style={styles.modulePill}>
                                                            <Text style={styles.moduleText}>{m}</Text>
                                                        </View>
                                                    ))}
                                                </View>
                                            )}
                                        </View>
                                        <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                                    </View>
                                </TouchableOpacity>
                            );
                        })}

                        {activeMaxxes.length === 0 && (
                            <TouchableOpacity style={styles.emptyCard} onPress={() => navigation.navigate('EditPersonal', { onlyGoals: true })} activeOpacity={0.7}>
                                <Text style={styles.emptyTitle}>No Maxxes active</Text>
                                <Text style={styles.emptyDesc}>Select a max goal in your profile to begin.</Text>
                                <View style={styles.emptyButton}>
                                    <Text style={styles.emptyButtonText}>Select Goals</Text>
                                </View>
                            </TouchableOpacity>
                        )}

                        {activeMaxxes.length > 0 && (
                            <TouchableOpacity style={[styles.emptyButton, { marginTop: spacing.md, alignSelf: 'center' }]} onPress={() => navigation.navigate('EditPersonal', { onlyGoals: true })} activeOpacity={0.7}>
                                <Text style={styles.emptyButtonText}>Add More Maxxes</Text>
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
    profileAvatar: { width: 40, height: 40, borderRadius: 20 },
    profileInitial: { fontSize: 16, fontWeight: '600', color: colors.buttonText },
    section: { paddingHorizontal: spacing.lg, marginTop: spacing.md },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
    sectionLabel: { ...typography.label },
    sectionCount: {
        fontSize: 11, fontWeight: '600', color: colors.textSecondary,
        backgroundColor: colors.surface,
        paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10,
    },
    courseCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        paddingVertical: spacing.xl,
        paddingHorizontal: spacing.lg,
        marginBottom: spacing.md,
        ...shadows.md,
    },
    courseRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    courseIcon: {
        width: 48, height: 48, borderRadius: borderRadius.md,
        backgroundColor: colors.surface,
        alignItems: 'center', justifyContent: 'center',
    },
    courseContent: { flex: 1 },
    courseTitle: { fontSize: 18, fontWeight: '700', color: colors.foreground, marginBottom: 8 },
    progressRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    progressBar: { flex: 1, height: 6, backgroundColor: colors.borderLight, borderRadius: 3, overflow: 'hidden' },
    progressFill: { height: '100%', backgroundColor: colors.foreground, borderRadius: 3 },
    coursePercent: { fontSize: 13, fontWeight: '500', color: colors.textMuted, width: 40, textAlign: 'right' },
    moduleRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: spacing.xs,
        marginTop: spacing.sm,
    },
    modulePill: {
        paddingHorizontal: spacing.sm,
        paddingVertical: 4,
        borderRadius: 999,
        backgroundColor: colors.surface,
    },
    moduleText: {
        fontSize: 11,
        fontWeight: '500',
        color: colors.textSecondary,
    },
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
