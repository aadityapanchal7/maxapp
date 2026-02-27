/**
 * Onboarding Screen - Goals questionnaire
 */

import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

const GOALS = [
    { id: 'jawline', label: 'Jawline Definition', icon: 'fitness' },
    { id: 'fat_loss', label: 'Facial Fat Loss', icon: 'body' },
    { id: 'skin', label: 'Better Skin', icon: 'sparkles' },
    { id: 'posture', label: 'Posture Improvement', icon: 'walk' },
    { id: 'symmetry', label: 'Facial Symmetry', icon: 'grid' },
    { id: 'hair', label: 'Hair Optimization', icon: 'cut' },
];

const EXPERIENCE = [
    { id: 'beginner', label: 'Beginner', desc: 'New to lookmaxxing' },
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
        setSelectedGoals((prev) =>
            prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id]
        );
    };

    const handleContinue = async () => {
        if (selectedGoals.length === 0) {
            Alert.alert('Select Goals', 'Please select at least one goal');
            return;
        }
        if (!experience) {
            Alert.alert('Select Experience', 'Please select your experience level');
            return;
        }

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
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
            <Text style={styles.title}>What are your goals?</Text>
            <Text style={styles.subtitle}>Select all that apply</Text>

            <View style={styles.goalsGrid}>
                {GOALS.map((goal) => (
                    <TouchableOpacity
                        key={goal.id}
                        style={[styles.goalCard, selectedGoals.includes(goal.id) && styles.goalCardSelected]}
                        onPress={() => toggleGoal(goal.id)}
                    >
                        <Ionicons name={goal.icon as any} size={28} color={selectedGoals.includes(goal.id) ? colors.primary : colors.textSecondary} />
                        <Text style={[styles.goalLabel, selectedGoals.includes(goal.id) && styles.goalLabelSelected]}>{goal.label}</Text>
                    </TouchableOpacity>
                ))}
            </View>

            <Text style={[styles.title, { marginTop: spacing.xl }]}>Experience Level</Text>

            <View style={styles.experienceList}>
                {EXPERIENCE.map((exp) => (
                    <TouchableOpacity
                        key={exp.id}
                        style={[styles.expCard, experience === exp.id && styles.expCardSelected]}
                        onPress={() => setExperience(exp.id)}
                    >
                        <Text style={[styles.expLabel, experience === exp.id && styles.expLabelSelected]}>{exp.label}</Text>
                        <Text style={styles.expDesc}>{exp.desc}</Text>
                    </TouchableOpacity>
                ))}
            </View>

            <TouchableOpacity style={styles.button} onPress={handleContinue} disabled={loading}>
                <Text style={styles.buttonText}>{loading ? 'Saving...' : 'Continue'}</Text>
            </TouchableOpacity>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg, paddingTop: 60 },
    title: { ...typography.h2, marginBottom: spacing.xs },
    subtitle: { ...typography.bodySmall, marginBottom: spacing.lg },
    goalsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
    goalCard: { width: '47%', backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, alignItems: 'center', borderWidth: 2, borderColor: colors.border },
    goalCardSelected: { borderColor: colors.primary, backgroundColor: colors.surfaceLight },
    goalLabel: { ...typography.bodySmall, marginTop: spacing.sm, textAlign: 'center' },
    goalLabelSelected: { color: colors.primary },
    experienceList: { gap: spacing.md, marginBottom: spacing.xl },
    expCard: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.md, borderWidth: 2, borderColor: colors.border },
    expCardSelected: { borderColor: colors.primary },
    expLabel: { ...typography.body, fontWeight: '600' },
    expLabelSelected: { color: colors.primary },
    expDesc: { ...typography.caption, marginTop: 4 },
    button: { backgroundColor: colors.primary, borderRadius: borderRadius.md, padding: spacing.md, alignItems: 'center' },
    buttonText: { ...typography.button },
});
