import React, { useState, useEffect, useRef } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    ScrollView,
    Alert,
    Animated,
    TextInput,
    KeyboardAvoidingView,
    Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const GOALS = [
    { id: 'bonemax', label: 'Bonemax', icon: 'fitness-outline' },
    { id: 'heightmax', label: 'Heightmax', icon: 'resize-outline' },
    { id: 'skinmax', label: 'Skinmax', icon: 'sparkles-outline' },
    { id: 'hairmax', label: 'Hairmax', icon: 'cut-outline' },
    { id: 'fitmax', label: 'Fitmax', icon: 'body-outline' },
];

const EXPERIENCE = [
    { id: 'beginner', label: 'Beginner', desc: 'Just getting started' },
    { id: 'intermediate', label: 'Intermediate', desc: 'Some experience' },
    { id: 'advanced', label: 'Advanced', desc: 'Experienced practitioner' },
];

const ACTIVITY_LEVELS = [
    { id: 'sedentary', label: 'Sedentary', desc: 'Little to no exercise' },
    { id: 'light', label: 'Light', desc: '1-3 days/week' },
    { id: 'moderate', label: 'Moderate', desc: '3-5 days/week' },
    { id: 'active', label: 'Active', desc: '6-7 days/week' },
];

const EQUIPMENT = [
    { id: 'none', label: 'None / Bodyweight', icon: 'hand-left' },
    { id: 'dumbbells', label: 'Dumbbells', icon: 'barbell' },
    { id: 'gym', label: 'Full Gym Access', icon: 'business' },
];

const SKIN_TYPES = [
    { id: 'oily', label: 'Oily' },
    { id: 'dry', label: 'Dry' },
    { id: 'combination', label: 'Combination' },
    { id: 'sensitive', label: 'Sensitive' },
];

const REQUIRED = ' · Required';

export default function OnboardingScreen() {
    const navigation = useNavigation<any>();
    const { user, refreshUser, isAuthenticated } = useAuth() as any;

    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [fieldError, setFieldError] = useState<string | null>(null);

    const [selectedGoals, setSelectedGoals] = useState<string[]>([]);
    const [gender, setGender] = useState('');
    const [age, setAge] = useState('');
    const [unitSystem, setUnitSystem] = useState<'metric' | 'imperial'>('metric');
    const [height, setHeight] = useState('');
    const [heightFt, setHeightFt] = useState('');
    const [heightIn, setHeightIn] = useState('');
    const [weight, setWeight] = useState('');
    const [activityLevel, setActivityLevel] = useState('');
    const [selectedEquipment, setSelectedEquipment] = useState<string[]>([]);
    const [experience, setExperience] = useState('');
    const [skinType, setSkinType] = useState('');

    const fadeAnim = useRef(new Animated.Value(0)).current;

    useEffect(() => {
        setFieldError(null);
        Animated.timing(fadeAnim, { toValue: 1, duration: 350, useNativeDriver: true }).start();
    }, [step]);

    const showError = (message: string) => {
        setFieldError(message);
        Alert.alert('Required', message);
    };

    const validateStep2 = (): boolean => {
        if (!gender.trim()) {
            showError('Please select your gender.');
            return false;
        }
        const ageNum = parseInt(age, 10);
        if (!age.trim() || isNaN(ageNum)) {
            showError('Please enter your age.');
            return false;
        }
        if (ageNum < 13 || ageNum > 120) {
            showError('Please enter an age between 13 and 120.');
            return false;
        }
        const weightNum = parseFloat(weight);
        if (!weight.trim() || isNaN(weightNum) || weightNum <= 0) {
            showError('Please enter a valid weight.');
            return false;
        }
        if (unitSystem === 'metric') {
            const heightNum = parseFloat(height);
            if (!height.trim() || isNaN(heightNum) || heightNum <= 0) {
                showError('Please enter a valid height in cm.');
                return false;
            }
        } else {
            const ft = parseInt(heightFt, 10) || 0;
            const inch = parseInt(heightIn, 10) || 0;
            if (ft <= 0 && inch <= 0) {
                showError('Please enter your height in feet and inches.');
                return false;
            }
        }
        return true;
    };

    const nextStep = () => {
        setFieldError(null);

        if (step === 1) {
            if (selectedGoals.length === 0) {
                showError('Please select at least one goal.');
                return;
            }
        }
        if (step === 2) {
            if (!validateStep2()) return;
        }
        if (step === 3) {
            if (!activityLevel) {
                showError('Please select your activity level.');
                return;
            }
            if (selectedEquipment.length === 0) {
                showError('Please select at least one equipment option.');
                return;
            }
        }
        if (step === 4) {
            if (!experience) {
                showError('Please select your experience level.');
                return;
            }
            if (!skinType) {
                showError('Please select your skin type.');
                return;
            }
        }

        if (step < 4) {
            Animated.timing(fadeAnim, { toValue: 0, duration: 180, useNativeDriver: true }).start(() => {
                setStep(step + 1);
            });
        } else {
            handleFinish();
        }
    };

    const prevStep = () => {
        setFieldError(null);
        if (step > 1) {
            Animated.timing(fadeAnim, { toValue: 0, duration: 180, useNativeDriver: true }).start(() => {
                setStep(step - 1);
            });
        }
    };

    const handleFinish = async () => {
        setLoading(true);
        setFieldError(null);

        let finalHeight = parseFloat(height) || 0;
        let finalWeight = parseFloat(weight) || 0;

        if (unitSystem === 'imperial') {
            const ft = parseInt(heightFt, 10) || 0;
            const inch = parseInt(heightIn, 10) || 0;
            finalHeight = ft * 30.48 + inch * 2.54;
            finalWeight = finalWeight * 0.453592;
        }

        try {
            const payload = {
                goals: selectedGoals,
                gender: gender.trim(),
                age: parseInt(age, 10),
                height: Math.round(finalHeight * 10) / 10,
                weight: Math.round(finalWeight * 10) / 10,
                activity_level: activityLevel,
                equipment: selectedEquipment,
                experience_level: experience,
                skin_type: skinType,
                unit_system: unitSystem,
                timezone: typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC',
                completed: true,
            };

            if (isAuthenticated) {
                await api.saveOnboarding(payload);
                await refreshUser();
                navigation.navigate('FeaturesIntro');
            } else {
                const res = await api.saveOnboardingAnonymous(payload);
                navigation.navigate('Login', { onboarding: res.data });
            }
        } catch (error) {
            setFieldError('Could not save. Please try again.');
            Alert.alert('Error', 'Could not save your profile. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const renderStepContent = () => {
        switch (step) {
            case 1:
                return (
                    <View style={styles.stepBlock}>
                        <Text style={styles.title}>What are your goals?</Text>
                        <Text style={styles.subtitle}>Select all the areas you want to optimize.</Text>
                        <Text style={styles.requiredLabel}>Goals{REQUIRED}</Text>
                        <View style={styles.goalsGrid}>
                            {GOALS.map((goal) => {
                                const selected = selectedGoals.includes(goal.id);
                                return (
                                    <TouchableOpacity
                                        key={goal.id}
                                        style={[styles.goalCard, selected && styles.goalCardSelected]}
                                        onPress={() => setSelectedGoals((prev) => (prev.includes(goal.id) ? prev.filter((g) => g !== goal.id) : [...prev, goal.id]))}
                                        activeOpacity={0.8}
                                    >
                                        <Ionicons name={goal.icon as any} size={26} color={selected ? colors.foreground : colors.textMuted} />
                                        <Text style={[styles.goalLabel, selected && styles.goalLabelSelected]}>{goal.label}</Text>
                                    </TouchableOpacity>
                                );
                            })}
                        </View>
                        {fieldError && step === 1 ? <Text style={styles.inlineError}>{fieldError}</Text> : null}
                    </View>
                );
            case 2:
                return (
                    <View style={styles.stepBlock}>
                        <Text style={styles.title}>Physical profile</Text>
                        <Text style={styles.subtitle}>Help Max tailor your plan.</Text>

                        <View style={styles.titleRow}>
                            <Text style={styles.requiredLabel}>Gender{REQUIRED}</Text>
                            <View style={styles.unitToggle}>
                                <TouchableOpacity onPress={() => setUnitSystem('metric')} style={[styles.unitBtn, unitSystem === 'metric' && styles.unitBtnActive]} activeOpacity={0.8}>
                                    <Text style={[styles.unitLabel, unitSystem === 'metric' && styles.unitLabelActive]}>Metric</Text>
                                </TouchableOpacity>
                                <TouchableOpacity onPress={() => setUnitSystem('imperial')} style={[styles.unitBtn, unitSystem === 'imperial' && styles.unitBtnActive]} activeOpacity={0.8}>
                                    <Text style={[styles.unitLabel, unitSystem === 'imperial' && styles.unitLabelActive]}>US</Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                        <View style={styles.chipRow}>
                            {['Male', 'Female', 'Other'].map((g) => (
                                <TouchableOpacity
                                    key={g}
                                    style={[styles.chip, gender === g && styles.chipSelected]}
                                    onPress={() => setGender(g)}
                                    activeOpacity={0.8}
                                >
                                    <Text style={[styles.chipText, gender === g && styles.chipTextSelected]}>{g}</Text>
                                </TouchableOpacity>
                            ))}
                        </View>

                        <Text style={styles.requiredLabel}>Age{REQUIRED}</Text>
                        <TextInput
                            style={[styles.input, !age.trim() && fieldError ? styles.inputError : undefined]}
                            placeholder="e.g. 25"
                            placeholderTextColor={colors.textMuted}
                            keyboardType="numeric"
                            value={age}
                            onChangeText={(t) => { setAge(t); setFieldError(null); }}
                        />

                        <Text style={styles.requiredLabel}>Weight ({unitSystem === 'metric' ? 'kg' : 'lbs'}){REQUIRED}</Text>
                        <TextInput
                            style={[styles.input, !weight.trim() && fieldError ? styles.inputError : undefined]}
                            placeholder={unitSystem === 'metric' ? 'e.g. 70' : 'e.g. 154'}
                            placeholderTextColor={colors.textMuted}
                            keyboardType="decimal-pad"
                            value={weight}
                            onChangeText={(t) => { setWeight(t); setFieldError(null); }}
                        />

                        <Text style={styles.requiredLabel}>Height ({unitSystem === 'metric' ? 'cm' : 'ft / in'}){REQUIRED}</Text>
                        {unitSystem === 'metric' ? (
                            <TextInput
                                style={[styles.input, !height.trim() && fieldError ? styles.inputError : undefined]}
                                placeholder="e.g. 175"
                                placeholderTextColor={colors.textMuted}
                                keyboardType="decimal-pad"
                                value={height}
                                onChangeText={(t) => { setHeight(t); setFieldError(null); }}
                            />
                        ) : (
                            <View style={styles.inputRow}>
                                <TextInput
                                    style={[styles.input, styles.inputHalf, !heightFt && fieldError ? styles.inputError : undefined]}
                                    placeholder="ft"
                                    placeholderTextColor={colors.textMuted}
                                    keyboardType="number-pad"
                                    value={heightFt}
                                    onChangeText={(t) => { setHeightFt(t); setFieldError(null); }}
                                />
                                <TextInput
                                    style={[styles.input, styles.inputHalf, !heightIn && fieldError ? styles.inputError : undefined]}
                                    placeholder="in"
                                    placeholderTextColor={colors.textMuted}
                                    keyboardType="number-pad"
                                    value={heightIn}
                                    onChangeText={(t) => { setHeightIn(t); setFieldError(null); }}
                                />
                            </View>
                        )}
                        {fieldError && step === 2 ? <Text style={styles.inlineError}>{fieldError}</Text> : null}
                    </View>
                );
            case 3:
                return (
                    <View style={styles.stepBlock}>
                        <Text style={styles.title}>Lifestyle</Text>
                        <Text style={styles.subtitle}>Activity and equipment help us personalize your plan.</Text>

                        <Text style={styles.requiredLabel}>Activity level{REQUIRED}</Text>
                        <View style={styles.list}>
                            {ACTIVITY_LEVELS.map((level) => (
                                <TouchableOpacity
                                    key={level.id}
                                    style={[styles.listCard, activityLevel === level.id && styles.listCardSelected]}
                                    onPress={() => setActivityLevel(level.id)}
                                    activeOpacity={0.8}
                                >
                                    <Text style={styles.listLabel}>{level.label}</Text>
                                    <Text style={styles.listDesc}>{level.desc}</Text>
                                </TouchableOpacity>
                            ))}
                        </View>

                        <Text style={styles.requiredLabel}>Equipment access{REQUIRED}</Text>
                        <Text style={styles.hint}>Select at least one.</Text>
                        <View style={styles.equipRow}>
                            {EQUIPMENT.map((item) => {
                                const selected = selectedEquipment.includes(item.id);
                                return (
                                    <TouchableOpacity
                                        key={item.id}
                                        style={[styles.equipCard, selected && styles.goalCardSelected]}
                                        onPress={() => setSelectedEquipment((prev) => (prev.includes(item.id) ? prev.filter((i) => i !== item.id) : [...prev, item.id]))}
                                        activeOpacity={0.8}
                                    >
                                        <Ionicons name={item.icon as any} size={22} color={selected ? colors.foreground : colors.textMuted} />
                                        <Text style={[styles.caption, selected && styles.goalLabelSelected]}>{item.label}</Text>
                                    </TouchableOpacity>
                                );
                            })}
                        </View>
                        {fieldError && step === 3 ? <Text style={styles.inlineError}>{fieldError}</Text> : null}
                    </View>
                );
            case 4:
                return (
                    <View style={styles.stepBlock}>
                        <Text style={styles.title}>Last details</Text>
                        <Text style={styles.subtitle}>Finalize your profile so Max can coach you better.</Text>

                        <Text style={styles.requiredLabel}>Experience level{REQUIRED}</Text>
                        <View style={styles.list}>
                            {EXPERIENCE.map((exp) => (
                                <TouchableOpacity
                                    key={exp.id}
                                    style={[styles.listCard, experience === exp.id && styles.listCardSelected]}
                                    onPress={() => setExperience(exp.id)}
                                    activeOpacity={0.8}
                                >
                                    <Text style={styles.listLabel}>{exp.label}</Text>
                                    <Text style={styles.listDesc}>{exp.desc}</Text>
                                </TouchableOpacity>
                            ))}
                        </View>

                        <Text style={styles.requiredLabel}>Skin type{REQUIRED}</Text>
                        <View style={styles.chipRow}>
                            {SKIN_TYPES.map((type) => (
                                <TouchableOpacity
                                    key={type.id}
                                    style={[styles.chip, skinType === type.id && styles.chipSelected]}
                                    onPress={() => setSkinType(type.id)}
                                    activeOpacity={0.8}
                                >
                                    <Text style={[styles.chipText, skinType === type.id && styles.chipTextSelected]}>{type.label}</Text>
                                </TouchableOpacity>
                            ))}
                        </View>
                        {fieldError && step === 4 ? <Text style={styles.inlineError}>{fieldError}</Text> : null}
                    </View>
                );
            default:
                return null;
        }
    };

    return (
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.wrapper}>
            <View style={styles.header}>
                <TouchableOpacity onPress={prevStep} disabled={step === 1} style={styles.backBtn} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={24} color={step === 1 ? colors.textMuted : colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.stepIndicator}>Step {step} of 4</Text>
                <View style={styles.backBtn} />
            </View>

                <View style={styles.progressWrap}>
                <View style={styles.progressBar}>
                    <View style={[styles.progressFill, { width: `${(step / 4) * 100}%` }]} />
                </View>
            </View>

            <ScrollView
                style={styles.scroll}
                contentContainerStyle={styles.content}
                showsVerticalScrollIndicator={false}
                keyboardShouldPersistTaps="handled"
            >
                <Animated.View style={{ opacity: fadeAnim }}>{renderStepContent()}</Animated.View>

                <TouchableOpacity
                    style={[styles.button, loading && styles.buttonDisabled]}
                    onPress={nextStep}
                    disabled={loading}
                    activeOpacity={0.85}
                >
                    <Text style={styles.buttonText}>{loading ? 'Saving...' : step === 4 ? 'Complete profile' : 'Continue'}</Text>
                </TouchableOpacity>
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    wrapper: { flex: 1, backgroundColor: colors.background },
    scroll: { flex: 1 },
    content: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: 48 },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingTop: 56,
        paddingBottom: spacing.sm,
    },
    backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
    stepIndicator: { ...typography.label, color: colors.textMuted, letterSpacing: 0.5 },
    progressWrap: { paddingHorizontal: spacing.lg, marginBottom: spacing.xl },
    progressBar: { height: 6, backgroundColor: colors.surface, borderRadius: 3, overflow: 'hidden' },
    progressFill: { height: '100%', backgroundColor: colors.foreground, borderRadius: 3 },
    stepBlock: { marginBottom: spacing.xl },
    title: { ...typography.h1, marginBottom: spacing.xs, fontSize: 26 },
    titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
    subtitle: { ...typography.bodySmall, color: colors.textSecondary, marginBottom: spacing.xl, lineHeight: 20 },
    requiredLabel: {
        ...typography.label,
        color: colors.textMuted,
        marginBottom: spacing.sm,
        marginTop: spacing.lg,
    },
    hint: { fontSize: 12, color: colors.textMuted, marginBottom: spacing.sm },
    inlineError: { fontSize: 13, color: colors.error, marginTop: spacing.sm },
    goalsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    goalCard: {
        width: '31%',
        minHeight: 88,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 2,
        borderColor: 'transparent',
        ...shadows.sm,
    },
    goalCardSelected: { borderColor: colors.foreground, backgroundColor: colors.accentMuted },
    goalLabel: { ...typography.caption, marginTop: spacing.xs, color: colors.textSecondary, textAlign: 'center' },
    goalLabelSelected: { color: colors.foreground, fontWeight: '600' },
    unitToggle: {
        flexDirection: 'row',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.full,
        padding: 4,
        borderWidth: 1,
        borderColor: colors.border,
    },
    unitBtn: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: borderRadius.full },
    unitBtnActive: { backgroundColor: colors.foreground },
    unitLabel: { fontSize: 12, fontWeight: '600', color: colors.textMuted },
    unitLabelActive: { color: colors.buttonText },
    chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    chip: {
        paddingHorizontal: spacing.lg,
        paddingVertical: 12,
        borderRadius: borderRadius.full,
        backgroundColor: colors.card,
        borderWidth: 2,
        borderColor: colors.border,
    },
    chipSelected: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    chipText: { ...typography.bodySmall, fontWeight: '500', color: colors.textSecondary },
    chipTextSelected: { color: colors.buttonText, fontWeight: '600' },
    input: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.md,
        paddingVertical: 14,
        paddingHorizontal: spacing.md,
        fontSize: 16,
        color: colors.textPrimary,
        borderWidth: 2,
        borderColor: colors.border,
    },
    inputError: { borderColor: colors.error },
    inputRow: { flexDirection: 'row', gap: spacing.md },
    inputHalf: { flex: 1 },
    list: { gap: spacing.sm },
    listCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.lg,
        borderWidth: 2,
        borderColor: 'transparent',
    },
    listCardSelected: { borderColor: colors.foreground, backgroundColor: colors.accentMuted },
    listLabel: { ...typography.body, fontWeight: '600', color: colors.foreground },
    listDesc: { ...typography.caption, color: colors.textMuted, marginTop: 4 },
    equipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    equipCard: {
        width: '31%',
        minHeight: 80,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 2,
        borderColor: 'transparent',
        ...shadows.sm,
    },
    caption: { ...typography.caption, color: colors.textMuted, textAlign: 'center', marginTop: 4 },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: 18,
        alignItems: 'center',
        marginTop: spacing.xl,
        ...shadows.md,
    },
    buttonDisabled: { opacity: 0.6 },
    buttonText: { ...typography.button, color: colors.buttonText },
});
