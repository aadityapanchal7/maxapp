import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function CourseDetailScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { courseId } = route.params;
    const [course, setCourse] = useState<any>(null);
    const [progress, setProgress] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [joining, setJoining] = useState(false);
    const [expandedModules, setExpandedModules] = useState<{ [key: number]: boolean }>({ 1: true });

    useEffect(() => { loadData(); }, []);

    const loadData = async () => {
        try {
            const [courseData, progressData] = await Promise.all([api.getCourse(courseId), api.getCourseProgress()]);
            setCourse(courseData);
            const myProgress = progressData.progress.find((p: any) => p.course_id === courseId);
            setProgress(myProgress || null);
            if (myProgress) setExpandedModules(prev => ({ ...prev, [myProgress.current_module]: true }));
        } catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const handleJoin = async () => { setJoining(true); try { await api.startCourse(courseId); loadData(); } catch (e) { Alert.alert("Error", "Could not start course"); } finally { setJoining(false); } };
    const toggleModule = (moduleNum: number) => { setExpandedModules(prev => ({ ...prev, [moduleNum]: !prev[moduleNum] })); };
    const handleChapterPress = (chapter: any, moduleNum: number) => {
        if (!progress) { Alert.alert("Locked", "Please start the course first."); return; }
        navigation.navigate('ChapterView', { chapter, courseId, moduleNumber: moduleNum, isCompleted: progress.completed_chapters.includes(chapter.chapter_id) });
    };

    if (loading) return <View style={[styles.container, styles.center]}><ActivityIndicator size="large" color={colors.foreground} /></View>;
    if (!course) return <View style={[styles.container, styles.center]}><Text style={{ color: colors.foreground, marginBottom: 10 }}>Failed to load course</Text><TouchableOpacity onPress={loadData} style={{ padding: 10, backgroundColor: colors.surface, borderRadius: 8 }}><Text style={{ color: colors.foreground }}>Retry</Text></TouchableOpacity></View>;

    const isStarted = !!progress;
    const completedChapters = progress?.completed_chapters || [];

    return (
        <ScrollView style={styles.container}>
            <Image source={{ uri: course.thumbnail_url }} style={styles.headerImage} />
            <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}><Ionicons name="arrow-back" size={22} color="#fff" /></TouchableOpacity>

            <View style={styles.content}>
                <View style={styles.titleRow}>
                    <Text style={styles.title}>{course.title}</Text>
                    {isStarted && <View style={styles.progressBadge}><Text style={styles.progressText}>{Math.round(progress.progress_percentage)}%</Text></View>}
                </View>
                <Text style={styles.description}>{course.description}</Text>

                {!isStarted && (
                    <TouchableOpacity style={styles.joinButton} onPress={handleJoin} disabled={joining} activeOpacity={0.7}>
                        {joining ? <ActivityIndicator color={colors.buttonText} /> : <Text style={styles.joinText}>Start Course</Text>}
                    </TouchableOpacity>
                )}

                {isStarted && (
                    <TouchableOpacity
                        style={styles.scheduleButton}
                        onPress={() => navigation.navigate('Schedule', {
                            courseId,
                            moduleNumber: progress?.current_module || 1,
                            courseTitle: course.title,
                        })}
                        activeOpacity={0.7}
                    >
                        <Ionicons name="calendar-outline" size={18} color={colors.foreground} />
                        <Text style={styles.scheduleButtonText}>View AI Schedule</Text>
                        <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
                    </TouchableOpacity>
                )}

                <Text style={styles.sectionLabel}>MODULES</Text>

                {course.modules.map((mod: any) => (
                    <View key={mod.module_number} style={styles.moduleCard}>
                        <TouchableOpacity style={styles.moduleHeader} onPress={() => toggleModule(mod.module_number)} activeOpacity={0.7}>
                            <View style={styles.moduleInfo}>
                                <Text style={styles.moduleNum}>MODULE {mod.module_number}</Text>
                                <Text style={styles.moduleTitle}>{mod.title}</Text>
                            </View>
                            <Ionicons name={expandedModules[mod.module_number] ? "chevron-up" : "chevron-down"} size={18} color={colors.textMuted} />
                        </TouchableOpacity>

                        {expandedModules[mod.module_number] && (
                            <View style={styles.chapterList}>
                                {mod.chapters.map((chap: any) => {
                                    const isDone = completedChapters.includes(chap.chapter_id);
                                    return (
                                        <TouchableOpacity key={chap.chapter_id} style={[styles.chapterItem, isDone && styles.chapterDone]} onPress={() => handleChapterPress(chap, mod.module_number)} activeOpacity={0.7}>
                                            <View style={styles.chapterLeft}>
                                                <Ionicons name={isDone ? "checkmark-circle" : (chap.type === 'video' ? 'play-circle' : chap.type === 'image' ? 'image' : 'document-text')} size={20} color={isDone ? colors.foreground : colors.textSecondary} />
                                                <View><Text style={[styles.chapterTitle, isDone && styles.textDone]}>{chap.title}</Text><Text style={styles.chapterDuration}>{chap.duration_minutes} min</Text></View>
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
    headerImage: { width: '100%', height: 240, resizeMode: 'cover' },
    backButton: { position: 'absolute', top: 60, left: 20, width: 36, height: 36, borderRadius: 18, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'center', alignItems: 'center' },
    content: { padding: spacing.lg },
    titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
    title: { ...typography.h2, flex: 1 },
    progressBadge: { backgroundColor: colors.foreground, paddingHorizontal: 10, paddingVertical: 4, borderRadius: borderRadius.full },
    progressText: { fontSize: 11, fontWeight: '700', color: colors.buttonText },
    description: { fontSize: 14, color: colors.textSecondary, marginBottom: spacing.xl, lineHeight: 20 },
    joinButton: { backgroundColor: colors.foreground, padding: spacing.md, borderRadius: borderRadius.full, alignItems: 'center', marginBottom: spacing.xl, ...shadows.md },
    joinText: { ...typography.button },
    scheduleButton: {
        flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
        backgroundColor: colors.card, padding: spacing.md, borderRadius: borderRadius.lg,
        marginBottom: spacing.xl, ...shadows.sm,
    },
    scheduleButtonText: { flex: 1, fontSize: 14, fontWeight: '600' as const, color: colors.foreground },
    sectionLabel: { ...typography.label, marginBottom: spacing.md },
    moduleCard: {
        backgroundColor: colors.card, borderRadius: borderRadius['2xl'],
        marginBottom: spacing.md, overflow: 'hidden',
        ...shadows.sm,
    },
    moduleHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: spacing.md, backgroundColor: colors.surface },
    moduleInfo: { flex: 1 },
    moduleNum: { fontSize: 10, fontWeight: '700', color: colors.textMuted, letterSpacing: 1, marginBottom: 2 },
    moduleTitle: { fontSize: 14, fontWeight: '600', color: colors.foreground },
    chapterList: { padding: spacing.sm },
    chapterItem: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: spacing.md, borderRadius: borderRadius.md, marginBottom: 4 },
    chapterDone: { backgroundColor: colors.accentMuted },
    chapterLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, flex: 1 },
    chapterTitle: { fontSize: 14, fontWeight: '500', color: colors.foreground },
    chapterDuration: { fontSize: 11, color: colors.textMuted, marginTop: 1 },
    textDone: { color: colors.textSecondary, textDecorationLine: 'line-through' },
    doneLabel: { fontSize: 11, color: colors.foreground, fontWeight: '600' },
});
