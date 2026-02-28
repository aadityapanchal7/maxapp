import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const GOALS = [
    { id: 'jawline', label: 'Jawline', icon: 'fitness' },
    { id: 'fat_loss', label: 'Fat Loss', icon: 'body' },
    { id: 'skin', label: 'Skin', icon: 'sparkles' },
    { id: 'posture', label: 'Posture', icon: 'walk' },
    { id: 'symmetry', label: 'Symmetry', icon: 'grid' },
    { id: 'hair', label: 'Hair', icon: 'cut' },
];

const EXPERIENCE = [
    { id: 'beginner', label: 'Beginner', desc: 'Just getting started' },
    { id: 'intermediate', label: 'Intermediate', desc: 'Some experience' },
    { id: 'advanced', label: 'Advanced', desc: 'Experienced practitioner' },
];

export default function OnboardingScreen() {
    const navigation = useNavigation<any>();
    const { refreshUser } = useAuth();
    const [selectedGoals, setSelectedGoals] = useState<string[]>([]);
    const [experience, setExperience] = useState('');
    const [loading, setLoading] = useState(false);

    const toggleGoal = (id: string) => {
        setSelectedGoals((prev) => prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id]);
    };

    const handleContinue = async () => {
        if (selectedGoals.length === 0) { Alert.alert('Select Goals', 'Please select at least one goal'); return; }
        if (!experience) { Alert.alert('Select Experience', 'Please select your experience level'); return; }
        setLoading(true);
        try {
            await api.saveOnboarding({ goals: selectedGoals, experience_level: experience });
            await refreshUser();
            navigation.navigate('FeaturesIntro');
        } catch (error) {
            Alert.alert('Error', 'Could not save onboarding data');
        } finally {
            setLoading(false);
        }
    };

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
            <View style={styles.header}>
                <Text style={styles.stepLabel}>STEP 1 OF 2</Text>
                <Text style={styles.title}>What are your goals?</Text>
                <Text style={styles.subtitle}>Select all that apply</Text>
            </View>

            <View style={styles.goalsGrid}>
                {GOALS.map((goal) => {
                    const selected = selectedGoals.includes(goal.id);
                    return (
                        <TouchableOpacity
                            key={goal.id}
                            style={[styles.goalCard, selected && styles.goalCardSelected]}
                            onPress={() => toggleGoal(goal.id)}
                            activeOpacity={0.8}
                        >
                            <View style={[styles.goalIcon, selected && styles.goalIconSelected]}>
                                <Ionicons name={goal.icon as any} size={22} color={selected ? colors.accent : colors.textMuted} />
                            </View>
                            <Text style={[styles.goalLabel, selected && styles.goalLabelSelected]}>{goal.label}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>

            <View style={styles.sectionDivider} />

            <Text style={styles.sectionTitle}>Experience Level</Text>

            <View style={styles.experienceList}>
                {EXPERIENCE.map((exp) => {
                    const selected = experience === exp.id;
                    return (
                        <TouchableOpacity
                            key={exp.id}
                            style={[styles.expCard, selected && styles.expCardSelected]}
                            onPress={() => setExperience(exp.id)}
                            activeOpacity={0.8}
                        >
                            <View style={styles.expRow}>
                                <View style={[styles.radioOuter, selected && styles.radioOuterSelected]}>
                                    {selected && <View style={styles.radioInner} />}
                                </View>
                                <View>
                                    <Text style={[styles.expLabel, selected && styles.expLabelSelected]}>{exp.label}</Text>
                                    <Text style={styles.expDesc}>{exp.desc}</Text>
                                </View>
                            </View>
                        </TouchableOpacity>
                    );
                })}
            </View>

            <TouchableOpacity
                style={[styles.button, loading && { opacity: 0.6 }]}
                onPress={handleContinue}
                disabled={loading}
                activeOpacity={0.85}
            >
                <Text style={styles.buttonText}>{loading ? 'Saving...' : 'Continue'}</Text>
                <Ionicons name="arrow-forward" size={18} color={colors.buttonText} />
            </TouchableOpacity>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg, paddingTop: 60, paddingBottom: spacing.xxl },
    header: { marginBottom: spacing.xl },
    stepLabel: { ...typography.caption, letterSpacing: 2, textTransform: 'uppercase', color: colors.accent, marginBottom: spacing.sm, fontWeight: '600' },
    title: { ...typography.h1, marginBottom: spacing.xs },
    subtitle: { ...typography.bodySmall },
    goalsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    goalCard: {
        width: '31%',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        paddingVertical: spacing.md,
        alignItems: 'center',
        borderWidth: 1.5,
        borderColor: colors.border,
    },
    goalCardSelected: { borderColor: colors.accent, backgroundColor: colors.accentMuted },
    goalIcon: {
        width: 44, height: 44, borderRadius: 22,
        backgroundColor: colors.background,
        alignItems: 'center', justifyContent: 'center',
        marginBottom: spacing.xs,
    },
    goalIconSelected: { backgroundColor: 'rgba(184, 152, 110, 0.15)' },
    goalLabel: { ...typography.caption, fontWeight: '500', color: colors.textSecondary },
    goalLabelSelected: { color: colors.accent, fontWeight: '600' },
    sectionDivider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.xl },
    sectionTitle: { ...typography.h2, marginBottom: spacing.md },
    experienceList: { gap: spacing.sm, marginBottom: spacing.xl },
    expCard: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        padding: spacing.md,
        borderWidth: 1.5,
        borderColor: colors.border,
    },
    expCardSelected: { borderColor: colors.accent, backgroundColor: colors.accentMuted },
    expRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    radioOuter: {
        width: 20, height: 20, borderRadius: 10,
        borderWidth: 2, borderColor: colors.border,
        alignItems: 'center', justifyContent: 'center',
    },
    radioOuterSelected: { borderColor: colors.accent },
    radioInner: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.accent },
    expLabel: { ...typography.body, fontWeight: '600' },
    expLabelSelected: { color: colors.textPrimary },
    expDesc: { ...typography.caption, marginTop: 2 },
    button: {
        flexDirection: 'row',
        backgroundColor: colors.primary,
        borderRadius: borderRadius.md,
        paddingVertical: 16,
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        ...shadows.md,
    },
    buttonText: { ...typography.button },
});
