import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { CachedImage } from '../../components/CachedImage';

export default function CourseListScreen() {
    const navigation = useNavigation<any>();
    const [courses, setCourses] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => { loadCourses(); }, []);
    const loadCourses = async () => { try { const result = await api.getCourses(); setCourses(result.courses || []); } catch (e) { console.error(e); } finally { setLoading(false); } };

    const renderItem = ({ item }: { item: any }) => (
        <TouchableOpacity style={styles.courseCard} onPress={() => navigation.navigate('CourseDetail', { courseId: item.id })} activeOpacity={0.7}>
            <CachedImage uri={item.thumbnail_url || 'https://via.placeholder.com/300'} style={styles.thumbnail} />
            <View style={styles.cardContent}>
                <View style={styles.badgeContainer}>
                    <View style={styles.badge}><Text style={styles.badgeText}>{item.category.toUpperCase()}</Text></View>
                    <View style={[styles.badge, styles.badgeOutline]}><Text style={styles.badgeOutlineText}>{item.difficulty.toUpperCase()}</Text></View>
                </View>
                <Text style={styles.title}>{item.title}</Text>
                <Text style={styles.description} numberOfLines={2}>{item.description}</Text>
                <View style={styles.footer}>
                    <Text style={styles.duration}>{item.estimated_weeks} weeks</Text>
                    <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                </View>
            </View>
        </TouchableOpacity>
    );

    if (loading) return <View style={[styles.container, styles.center]}><ActivityIndicator size="large" color={colors.foreground} /></View>;

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}><Ionicons name="arrow-back" size={22} color={colors.foreground} /></TouchableOpacity>
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
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.lg, paddingTop: 64, paddingBottom: spacing.md },
    backButton: { padding: spacing.xs },
    headerTitle: { ...typography.h3 },
    list: { padding: spacing.lg },
    courseCard: {
        backgroundColor: colors.card, borderRadius: borderRadius['2xl'],
        marginBottom: spacing.lg, overflow: 'hidden',
        ...shadows.md,
    },
    thumbnail: { width: '100%', height: 180, resizeMode: 'cover' },
    cardContent: { padding: spacing.md },
    badgeContainer: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
    badge: { paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: borderRadius.full, backgroundColor: colors.foreground },
    badgeText: { fontSize: 10, fontWeight: '600', color: colors.buttonText, letterSpacing: 0.5 },
    badgeOutline: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.border },
    badgeOutlineText: { fontSize: 10, fontWeight: '600', color: colors.textSecondary, letterSpacing: 0.5 },
    title: { fontSize: 16, fontWeight: '600', color: colors.foreground, marginBottom: 4 },
    description: { fontSize: 13, color: colors.textSecondary, marginBottom: spacing.md, lineHeight: 18 },
    footer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    duration: { fontSize: 12, fontWeight: '600', color: colors.textMuted, letterSpacing: 0.3 },
});
