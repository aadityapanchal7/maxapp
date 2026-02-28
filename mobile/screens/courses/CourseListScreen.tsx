import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, Image, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function CourseListScreen() {
    const navigation = useNavigation<any>();
    const [courses, setCourses] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadCourses(); }, []);
    const loadCourses = async () => { try { const result = await api.getCourses(); setCourses(result.courses || []); } catch (e) { console.error(e); } finally { setLoading(false); } };

    const renderItem = ({ item }: { item: any }) => (
        <TouchableOpacity style={styles.courseCard} onPress={() => navigation.navigate('CourseDetail', { courseId: item.id })}>
            <Image source={{ uri: item.thumbnail_url || 'https://via.placeholder.com/300' }} style={styles.thumbnail} />
            <View style={styles.cardContent}>
                <View style={styles.badgeContainer}>
                    <View style={[styles.badge, styles.categoryBadge]}><Text style={styles.badgeText}>{item.category.toUpperCase()}</Text></View>
                    <View style={[styles.badge, styles.difficultyBadge]}><Text style={styles.badgeText}>{item.difficulty.toUpperCase()}</Text></View>
                </View>
                <Text style={styles.title}>{item.title}</Text>
                <Text style={styles.description} numberOfLines={2}>{item.description}</Text>
                <View style={styles.footer}>
                    <Text style={styles.duration}>{item.estimated_weeks} Weeks</Text>
                    <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                </View>
            </View>
        </TouchableOpacity>
    );

    if (loading) return <View style={[styles.container, styles.center]}><ActivityIndicator size="large" color={colors.primary} /></View>;

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}><Ionicons name="arrow-back" size={24} color={colors.textPrimary} /></TouchableOpacity>
                <Text style={styles.headerTitle}>All Courses</Text>
                <View style={{ width: 40 }} />
            </View>
            <FlatList data={courses} renderItem={renderItem} keyExtractor={(item) => item.id} contentContainerStyle={styles.list} showsVerticalScrollIndicator={false} />
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    center: { justifyContent: 'center', alignItems: 'center' },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.lg, paddingTop: 60, paddingBottom: spacing.md },
    backButton: { padding: spacing.xs },
    headerTitle: { ...typography.h3 },
    list: { padding: spacing.lg },
    courseCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, marginBottom: spacing.lg, overflow: 'hidden', ...shadows.sm },
    thumbnail: { width: '100%', height: 180, resizeMode: 'cover' },
    cardContent: { padding: spacing.md },
    badgeContainer: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
    badge: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 4 },
    categoryBadge: { backgroundColor: colors.accent },
    difficultyBadge: { backgroundColor: colors.textMuted },
    badgeText: { fontSize: 10, fontWeight: '700', color: colors.buttonText },
    title: { ...typography.h3, marginBottom: 4 },
    description: { ...typography.bodySmall, marginBottom: spacing.md },
    footer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    duration: { ...typography.caption, fontWeight: '700' },
});
