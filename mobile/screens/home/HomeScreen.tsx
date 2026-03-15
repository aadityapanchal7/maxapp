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
    const [maxes, setMaxes] = useState<any[]>([]);
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
            const res = await api.getMaxxes();
            setMaxes(res.maxes || []);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const userName = user?.first_name || user?.email?.split('@')[0] || 'there';
    const selectedGoals: string[] = (user?.onboarding?.goals || []).map((g: string) => g.toLowerCase());

    // Filter maxes from RDS down to only the ones the user selected
    const activeMaxxes = maxes.filter(m => selectedGoals.includes(m.id?.toLowerCase()));

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

                        {activeMaxxes.map((maxx) => {
                            const moduleTitles: string[] = (maxx.modules || []).map((m: any) => m.title);
                            return (
                                <TouchableOpacity
                                    key={maxx.id}
                                    style={styles.courseCard}
                                    onPress={() => navigation.navigate('MaxxDetail', { maxxId: maxx.id })}
                                    activeOpacity={0.7}
                                >
                                    <View style={styles.courseRow}>
                                        <View style={[styles.courseIcon, maxx.color ? { backgroundColor: maxx.color + '22' } : {}]}>
                                            <Ionicons name={(maxx.icon || 'book-outline') as any} size={20} color={maxx.color || colors.textSecondary} />
                                        </View>
                                        <View style={styles.courseContent}>
                                            <Text style={styles.courseTitle} numberOfLines={1}>{maxx.label}</Text>
                                            <Text style={[styles.emptyDesc, { fontSize: 12, marginBottom: 6, textAlign: 'left' }]} numberOfLines={2}>{maxx.description}</Text>
                                            {moduleTitles.length > 0 && (
                                                <View style={styles.moduleRow}>
                                                    {moduleTitles.map((t) => (
                                                        <View key={t} style={styles.modulePill}>
                                                            <Text style={styles.moduleText}>{t}</Text>
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
