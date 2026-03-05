import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Alert, Animated } from 'react-native';
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

    const fadeAnim = useRef(new Animated.Value(0)).current;
    const slideAnim = useRef(new Animated.Value(20)).current;

    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
            Animated.timing(slideAnim, { toValue: 0, duration: 500, useNativeDriver: true }),
        ]).start();
    }, []);

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
        } catch (error) { Alert.alert('Error', 'Could not save onboarding data'); }
        finally { setLoading(false); }
    };

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
            <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>
                <View style={styles.header}>
                    <Text style={styles.stepLabel}>STEP 1 OF 2</Text>
                    <Text style={styles.title}>What are your goals?</Text>
                    <Text style={styles.subtitle}>Select all that apply</Text>
                </View>

                <View style={styles.goalsGrid}>
                    {GOALS.map((goal) => {
                        const selected = selectedGoals.includes(goal.id);
                        return (
                            <TouchableOpacity key={goal.id} style={[styles.goalCard, selected && styles.goalCardSelected]} onPress={() => toggleGoal(goal.id)} activeOpacity={0.7}>
                                <Ionicons name={goal.icon as any} size={20} color={selected ? colors.foreground : colors.textMuted} />
                                <Text style={[styles.goalLabel, selected && styles.goalLabelSelected]}>{goal.label}</Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>

                <View style={styles.divider} />

                <Text style={styles.sectionLabel}>EXPERIENCE LEVEL</Text>

                <View style={styles.experienceList}>
                    {EXPERIENCE.map((exp) => {
                        const selected = experience === exp.id;
                        return (
                            <TouchableOpacity key={exp.id} style={[styles.expCard, selected && styles.expCardSelected]} onPress={() => setExperience(exp.id)} activeOpacity={0.7}>
                                <View style={styles.expRow}>
                                    <View style={[styles.radio, selected && styles.radioSelected]}>
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

                <TouchableOpacity style={[styles.button, loading && { opacity: 0.5 }]} onPress={handleContinue} disabled={loading} activeOpacity={0.7}>
                    <Text style={styles.buttonText}>{loading ? 'Saving...' : 'Continue'}</Text>
                </TouchableOpacity>
            </Animated.View>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg, paddingTop: 80, paddingBottom: spacing.xxl },
    header: { marginBottom: spacing.xl },
    stepLabel: { ...typography.label, color: colors.textMuted, marginBottom: spacing.sm },
    title: { ...typography.h1, marginBottom: spacing.xs },
    subtitle: { ...typography.bodySmall },
    goalsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    goalCard: {
        width: '31%',
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        paddingVertical: spacing.md,
        alignItems: 'center',
        ...shadows.sm,
        gap: spacing.xs,
    },
    goalCardSelected: { backgroundColor: colors.accentMuted, ...shadows.md },
    goalLabel: { ...typography.caption, color: colors.textSecondary },
    goalLabelSelected: { color: colors.foreground, fontWeight: '600' },
    divider: { height: 1, backgroundColor: colors.borderLight, marginVertical: spacing.xl },
    sectionLabel: { ...typography.label, marginBottom: spacing.md },
    experienceList: { gap: spacing.sm, marginBottom: spacing.xl },
    expCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        ...shadows.sm,
    },
    expCardSelected: { backgroundColor: colors.accentMuted, ...shadows.md },
    expRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    radio: {
        width: 20, height: 20, borderRadius: 10,
        borderWidth: 2, borderColor: colors.border,
        alignItems: 'center', justifyContent: 'center',
    },
    radioSelected: { borderColor: colors.foreground },
    radioInner: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.foreground },
    expLabel: { ...typography.body, fontWeight: '600' },
    expLabelSelected: { color: colors.foreground },
    expDesc: { ...typography.caption, marginTop: 2 },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: 16,
        alignItems: 'center',
        ...shadows.md,
    },
    buttonText: { ...typography.button },
});
