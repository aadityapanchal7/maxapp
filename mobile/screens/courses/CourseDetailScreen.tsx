import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function CourseDetailScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { courseId } = route.params;

    const [course, setCourse] = useState<any>(null);
    const [progress, setProgress] = useState<any>(null); // user_course_progress
    const [loading, setLoading] = useState(true);
    const [joining, setJoining] = useState(false);

    // Expanded modules state (default all open or just current)
    const [expandedModules, setExpandedModules] = useState<{ [key: number]: boolean }>({ 1: true });

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const [courseData, progressData] = await Promise.all([
                api.getCourse(courseId),
                api.getCourseProgress() // Fetches all, we filter
            ]);

            setCourse(courseData);

            // Find progress for this course
            const myProgress = progressData.progress.find((p: any) => p.course_id === courseId);
            setProgress(myProgress || null);

            if (myProgress) {
                // Expand current module
                setExpandedModules(prev => ({ ...prev, [myProgress.current_module]: true }));
            }
        } catch (error) {
            console.error("Failed to load details", error);
        } finally {
            setLoading(false);
        }
    };

    const handleJoin = async () => {
        setJoining(true);
        try {
            await api.startCourse(courseId);
            loadData(); // Reload to get progress
        } catch (error) {
            Alert.alert("Error", "Could not start course");
        } finally {
            setJoining(false);
        }
    };

    const toggleModule = (moduleNum: number) => {
        setExpandedModules(prev => ({ ...prev, [moduleNum]: !prev[moduleNum] }));
    };

    const handleChapterPress = (chapter: any, moduleNum: number) => {
        if (!progress) {
            Alert.alert("Locked", "Please start the course first.");
            return;
        }

        // Navigation to content view
        navigation.navigate('ChapterView', {
            chapter,
            courseId,
            moduleNumber: moduleNum,
            isCompleted: progress.completed_chapters.includes(chapter.chapter_id)
        });
    };

    if (loading) {
        return (
            <View style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color={colors.primary} />
            </View>
        );
    }

    if (!course) {
        return (
            <View style={[styles.container, styles.center]}>
                <Ionicons name="alert-circle" size={48} color={colors.error} />
                <Text style={{ color: colors.textPrimary, marginTop: 10 }}>Failed to load course details</Text>
                <TouchableOpacity onPress={loadData} style={{ marginTop: 20, padding: 10, backgroundColor: colors.surfaceLight, borderRadius: 8 }}>
                    <Text style={{ color: colors.primary }}>Retry</Text>
                </TouchableOpacity>
            </View>
        );
    }

    const isStarted = !!progress;
    const completedChapters = progress?.completed_chapters || [];

    return (
        <ScrollView style={styles.container}>
            <Image source={{ uri: course.thumbnail_url }} style={styles.headerImage} />
            <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                <Ionicons name="arrow-back" size={24} color={colors.textPrimary} />
            </TouchableOpacity>

            <View style={styles.content}>
                <View style={styles.titleRow}>
                    <Text style={styles.title}>{course.title}</Text>
                    {isStarted && (
                        <View style={styles.progressBadge}>
                            <Text style={styles.progressText}>{Math.round(progress.progress_percentage)}%</Text>
                        </View>
                    )}
                </View>

                <Text style={styles.description}>{course.description}</Text>

                {!isStarted && (
                    <TouchableOpacity
                        style={styles.joinButton}
                        onPress={handleJoin}
                        disabled={joining}
                    >
                        {joining ? <ActivityIndicator color="#000" /> : <Text style={styles.joinText}>Start Course</Text>}
                    </TouchableOpacity>
                )}

                <Text style={styles.sectionTitle}>Modules</Text>

                {course.modules.map((mod: any) => (
                    <View key={mod.module_number} style={styles.moduleCard}>
                        <TouchableOpacity
                            style={styles.moduleHeader}
                            onPress={() => toggleModule(mod.module_number)}
                        >
                            <View style={styles.moduleInfo}>
                                <Text style={styles.moduleNum}>MODULE {mod.module_number}</Text>
                                <Text style={styles.moduleTitle}>{mod.title}</Text>
                            </View>
                            <Ionicons
                                name={expandedModules[mod.module_number] ? "chevron-up" : "chevron-down"}
                                size={20}
                                color={colors.textMuted}
                            />
                        </TouchableOpacity>

                        {expandedModules[mod.module_number] && (
                            <View style={styles.chapterList}>
                                {mod.chapters.map((chap: any, idx: number) => {
                                    const isDone = completedChapters.includes(chap.chapter_id);
                                    return (
                                        <TouchableOpacity
                                            key={chap.chapter_id}
                                            style={[styles.chapterItem, isDone && styles.chapterDone]}
                                            onPress={() => handleChapterPress(chap, mod.module_number)}
                                        >
                                            <View style={styles.chapterLeft}>
                                                <Ionicons
                                                    name={isDone ? "checkmark-circle" : (
                                                        chap.type === 'video' ? 'play-circle' :
                                                            chap.type === 'image' ? 'image' : 'document-text'
                                                    )}
                                                    size={24}
                                                    color={isDone ? colors.success : colors.primary}
                                                />
                                                <View>
                                                    <Text style={[styles.chapterTitle, isDone && styles.textDone]}>{chap.title}</Text>
                                                    <Text style={styles.chapterDuration}>{chap.duration_minutes} min</Text>
                                                </View>
                                            </View>
                                            {isDone && <Text style={styles.doneLabel}>Done</Text>}
                                        </TouchableOpacity>
                                    );
                                })}
                            </View>
                        )}
                    </View>
                ))}
            </View>
            <View style={{ height: 40 }} />
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    center: { justifyContent: 'center', alignItems: 'center' },
    headerImage: { width: '100%', height: 250, resizeMode: 'cover' },
    backButton: { position: 'absolute', top: 60, left: 20, width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center' },
    content: { padding: spacing.lg },
    titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
    title: { ...typography.h2, flex: 1 },
    progressBadge: { backgroundColor: colors.primary, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12 },
    progressText: { ...typography.caption, fontWeight: '700', color: colors.background },
    description: { ...typography.body, color: colors.textSecondary, marginBottom: spacing.xl },
    joinButton: { backgroundColor: colors.primary, padding: spacing.md, borderRadius: borderRadius.md, alignItems: 'center', marginBottom: spacing.xl },
    joinText: { ...typography.button, color: '#000' },
    sectionTitle: { ...typography.h3, marginBottom: spacing.md },
    moduleCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, marginBottom: spacing.md, overflow: 'hidden' },
    moduleHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: spacing.md, backgroundColor: colors.surfaceLight },
    moduleInfo: { flex: 1 },
    moduleNum: { fontSize: 10, fontWeight: '700', color: colors.textMuted, marginBottom: 2 },
    moduleTitle: { ...typography.body, fontWeight: '700' },
    chapterList: { padding: spacing.sm },
    chapterItem: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: spacing.md, borderRadius: borderRadius.md, marginBottom: 4 },
    chapterDone: { backgroundColor: 'rgba(52, 199, 89, 0.1)' },
    chapterLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, flex: 1 },
    chapterTitle: { ...typography.body, fontWeight: '500' },
    chapterDuration: { ...typography.caption, color: colors.textMuted },
    textDone: { color: colors.textSecondary, textDecorationLine: 'line-through' },
    doneLabel: { ...typography.caption, color: colors.success, fontWeight: '700' }
});
