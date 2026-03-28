/**
 * Pre-payment profile questionnaire (after login, before face scan & pay).
 * Cal-AI style: grouped sections, priorities replace manual module pick — data → user.onboarding.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    ScrollView,
    TextInput,
    KeyboardAvoidingView,
    Platform,
    Alert,
    Animated,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const PRIORITY_KEYS = ['face_structure', 'skin', 'hair', 'body', 'height'] as const;
type PriorityKey = (typeof PRIORITY_KEYS)[number];

const PRIORITY_LABELS: Record<PriorityKey, string> = {
    face_structure: 'Face structure',
    skin: 'Skin',
    hair: 'Hair',
    body: 'Body',
    height: 'Height',
};

const APPEARANCE_OPTIONS: { id: string; label: string }[] = [
    { id: 'jawline', label: 'Jawline' },
    { id: 'skin', label: 'Skin' },
    { id: 'hair_thinning', label: 'Hair thinning' },
    { id: 'body_fat', label: 'Body fat' },
    { id: 'posture', label: 'Posture' },
    { id: 'height', label: 'Height' },
    { id: 'under_eye', label: 'Under-eye area' },
    { id: 'asymmetry', label: 'Facial asymmetry' },
    { id: 'acne', label: 'Acne' },
    { id: 'teeth', label: 'Teeth' },
];

const SKIN_CONCERNS = [
    { id: 'acne', label: 'Acne' },
    { id: 'pigmentation', label: 'Pigmentation' },
    { id: 'texture-scarring', label: 'Texture / scarring' },
    { id: 'redness', label: 'Redness' },
    { id: 'aging', label: 'Aging' },
];

const SCREEN_TIME_BANDS = [
    { id: 'under_4', label: 'Under 4h' },
    { id: '4_6', label: '4–6h' },
    { id: '6_8', label: '6–8h' },
    { id: '8_plus', label: '8h+' },
];

/** Reasonable human ranges — enforced on type + on Continue */
const AGE_MIN = 13;
const AGE_MAX = 120;
const HEIGHT_CM_MIN = 122; // ~4′0″
const HEIGHT_CM_MAX = 272; // ~8′11″
const WEIGHT_KG_MIN = 30;
const WEIGHT_KG_MAX = 300;
const WEIGHT_LBS_MIN = 66;
const WEIGHT_LBS_MAX = 660;
const HEIGHT_FT_MAX = 8;
const HEIGHT_IN_MAX = 11;
const HEIGHT_TOTAL_IN_MIN = 48; // 4′0″
const HEIGHT_TOTAL_IN_MAX = 107; // 8′11″

function mapPriorityToGoals(order: PriorityKey[]): string[] {
    const m: Record<PriorityKey, string> = {
        face_structure: 'bonemax',
        skin: 'skinmax',
        hair: 'hairmax',
        body: 'fitmax',
        height: 'heightmax',
    };
    return [...new Set(order.map((k) => m[k]).filter(Boolean))];
}

function mapSkinConcernToType(concern: string): string {
    const c: Record<string, string> = {
        acne: 'oily',
        pigmentation: 'combination',
        'texture-scarring': 'combination',
        redness: 'sensitive',
        aging: 'normal',
    };
    return c[concern] || 'normal';
}

function mapTrainingToExperience(t: string): string {
    if (t === 'never' || t === 'beginner') return 'beginner';
    if (t === 'intermediate') return 'intermediate';
    if (t === 'advanced') return 'advanced';
    return 'beginner';
}

function mapEquipmentToList(eq: string): string[] {
    if (eq === 'full_gym') return ['gym'];
    if (eq === 'home_gym') return ['dumbbells'];
    return ['none'];
}

function detectHairFromScan(scan: any): boolean {
    const m = scan?.analysis?.umax_metrics;
    if (!Array.isArray(m)) return false;
    return m.some((x: any) => {
        const id = `${x.id || ''} ${x.label || ''}`.toLowerCase();
        if (!id.includes('hair')) return false;
        const s = Number(x.score);
        return !Number.isNaN(s) && s < 5.5;
    });
}

function sanitizeAge(raw: string): string {
    const d = raw.replace(/\D/g, '').slice(0, 3);
    if (!d) return '';
    let n = parseInt(d, 10);
    if (Number.isNaN(n)) return '';
    if (n > AGE_MAX) n = AGE_MAX;
    return String(n);
}

function sanitizeFeet(raw: string): string {
    const d = raw.replace(/\D/g, '').slice(0, 2);
    if (!d) return '';
    let n = parseInt(d, 10);
    if (Number.isNaN(n)) return '';
    if (n > HEIGHT_FT_MAX) n = HEIGHT_FT_MAX;
    return String(n);
}

function sanitizeInches(raw: string): string {
    const d = raw.replace(/\D/g, '').slice(0, 2);
    if (!d) return '';
    let n = parseInt(d, 10);
    if (Number.isNaN(n)) return '';
    if (n > HEIGHT_IN_MAX) n = HEIGHT_IN_MAX;
    return String(n);
}

function sanitizeHeightCmInput(raw: string): string {
    let s = raw.replace(/[^\d.]/g, '');
    const firstDot = s.indexOf('.');
    if (firstDot !== -1) {
        s = s.slice(0, firstDot + 1) + s.slice(firstDot + 1).replace(/\./g, '');
    }
    const parts = s.split('.');
    const intPart = (parts[0] || '').slice(0, 3);
    const dec = parts.length > 1 ? parts[1].slice(0, 1) : '';
    let out = dec !== '' ? `${intPart}.${dec}` : intPart;
    if (out === '.' || out.endsWith('.')) return out;
    const n = parseFloat(out);
    if (!Number.isNaN(n) && n > HEIGHT_CM_MAX) return String(HEIGHT_CM_MAX);
    return out;
}

function sanitizeWeightInput(raw: string, metric: boolean): string {
    let s = raw.replace(/[^\d.]/g, '');
    const firstDot = s.indexOf('.');
    if (firstDot !== -1) {
        s = s.slice(0, firstDot + 1) + s.slice(firstDot + 1).replace(/\./g, '');
    }
    const parts = s.split('.');
    const intPart = (parts[0] || '').slice(0, 3);
    const decPart = parts.length > 1 ? parts[1].slice(0, 2) : '';
    let out = decPart !== '' ? `${intPart}.${decPart}` : intPart;
    if (out === '.' || out.endsWith('.')) return out;
    const n = parseFloat(out);
    if (Number.isNaN(n)) return out;
    const max = metric ? WEIGHT_KG_MAX : WEIGHT_LBS_MAX;
    if (n > max) return String(max);
    return out;
}

const TIME_OPTIONS: string[] = Array.from({ length: 48 }, (_, i) => {
    const h = Math.floor(i / 2);
    const m = i % 2 === 0 ? 0 : 30;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
});

function formatTime12h(hhmm24: string): string {
    const [hs, ms] = hhmm24.split(':');
    const h = parseInt(hs || '0', 10);
    const m = parseInt(ms || '0', 10);
    if (Number.isNaN(h) || Number.isNaN(m)) return hhmm24;
    const suffix = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}:${String(m).padStart(2, '0')} ${suffix}`;
}

/** Returns null if valid, else error message */
function validateClockHHMM(s: string, label: string): string | null {
    const t = s.trim();
    if (!/^\d{1,2}:\d{2}$/.test(t)) return `${label}: use HH:MM (24h), e.g. 07:00.`;
    const [hs, ms] = t.split(':');
    const h = parseInt(hs, 10);
    const m = parseInt(ms, 10);
    if (h < 0 || h > 23 || m < 0 || m > 59) return `${label}: hour 0–23, minutes 0–59.`;
    return null;
}

function isAgeOutOfRange(age: string): boolean {
    const t = age.trim();
    if (!t) return false;
    if (!/^\d+$/.test(t)) return true;
    const a = parseInt(t, 10);
    if (Number.isNaN(a)) return true;
    if (t.length === 1) return false;
    return a < AGE_MIN || a > AGE_MAX;
}

function isWeightOutOfRange(weightStr: string, metric: boolean): boolean {
    const t = weightStr.trim();
    if (!t) return false;
    const w = parseFloat(t);
    if (Number.isNaN(w) || w <= 0) return true;
    const min = metric ? WEIGHT_KG_MIN : WEIGHT_LBS_MIN;
    const max = metric ? WEIGHT_KG_MAX : WEIGHT_LBS_MAX;
    return w < min || w > max;
}

function isHeightCmOutOfRange(heightCmStr: string): boolean {
    const t = heightCmStr.trim();
    if (!t) return false;
    const h = parseFloat(t);
    if (Number.isNaN(h) || h <= 0) return true;
    return h < HEIGHT_CM_MIN || h > HEIGHT_CM_MAX;
}

function isHeightImperialOutOfRange(ftStr: string, inStr: string): boolean {
    const ft = parseInt(ftStr, 10) || 0;
    const inch = parseInt(inStr, 10) || 0;
    if (ft <= 0 && inch <= 0) return false;
    const totalIn = ft * 12 + inch;
    return totalIn < HEIGHT_TOTAL_IN_MIN || totalIn > HEIGHT_TOTAL_IN_MAX;
}

export default function OnboardingScreen() {
    const navigation = useNavigation<any>();
    const { refreshUser, isAuthenticated } = useAuth() as any;
    const fade = useRef(new Animated.Value(1)).current;

    const [stepIndex, setStepIndex] = useState(0);
    const [loading, setLoading] = useState(false);
    const [scanHairHint, setScanHairHint] = useState(false);

    const [unitSystem, setUnitSystem] = useState<'metric' | 'imperial'>('imperial');
    const [age, setAge] = useState('');
    const [gender, setGender] = useState('');
    const [heightCm, setHeightCm] = useState('');
    const [heightFt, setHeightFt] = useState('');
    const [heightIn, setHeightIn] = useState('');
    const [weight, setWeight] = useState('');

    const [priorityOrder, setPriorityOrder] = useState<PriorityKey[]>([...PRIORITY_KEYS]);
    const [appearanceConcerns, setAppearanceConcerns] = useState<string[]>([]);

    const [primarySkin, setPrimarySkin] = useState('');
    const [secondarySkin, setSecondarySkin] = useState('');
    const [skincareRoutine, setSkincareRoutine] = useState('');

    const [hairFamily, setHairFamily] = useState('');
    const [hairLoss, setHairLoss] = useState('');
    const [hairTreatments, setHairTreatments] = useState('');
    const [hairSides, setHairSides] = useState('');

    const [fitGoal, setFitGoal] = useState('');
    const [fitExperience, setFitExperience] = useState('');
    const [fitEquipment, setFitEquipment] = useState('');
    const [fitDays, setFitDays] = useState<number | null>(null);

    const [wakeTime, setWakeTime] = useState('07:00');
    const [bedTime, setBedTime] = useState('23:00');
    const [workoutTime, setWorkoutTime] = useState('18:00');
    const [openTimePicker, setOpenTimePicker] = useState<'wake' | 'bed' | 'workout' | null>(null);
    const [screenBand, setScreenBand] = useState('');

    const [attemptA, setAttemptA] = useState(false);
    const [attemptB, setAttemptB] = useState(false);
    const [attemptC, setAttemptC] = useState(false);
    const [attemptD, setAttemptD] = useState(false);
    const [attemptE, setAttemptE] = useState(false);
    const [attemptF, setAttemptF] = useState(false);

    useEffect(() => {
        (async () => {
            try {
                const scan = await api.getLatestScan();
                setScanHairHint(detectHairFromScan(scan));
            } catch {
                setScanHairHint(false);
            }
        })();
    }, []);

    useEffect(() => {
        setAttemptA(false);
        setAttemptB(false);
        setAttemptC(false);
        setAttemptD(false);
        setAttemptE(false);
        setAttemptF(false);
    }, [stepIndex]);

    const topThree = useMemo(() => priorityOrder.slice(0, 3), [priorityOrder]);
    const showSkin = topThree.includes('skin');
    const showBody = topThree.includes('body');
    const showHair = topThree.includes('hair') || scanHairHint || appearanceConcerns.includes('hair_thinning');
    const showWorkoutTime = showBody || appearanceConcerns.includes('body_fat') || appearanceConcerns.includes('posture');

    const sections = useMemo(() => {
        const s: string[] = ['A', 'B'];
        if (showSkin) s.push('C');
        if (showHair) s.push('D');
        if (showBody) s.push('E');
        s.push('F');
        return s;
    }, [showSkin, showHair, showBody]);

    const currentSection = sections[stepIndex] ?? 'A';
    const totalSteps = sections.length;

    const animateStep = useCallback(
        (next: number) => {
            Animated.timing(fade, { toValue: 0, duration: 160, useNativeDriver: true }).start(() => {
                setStepIndex(next);
                Animated.timing(fade, { toValue: 1, duration: 220, useNativeDriver: true }).start();
            });
        },
        [fade]
    );

    const movePriority = (index: number, dir: -1 | 1) => {
        const j = index + dir;
        if (j < 0 || j >= priorityOrder.length) return;
        const next = [...priorityOrder];
        [next[index], next[j]] = [next[j], next[index]];
        setPriorityOrder(next);
    };

    const toggleAppearance = (id: string) => {
        setAppearanceConcerns((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    };

    const validateSection = (): string | null => {
        if (currentSection === 'A') {
            const a = parseInt(age, 10);
            if (!gender.trim()) return 'Pick a gender.';
            if (!age.trim() || Number.isNaN(a) || a < AGE_MIN || a > AGE_MAX) return `Age (${AGE_MIN}–${AGE_MAX}).`;
            const w = parseFloat(weight);
            if (!weight.trim() || Number.isNaN(w) || w <= 0) return 'Enter your weight.';
            if (unitSystem === 'metric') {
                if (w < WEIGHT_KG_MIN || w > WEIGHT_KG_MAX) {
                    return `Weight: enter ${WEIGHT_KG_MIN}–${WEIGHT_KG_MAX} kg.`;
                }
                const h = parseFloat(heightCm);
                if (!heightCm.trim() || Number.isNaN(h) || h <= 0) return 'Enter height (cm).';
                if (h < HEIGHT_CM_MIN || h > HEIGHT_CM_MAX) {
                    return `Height: ${HEIGHT_CM_MIN}–${HEIGHT_CM_MAX} cm (about 4′0″–8′11″).`;
                }
            } else {
                if (w < WEIGHT_LBS_MIN || w > WEIGHT_LBS_MAX) {
                    return `Weight: enter ${WEIGHT_LBS_MIN}–${WEIGHT_LBS_MAX} lb.`;
                }
                const ft = Math.min(HEIGHT_FT_MAX, parseInt(heightFt, 10) || 0);
                const inch = Math.min(HEIGHT_IN_MAX, parseInt(heightIn, 10) || 0);
                if (ft <= 0 && inch <= 0) return 'Enter height (ft / in).';
                const totalIn = ft * 12 + inch;
                if (totalIn < HEIGHT_TOTAL_IN_MIN || totalIn > HEIGHT_TOTAL_IN_MAX) {
                    return `Height: roughly 4′0″–8′11″ — check feet and inches.`;
                }
            }
        }
        if (currentSection === 'B') {
            if (appearanceConcerns.length === 0) return 'Pick at least one area that bothers you.';
        }
        if (currentSection === 'C') {
            if (!primarySkin) return 'Pick your main skin concern.';
            if (!skincareRoutine) return 'How built-out is your routine?';
        }
        if (currentSection === 'D') {
            if (!hairFamily) return 'Family hair loss history?';
            if (!hairLoss) return 'Current hair loss status?';
            if (!hairTreatments) return 'Current treatments?';
            if (!hairSides) return 'Side-effect sensitivity?';
        }
        if (currentSection === 'E') {
            if (!fitGoal) return 'Pick a fitness goal.';
            if (!fitExperience) return 'Training experience?';
            if (!fitEquipment) return 'Equipment access?';
            if (!fitDays) return 'Days per week available?';
        }
        if (currentSection === 'F') {
            const wErr = validateClockHHMM(wakeTime, 'Wake time');
            if (wErr) return wErr;
            const bErr = validateClockHHMM(bedTime, 'Bed time');
            if (bErr) return bErr;
            if (showWorkoutTime) {
                const wo = validateClockHHMM(workoutTime, 'Workout time');
                if (wo) return wo;
            }
            if (!screenBand) return 'Rough screen time?';
        }
        return null;
    };

    /** Store height in cm (metric) OR total inches (imperial). */
    const toStoredHeight = (): number => {
        if (unitSystem === 'metric') return Math.round(parseFloat(heightCm) * 10) / 10;
        const ft = parseInt(heightFt, 10) || 0;
        const inch = parseInt(heightIn, 10) || 0;
        return Math.round((ft * 12 + inch) * 10) / 10;
    };

    /** Store weight in kg (metric) OR lbs (imperial). */
    const toStoredWeight = (): number => {
        const w = parseFloat(weight);
        return Math.round(w * 10) / 10;
    };

    const hhmm = (s: string) => {
        const p = s.trim().split(':');
        const h = Math.min(23, Math.max(0, parseInt(p[0] || '0', 10)));
        const m = Math.min(59, Math.max(0, parseInt(p[1] || '0', 10)));
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    };

    const buildPayload = (): Record<string, unknown> => {
        const goals = mapPriorityToGoals(priorityOrder);
        const skinType = showSkin && primarySkin ? mapSkinConcernToType(primarySkin) : 'normal';
        const experience_level = showBody ? mapTrainingToExperience(fitExperience) : 'beginner';
        const equipment = showBody ? mapEquipmentToList(fitEquipment) : [];

        const heavyScreen =
            screenBand === '6_8' || screenBand === '8_plus' ? '6+ hours/day' : screenBand === '4_6' ? '4-6 hours/day' : 'under 4 hours/day';

        const payload: Record<string, unknown> = {
            goals,
            questionnaire_v2_completed: true,
            completed: true,
            priority_order: [...priorityOrder],
            appearance_concerns: [...appearanceConcerns],
            age: parseInt(age, 10),
            gender: gender.trim(),
            height: toStoredHeight(),
            weight: toStoredWeight(),
            unit_system: unitSystem,
            timezone: typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC',
            skin_type: skinType,
            experience_level,
            equipment,
            activity_level: 'moderate',
            wake_time: hhmm(wakeTime),
            sleep_time: hhmm(bedTime),
            screen_hours_daily: screenBand,
            heightmax_screen_hours: heavyScreen,
            bonemax_heavy_screen_time: heavyScreen,
            scan_suggested_hair_focus: scanHairHint,
        };

        if (showSkin) {
            payload.primary_skin_concern = primarySkin;
            payload.secondary_skin_concern = secondarySkin || 'none';
            payload.skincare_routine_level = skincareRoutine;
        }
        if (showHair) {
            payload.hair_family_history = hairFamily;
            payload.hair_current_loss = hairLoss;
            payload.hair_treatments_current = hairTreatments;
            payload.hair_side_effect_sensitivity = hairSides;
            if (hairLoss === 'yes_active' || hairLoss === 'starting') {
                payload.hair_thinning = 'yes';
                payload.thinning = 'yes';
            } else {
                payload.hair_thinning = 'no';
            }
            if (hairSides === 'had_sides') {
                payload.hairmax_fin_sensitive = true;
                payload.hair_finasteride_sensitive = true;
            }
        }
        if (showBody) {
            payload.fitmax_primary_goal = fitGoal;
            payload.fitmax_training_experience = fitExperience;
            payload.fitmax_equipment = fitEquipment;
            payload.fitmax_workout_days_per_week = fitDays;
            payload.primary_goal = fitGoal;
            payload.training_experience = fitExperience;
        }
        if (showWorkoutTime) {
            payload.preferred_workout_time = hhmm(workoutTime);
            payload.fitmax_preferred_workout_time = hhmm(workoutTime);
            payload.heightmax_workout_time = hhmm(workoutTime);
        }
        return payload;
    };

    const submit = async () => {
        const err = validateSection();
        if (err) {
            if (currentSection === 'F') setAttemptF(true);
            return;
        }
        setLoading(true);
        try {
            const payload = buildPayload();
            if (isAuthenticated) {
                await api.saveOnboarding(payload as any);
                await refreshUser();
                navigation.navigate('FeaturesIntro');
            } else {
                const res = await api.saveOnboardingAnonymous(payload as any);
                navigation.navigate('Login', { onboarding: res.data });
            }
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not save profile. Try again.');
        } finally {
            setLoading(false);
        }
    };

    const goNext = () => {
        const err = validateSection();
        if (err) {
            switch (currentSection) {
                case 'A':
                    setAttemptA(true);
                    break;
                case 'B':
                    setAttemptB(true);
                    break;
                case 'C':
                    setAttemptC(true);
                    break;
                case 'D':
                    setAttemptD(true);
                    break;
                case 'E':
                    setAttemptE(true);
                    break;
                case 'F':
                    setAttemptF(true);
                    break;
            }
            return;
        }
        if (stepIndex >= totalSteps - 1) {
            submit();
            return;
        }
        animateStep(stepIndex + 1);
    };

    const goBack = () => {
        if (stepIndex <= 0) return;
        animateStep(stepIndex - 1);
    };

    const renderA = () => {
        const metric = unitSystem === 'metric';
        const aNum = parseInt(age, 10);
        const ageBad = !age.trim() || Number.isNaN(aNum) || aNum < AGE_MIN || aNum > AGE_MAX;
        const showAgeErr = (attemptA && ageBad) || isAgeOutOfRange(age);

        const w = parseFloat(weight);
        const weightBad =
            !weight.trim() ||
            Number.isNaN(w) ||
            w <= 0 ||
            (metric ? w < WEIGHT_KG_MIN || w > WEIGHT_KG_MAX : w < WEIGHT_LBS_MIN || w > WEIGHT_LBS_MAX);
        const showWeightErr = (attemptA && weightBad) || isWeightOutOfRange(weight, metric);

        const hCm = parseFloat(heightCm);
        const heightCmBad =
            !heightCm.trim() || Number.isNaN(hCm) || hCm <= 0 || hCm < HEIGHT_CM_MIN || hCm > HEIGHT_CM_MAX;
        const showHeightCmErr = (attemptA && heightCmBad) || isHeightCmOutOfRange(heightCm);

        const ft = Math.min(HEIGHT_FT_MAX, parseInt(heightFt, 10) || 0);
        const inch = Math.min(HEIGHT_IN_MAX, parseInt(heightIn, 10) || 0);
        const totalIn = ft * 12 + inch;
        const heightImpBad = (ft <= 0 && inch <= 0) || totalIn < HEIGHT_TOTAL_IN_MIN || totalIn > HEIGHT_TOTAL_IN_MAX;
        const showHeightImpErr = (attemptA && heightImpBad) || isHeightImperialOutOfRange(heightFt, heightIn);

        const showGenderErr = attemptA && !gender.trim();

        return (
            <View style={styles.card}>
                <Text style={styles.kicker}>Baseline</Text>
                <Text style={styles.h1} numberOfLines={1} ellipsizeMode="tail">
                    Baseline stats
                </Text>
                <Text style={styles.lead}>Used to personalize your targets, priorities, and reminders.</Text>

                <Text style={styles.label}>Gender</Text>
                <View style={[styles.rowWrap, showGenderErr && styles.groupErrorOutline]}>
                    {['Male', 'Female', 'Other'].map((g) => (
                        <TouchableOpacity key={g} style={[styles.pill, gender === g && styles.pillOn]} onPress={() => setGender(g)} activeOpacity={0.85}>
                            <Text style={[styles.pillText, gender === g && styles.pillTextOn]}>{g}</Text>
                        </TouchableOpacity>
                    ))}
                </View>
                {showGenderErr ? <Text style={styles.fieldErrorText}>Pick one.</Text> : null}

                <View style={styles.unitRow}>
                    <Text style={styles.label}>Units</Text>
                    <View style={styles.unitToggle}>
                        <TouchableOpacity style={[styles.unitChip, unitSystem === 'metric' && styles.unitChipOn]} onPress={() => setUnitSystem('metric')}>
                            <Text style={[styles.unitChipText, unitSystem === 'metric' && styles.unitChipTextOn]}>Metric</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={[styles.unitChip, unitSystem === 'imperial' && styles.unitChipOn]} onPress={() => setUnitSystem('imperial')}>
                            <Text style={[styles.unitChipText, unitSystem === 'imperial' && styles.unitChipTextOn]}>US</Text>
                        </TouchableOpacity>
                    </View>
                </View>

                <Text style={styles.label}>Age</Text>
                <TextInput
                    style={[styles.input, showAgeErr && styles.inputError]}
                    placeholder="e.g. 24"
                    placeholderTextColor={colors.textMuted}
                    keyboardType="number-pad"
                    value={age}
                    onChangeText={(t) => setAge(sanitizeAge(t))}
                />
                {showAgeErr ? (
                    <Text style={styles.fieldErrorText}>{!age.trim() ? 'Enter your age.' : `Use ${AGE_MIN}–${AGE_MAX}.`}</Text>
                ) : null}

                <Text style={styles.label}>Weight ({metric ? 'kg' : 'lb'})</Text>
                <TextInput
                    style={[styles.input, showWeightErr && styles.inputError]}
                    placeholder={metric ? 'e.g. 75' : 'e.g. 175'}
                    placeholderTextColor={colors.textMuted}
                    keyboardType="decimal-pad"
                    value={weight}
                    onChangeText={(t) => setWeight(sanitizeWeightInput(t, metric))}
                />
                {showWeightErr ? (
                    <Text style={styles.fieldErrorText}>
                        {!weight.trim() || Number.isNaN(w) || w <= 0
                            ? 'Enter your weight.'
                            : metric
                              ? `Use ${WEIGHT_KG_MIN}–${WEIGHT_KG_MAX} kg.`
                              : `Use ${WEIGHT_LBS_MIN}–${WEIGHT_LBS_MAX} lb.`}
                    </Text>
                ) : null}

                <Text style={styles.label}>Height {metric ? '(cm)' : '(ft / in)'}</Text>
                {metric ? (
                    <>
                        <TextInput
                            style={[styles.input, showHeightCmErr && styles.inputError]}
                            placeholder="e.g. 178"
                            placeholderTextColor={colors.textMuted}
                            keyboardType="decimal-pad"
                            value={heightCm}
                            onChangeText={(t) => setHeightCm(sanitizeHeightCmInput(t))}
                        />
                        {showHeightCmErr ? (
                            <Text style={styles.fieldErrorText}>
                                {!heightCm.trim() || Number.isNaN(hCm) || hCm <= 0
                                    ? 'Enter height in cm.'
                                    : `Use ${HEIGHT_CM_MIN}–${HEIGHT_CM_MAX} cm.`}
                            </Text>
                        ) : null}
                    </>
                ) : (
                    <>
                        <View style={styles.heightRowImperial}>
                            <TextInput
                                style={[styles.input, styles.heightSplitInput, showHeightImpErr && styles.inputError]}
                                placeholder="ft"
                                keyboardType="number-pad"
                                value={heightFt}
                                onChangeText={(t) => setHeightFt(sanitizeFeet(t))}
                                placeholderTextColor={colors.textMuted}
                            />
                            <TextInput
                                style={[styles.input, styles.heightSplitInput, showHeightImpErr && styles.inputError]}
                                placeholder="in"
                                keyboardType="number-pad"
                                value={heightIn}
                                onChangeText={(t) => setHeightIn(sanitizeInches(t))}
                                placeholderTextColor={colors.textMuted}
                            />
                        </View>
                        {showHeightImpErr ? (
                            <Text style={styles.fieldErrorText}>
                                {ft <= 0 && inch <= 0 ? 'Enter feet and inches.' : 'Height looks out of range — check ft/in.'}
                            </Text>
                        ) : null}
                    </>
                )}
            </View>
        );
    };

    const renderB = () => (
        <View style={styles.card}>
            <Text style={styles.kicker}>Stack order</Text>
            <Text style={styles.h1} numberOfLines={1} ellipsizeMode="tail">
                What we push first
            </Text>
            <Text style={styles.lead}>Rank top = loudest in your rotation. Lower slots still get love — just quieter.</Text>

            <Text style={styles.label}>Rank — use arrows</Text>
            {priorityOrder.map((key, i) => (
                <View key={key} style={styles.rankRow}>
                    <Text style={styles.rankNum}>{i + 1}</Text>
                    <Text style={styles.rankLabel}>{PRIORITY_LABELS[key]}</Text>
                    <View style={styles.rankArrows}>
                        <TouchableOpacity onPress={() => movePriority(i, -1)} disabled={i === 0} style={styles.iconBtn}>
                            <Ionicons name="chevron-up" size={22} color={i === 0 ? colors.border : colors.foreground} />
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => movePriority(i, 1)} disabled={i === priorityOrder.length - 1} style={styles.iconBtn}>
                            <Ionicons name="chevron-down" size={22} color={i === priorityOrder.length - 1 ? colors.border : colors.foreground} />
                        </TouchableOpacity>
                    </View>
                </View>
            ))}

            <Text style={[styles.label, { marginTop: spacing.xl }]}>What bothers you most? (select all)</Text>
            <View style={[styles.rowWrap, attemptB && appearanceConcerns.length === 0 && styles.groupErrorOutline]}>
                {APPEARANCE_OPTIONS.map((o) => {
                    const on = appearanceConcerns.includes(o.id);
                    return (
                        <TouchableOpacity key={o.id} style={[styles.tag, on && styles.tagOn]} onPress={() => toggleAppearance(o.id)} activeOpacity={0.85}>
                            <Text style={[styles.tagText, on && styles.tagTextOn]}>{o.label}</Text>
                        </TouchableOpacity>
                    );
                })}
            </View>
            {attemptB && appearanceConcerns.length === 0 ? <Text style={styles.fieldErrorText}>Pick at least one.</Text> : null}
        </View>
    );

    const renderC = () => (
        <View style={styles.card}>
            <Text style={styles.kicker}>Skin</Text>
            <Text style={styles.h1} numberOfLines={1} ellipsizeMode="tail">
                Skin priorities
            </Text>
            <Text style={styles.lead}>Pick the concerns you want to focus on first.</Text>

            <Text style={styles.label}>Primary concern</Text>
            <View style={[styles.rowWrap, attemptC && !primarySkin && styles.groupErrorOutline]}>
                {SKIN_CONCERNS.map((s) => (
                    <TouchableOpacity key={s.id} style={[styles.tag, primarySkin === s.id && styles.tagOn]} onPress={() => setPrimarySkin(s.id)}>
                        <Text style={[styles.tagText, primarySkin === s.id && styles.tagTextOn]}>{s.label}</Text>
                    </TouchableOpacity>
                ))}
            </View>
            {attemptC && !primarySkin ? <Text style={styles.fieldErrorText}>Pick your main concern.</Text> : null}

            <Text style={styles.label}>Secondary concern</Text>
            <View style={styles.rowWrap}>
                <TouchableOpacity style={[styles.tag, secondarySkin === 'none' && styles.tagOn]} onPress={() => setSecondarySkin('none')}>
                    <Text style={[styles.tagText, secondarySkin === 'none' && styles.tagTextOn]}>None</Text>
                </TouchableOpacity>
                {SKIN_CONCERNS.map((s) => (
                    <TouchableOpacity key={s.id} style={[styles.tag, secondarySkin === s.id && styles.tagOn]} onPress={() => setSecondarySkin(s.id)}>
                        <Text style={[styles.tagText, secondarySkin === s.id && styles.tagTextOn]}>{s.label}</Text>
                    </TouchableOpacity>
                ))}
            </View>

            <Text style={styles.label}>Current routine</Text>
            {[
                { id: 'none', label: 'Nothing consistent' },
                { id: 'basic', label: 'Cleanser + moisturizer' },
                { id: 'full', label: 'Full routine' },
            ].map((r) => (
                <TouchableOpacity key={r.id} style={[styles.listRow, skincareRoutine === r.id && styles.listRowOn]} onPress={() => setSkincareRoutine(r.id)}>
                    <Text style={[styles.listRowText, skincareRoutine === r.id && styles.listRowTextOn]}>{r.label}</Text>
                    {skincareRoutine === r.id ? <Ionicons name="checkmark-circle" size={22} color={colors.foreground} /> : null}
                </TouchableOpacity>
            ))}
            {attemptC && !skincareRoutine ? <Text style={styles.fieldErrorText}>Pick how built-out your routine is.</Text> : null}
        </View>
    );

    const renderD = () => (
        <View style={styles.card}>
            <Text style={styles.kicker}>Hair</Text>
            <Text style={styles.h1} numberOfLines={1} ellipsizeMode="tail">
                Hair profile
            </Text>
            <Text style={styles.lead}>Helps tailor your hair plan to your current situation.</Text>
            {scanHairHint ? <Text style={styles.banner}>Your scan flagged hair as a weaker metric — worth an honest pass.</Text> : null}

            <Text style={styles.label}>Family history of hair loss?</Text>
            {[
                { id: 'mom', label: "Mom's side" },
                { id: 'dad', label: "Dad's side" },
                { id: 'both', label: 'Both sides' },
                { id: 'no', label: 'No' },
                { id: 'unknown', label: "Don't know" },
            ].map((x) => (
                <TouchableOpacity key={x.id} style={[styles.listRow, hairFamily === x.id && styles.listRowOn]} onPress={() => setHairFamily(x.id)}>
                    <Text style={[styles.listRowText, hairFamily === x.id && styles.listRowTextOn]}>{x.label}</Text>
                </TouchableOpacity>
            ))}
            {attemptD && !hairFamily ? <Text style={styles.fieldErrorText}>Pick one.</Text> : null}

            <Text style={styles.label}>Currently losing hair?</Text>
            {[
                { id: 'yes_active', label: 'Yes — actively' },
                { id: 'starting', label: 'Think it’s starting' },
                { id: 'no', label: 'No' },
                { id: 'unsure', label: 'Not sure' },
            ].map((x) => (
                <TouchableOpacity key={x.id} style={[styles.listRow, hairLoss === x.id && styles.listRowOn]} onPress={() => setHairLoss(x.id)}>
                    <Text style={[styles.listRowText, hairLoss === x.id && styles.listRowTextOn]}>{x.label}</Text>
                </TouchableOpacity>
            ))}
            {attemptD && !hairLoss ? <Text style={styles.fieldErrorText}>Pick one.</Text> : null}

            <Text style={styles.label}>Current treatments</Text>
            {[
                { id: 'nothing', label: 'Nothing' },
                { id: 'minoxidil', label: 'Minoxidil' },
                { id: 'finasteride', label: 'Finasteride' },
                { id: 'both', label: 'Both' },
                { id: 'other', label: 'Other' },
            ].map((x) => (
                <TouchableOpacity key={x.id} style={[styles.listRow, hairTreatments === x.id && styles.listRowOn]} onPress={() => setHairTreatments(x.id)}>
                    <Text style={[styles.listRowText, hairTreatments === x.id && styles.listRowTextOn]}>{x.label}</Text>
                </TouchableOpacity>
            ))}
            {attemptD && !hairTreatments ? <Text style={styles.fieldErrorText}>Pick one.</Text> : null}

            <Text style={styles.label}>Finasteride / sides</Text>
            {[
                { id: 'not_concerned', label: 'Not concerned' },
                { id: 'somewhat', label: 'Somewhat concerned' },
                { id: 'had_sides', label: 'Had sides before' },
            ].map((x) => (
                <TouchableOpacity key={x.id} style={[styles.listRow, hairSides === x.id && styles.listRowOn]} onPress={() => setHairSides(x.id)}>
                    <Text style={[styles.listRowText, hairSides === x.id && styles.listRowTextOn]}>{x.label}</Text>
                </TouchableOpacity>
            ))}
        </View>
    );

    const renderE = () => (
        <View style={styles.card}>
            <Text style={styles.kicker}>Physique</Text>
            <Text style={styles.h1} numberOfLines={1} ellipsizeMode="tail">
                Training profile
            </Text>
            <Text style={styles.lead}>Sets your plan to match your goal, experience, and equipment.</Text>

            <Text style={styles.label}>Primary goal</Text>
            {[
                { id: 'lean', label: 'Get lean (face gains)' },
                { id: 'muscle', label: 'Build muscle' },
                { id: 'both', label: 'Both / recomp' },
                { id: 'maintain', label: 'Maintain' },
            ].map((x) => (
                <TouchableOpacity key={x.id} style={[styles.listRow, fitGoal === x.id && styles.listRowOn]} onPress={() => setFitGoal(x.id)}>
                    <Text style={[styles.listRowText, fitGoal === x.id && styles.listRowTextOn]}>{x.label}</Text>
                </TouchableOpacity>
            ))}

            <Text style={styles.label}>Training experience</Text>
            {[
                { id: 'never', label: 'Never trained' },
                { id: 'beginner', label: 'Beginner (<1 yr)' },
                { id: 'intermediate', label: 'Intermediate (1–3 yr)' },
                { id: 'advanced', label: 'Advanced (3+ yr)' },
            ].map((x) => (
                <TouchableOpacity key={x.id} style={[styles.listRow, fitExperience === x.id && styles.listRowOn]} onPress={() => setFitExperience(x.id)}>
                    <Text style={[styles.listRowText, fitExperience === x.id && styles.listRowTextOn]}>{x.label}</Text>
                </TouchableOpacity>
            ))}

            <Text style={styles.label}>Equipment</Text>
            {[
                { id: 'full_gym', label: 'Full gym' },
                { id: 'home_gym', label: 'Home gym (DB + bench + bar)' },
                { id: 'bodyweight', label: 'Bodyweight only' },
            ].map((x) => (
                <TouchableOpacity key={x.id} style={[styles.listRow, fitEquipment === x.id && styles.listRowOn]} onPress={() => setFitEquipment(x.id)}>
                    <Text style={[styles.listRowText, fitEquipment === x.id && styles.listRowTextOn]}>{x.label}</Text>
                </TouchableOpacity>
            ))}
            {attemptE && !fitEquipment ? <Text style={styles.fieldErrorText}>Pick equipment access.</Text> : null}

            <Text style={styles.label}>Days per week</Text>
            <View style={[styles.rowWrap, attemptE && fitDays === null && styles.groupErrorOutline]}>
                {[3, 4, 5, 6].map((d) => (
                    <TouchableOpacity key={d} style={[styles.pill, fitDays === d && styles.pillOn]} onPress={() => setFitDays(d)}>
                        <Text style={[styles.pillText, fitDays === d && styles.pillTextOn]}>{d}</Text>
                    </TouchableOpacity>
                ))}
            </View>
            {attemptE && fitDays === null ? <Text style={styles.fieldErrorText}>Pick days per week.</Text> : null}
        </View>
    );

    const renderF = () => {
        const wakeErr = validateClockHHMM(wakeTime, 'Wake');
        const bedErr = validateClockHHMM(bedTime, 'Bed');
        const workoutErr = showWorkoutTime ? validateClockHHMM(workoutTime, 'Workout') : null;
        const showWakeErr = attemptF && wakeErr !== null;
        const showBedErr = attemptF && bedErr !== null;
        const showWorkoutErr = attemptF && showWorkoutTime && workoutErr !== null;
        const showScreenErr = attemptF && !screenBand;
        const selectTime = (which: 'wake' | 'bed' | 'workout', value: string) => {
            if (which === 'wake') setWakeTime(value);
            if (which === 'bed') setBedTime(value);
            if (which === 'workout') setWorkoutTime(value);
            setOpenTimePicker(null);
        };
        const timeRow = (
            label: string,
            which: 'wake' | 'bed' | 'workout',
            value: string,
            hasErr: boolean,
            errText: string | null
        ) => (
            <>
                <Text style={styles.label}>{label}</Text>
                <TouchableOpacity
                    style={[styles.input, styles.timeSelectTrigger, hasErr && styles.inputError]}
                    activeOpacity={0.85}
                    onPress={() => setOpenTimePicker((prev) => (prev === which ? null : which))}
                >
                    <Text style={styles.timeSelectText}>{formatTime12h(value)}</Text>
                    <Ionicons
                        name={openTimePicker === which ? 'chevron-up' : 'chevron-down'}
                        size={18}
                        color={colors.textMuted}
                    />
                </TouchableOpacity>
                {openTimePicker === which ? (
                    <View style={styles.timeDropdown}>
                        <ScrollView nestedScrollEnabled style={styles.timeDropdownScroll}>
                            {TIME_OPTIONS.map((t) => {
                                const active = t === value;
                                return (
                                    <TouchableOpacity
                                        key={`${which}-${t}`}
                                        style={[styles.timeOption, active && styles.timeOptionOn]}
                                        onPress={() => selectTime(which, t)}
                                        activeOpacity={0.8}
                                    >
                                        <Text style={[styles.timeOptionText, active && styles.timeOptionTextOn]}>
                                            {formatTime12h(t)}
                                        </Text>
                                    </TouchableOpacity>
                                );
                            })}
                        </ScrollView>
                    </View>
                ) : null}
                {hasErr && errText ? <Text style={styles.fieldErrorText}>{errText}</Text> : null}
            </>
        );

        return (
            <View style={styles.card}>
                <Text style={styles.kicker}>Rhythm</Text>
                <Text style={styles.h1} numberOfLines={1} ellipsizeMode="tail">
                    Reminder timing
                </Text>
                <Text style={styles.lead}>Choose when daily reminders should appear.</Text>

                {timeRow('Wake', 'wake', wakeTime, showWakeErr, wakeErr)}
                {timeRow('Bed', 'bed', bedTime, showBedErr, bedErr)}

                {showWorkoutTime ? (
                    <>
                        {timeRow('Typical workout start', 'workout', workoutTime, showWorkoutErr, workoutErr)}
                    </>
                ) : null}

                <Text style={styles.label}>Screen time (daily)</Text>
                <View style={[styles.rowWrap, showScreenErr && styles.groupErrorOutline]}>
                    {SCREEN_TIME_BANDS.map((b) => (
                        <TouchableOpacity key={b.id} style={[styles.tag, screenBand === b.id && styles.tagOn]} onPress={() => setScreenBand(b.id)}>
                            <Text style={[styles.tagText, screenBand === b.id && styles.tagTextOn]}>{b.label}</Text>
                        </TouchableOpacity>
                    ))}
                </View>
                {showScreenErr ? <Text style={styles.fieldErrorText}>Pick a rough range.</Text> : null}
            </View>
        );
    };

    const body = () => {
        switch (currentSection) {
            case 'A':
                return renderA();
            case 'B':
                return renderB();
            case 'C':
                return renderC();
            case 'D':
                return renderD();
            case 'E':
                return renderE();
            case 'F':
                return renderF();
            default:
                return null;
        }
    };

    return (
        <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <View style={styles.topBar}>
                <TouchableOpacity onPress={goBack} disabled={stepIndex === 0} style={styles.backHit}>
                    <Ionicons name="chevron-back" size={26} color={stepIndex === 0 ? colors.border : colors.foreground} />
                </TouchableOpacity>
                <View style={styles.dots}>
                    {sections.map((_, i) => (
                        <View key={i} style={[styles.dot, i === stepIndex && styles.dotOn]} />
                    ))}
                </View>
                <View style={{ width: 36 }} />
            </View>

            <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                <Animated.View style={{ opacity: fade }}>{body()}</Animated.View>
            </ScrollView>

            <View style={styles.footer}>
                <TouchableOpacity style={[styles.cta, loading && styles.ctaDisabled]} onPress={goNext} disabled={loading} activeOpacity={0.9}>
                    <Text style={styles.ctaText}>{loading ? 'Saving…' : stepIndex >= totalSteps - 1 ? 'Continue to face scan' : 'Continue'}</Text>
                    <Ionicons name="arrow-forward" size={20} color={colors.background} />
                </TouchableOpacity>
            </View>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.md,
        paddingTop: 56,
        paddingBottom: spacing.sm,
    },
    backHit: { width: 40, height: 40, justifyContent: 'center' },
    dots: { flexDirection: 'row', gap: 6 },
    dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.border },
    dotOn: { backgroundColor: colors.foreground, width: 18 },
    scroll: { paddingHorizontal: spacing.lg, paddingBottom: 120 },
    card: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.sm,
    },
    kicker: { ...typography.label, color: colors.textMuted, marginBottom: spacing.xs, letterSpacing: 1.2 },
    h1: {
        fontSize: 22,
        fontWeight: '700',
        color: colors.foreground,
        letterSpacing: -0.5,
        marginBottom: spacing.sm,
    },
    lead: { fontSize: 15, color: colors.textSecondary, lineHeight: 22, marginBottom: spacing.lg },
    label: { ...typography.label, color: colors.textMuted, marginTop: spacing.lg, marginBottom: spacing.xs },
    input: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        paddingVertical: 14,
        paddingHorizontal: spacing.md,
        fontSize: 17,
        color: colors.foreground,
        borderWidth: 1,
        borderColor: colors.border,
    },
    inputError: { borderColor: colors.error },
    timeSelectTrigger: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    timeSelectText: { fontSize: 17, color: colors.foreground, fontWeight: '600' },
    timeDropdown: {
        marginTop: spacing.xs,
        marginBottom: spacing.xs,
        maxHeight: 220,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        overflow: 'hidden',
    },
    timeDropdownScroll: { maxHeight: 220 },
    timeOption: {
        paddingVertical: 11,
        paddingHorizontal: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.borderLight,
    },
    timeOptionOn: { backgroundColor: colors.accentMuted },
    timeOptionText: { fontSize: 15, color: colors.textSecondary, fontWeight: '600' },
    timeOptionTextOn: { color: colors.foreground },
    fieldErrorText: { fontSize: 12, color: colors.error, marginTop: spacing.xs },
    groupErrorOutline: { borderWidth: 1, borderColor: colors.error, borderRadius: borderRadius.lg, padding: spacing.sm },
    /** Keeps ft/in inside the card — flex + minWidth 0 avoids TextInput overflow. */
    heightRowImperial: {
        flexDirection: 'row',
        gap: spacing.sm,
        alignSelf: 'stretch',
        width: '100%',
    },
    heightSplitInput: {
        flex: 1,
        minWidth: 0,
        flexShrink: 1,
    },
    rowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    pill: {
        paddingHorizontal: 16,
        paddingVertical: 10,
        borderRadius: borderRadius.full,
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
    },
    pillOn: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    pillText: { fontSize: 14, fontWeight: '600', color: colors.textSecondary },
    pillTextOn: { color: colors.background },
    unitRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.md },
    unitToggle: { flexDirection: 'row', gap: 8 },
    unitChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: borderRadius.full, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    unitChipOn: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    unitChipText: { fontSize: 12, fontWeight: '600', color: colors.textMuted },
    unitChipTextOn: { color: colors.background },
    tag: {
        paddingHorizontal: 14,
        paddingVertical: 10,
        borderRadius: borderRadius.full,
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
    },
    tagOn: { borderColor: colors.foreground, backgroundColor: colors.accentMuted },
    tagText: { fontSize: 13, fontWeight: '600', color: colors.textSecondary },
    tagTextOn: { color: colors.foreground },
    rankRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        marginBottom: spacing.sm,
        borderWidth: 1,
        borderColor: colors.border,
    },
    rankNum: { width: 28, fontSize: 16, fontWeight: '800', color: colors.textMuted },
    rankLabel: { flex: 1, fontSize: 16, fontWeight: '600', color: colors.foreground },
    rankArrows: { flexDirection: 'row' },
    iconBtn: { padding: 6 },
    listRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingVertical: 14,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.lg,
        backgroundColor: colors.card,
        marginBottom: spacing.xs,
        borderWidth: 1,
        borderColor: colors.border,
    },
    listRowOn: { borderColor: colors.foreground, backgroundColor: colors.accentMuted },
    listRowText: { fontSize: 15, fontWeight: '500', color: colors.foreground, flex: 1 },
    listRowTextOn: { fontWeight: '700' },
    banner: {
        backgroundColor: colors.accentMuted,
        padding: spacing.md,
        borderRadius: borderRadius.lg,
        fontSize: 13,
        color: colors.foreground,
        marginBottom: spacing.md,
        overflow: 'hidden',
    },
    footer: {
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 0,
        padding: spacing.lg,
        paddingBottom: 28,
        backgroundColor: colors.background,
        borderTopWidth: 1,
        borderTopColor: colors.border,
    },
    cta: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: 16,
        borderRadius: borderRadius.full,
        ...shadows.md,
    },
    ctaDisabled: { opacity: 0.65 },
    ctaText: { ...typography.button, color: colors.background, fontSize: 16 },
});
