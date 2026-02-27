import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, Image, TouchableOpacity, ActivityIndicator } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

export default function CourseListScreen() {
    const navigation = useNavigation<any>();
    const [courses, setCourses] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadCourses();
    }, []);

    const loadCourses = async () => {
        try {
            const result = await api.getCourses();
            setCourses(result.courses || []);
        } catch (error) {
            console.error("Failed to load courses", error);
        } finally {
            setLoading(false);
        }
    };

    const renderItem = ({ item }: { item: any }) => (
        <TouchableOpacity
            style={styles.courseCard}
            onPress={() => navigation.navigate('CourseDetail', { courseId: item.id })}
        >
            <Image
                source={{ uri: item.thumbnail_url || 'https://via.placeholder.com/300' }}
                style={styles.thumbnail}
            />
            <View style={styles.cardContent}>
                <View style={styles.badgeContainer}>
                    <View style={[styles.badge, styles.categoryBadge]}>
                        <Text style={styles.badgeText}>{item.category.toUpperCase()}</Text>
                    </View>
                    <View style={[styles.badge, styles.difficultyBadge]}>
                        <Text style={styles.badgeText}>{item.difficulty.toUpperCase()}</Text>
                    </View>
                </View>
                <Text style={styles.title}>{item.title}</Text>
                <Text style={styles.description} numberOfLines={2}>{item.description}</Text>
                <View style={styles.footer}>
                    <Text style={styles.duration}>{item.estimated_weeks} Weeks</Text>
                    <Ionicons name="chevron-forward" size={20} color="#FFFFFF" />
                </View>
            </View>
        </TouchableOpacity>
    );

    if (loading) {
        return (
            <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={[styles.container, styles.center]}>
                <ActivityIndicator size="large" color="#FFFFFF" />
            </LinearGradient>
        );
    }

    return (
        <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
            <View style={styles.header}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
                    <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
                </TouchableOpacity>
                <Text style={styles.headerTitle}>All Courses</Text>
                <View style={{ width: 40 }} />
            </View>

            <FlatList
                data={courses}
                renderItem={renderItem}
                keyExtractor={(item) => item.id}
                contentContainerStyle={styles.list}
                showsVerticalScrollIndicator={false}
            />
        </LinearGradient>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1 },
    center: { justifyContent: 'center', alignItems: 'center' },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.lg, paddingTop: 60, paddingBottom: spacing.md },
    backButton: { padding: spacing.xs },
    headerTitle: { ...typography.h3, color: '#FFFFFF' },
    list: { padding: spacing.lg },
    courseCard: { backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: borderRadius.lg, marginBottom: spacing.lg, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
    thumbnail: { width: '100%', height: 180, resizeMode: 'cover' },
    cardContent: { padding: spacing.md },
    badgeContainer: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
    badge: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 4 },
    categoryBadge: { backgroundColor: 'rgba(255,255,255,0.2)' },
    difficultyBadge: { backgroundColor: 'rgba(255,255,255,0.1)' },
    badgeText: { fontSize: 10, fontWeight: '700', color: '#FFFFFF' },
    title: { ...typography.h3, marginBottom: 4, color: '#FFFFFF' },
    description: { ...typography.bodySmall, color: 'rgba(255,255,255,0.7)', marginBottom: spacing.md },
    footer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    duration: { ...typography.caption, color: '#FFFFFF', fontWeight: '700' },
});

