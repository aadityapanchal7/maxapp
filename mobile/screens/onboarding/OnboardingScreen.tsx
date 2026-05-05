/**
 * Onboarding — one question per page, slide transitions, editorial layout.
 *
 * Steps: gender → age → height → weight → priority ranking
 *
 * Data shape on save:
 *   gender:           'male' | 'female' | 'other' | 'prefer_not_to_say'
 *   age:              number (13–100)
 *   height (cm):      canonical, always cm in `height_cm`
 *   weight (kg):      canonical, always kg in `weight_kg`
 *   unit_system:      'metric' | 'imperial'
 *   priority_ranking: string[]   (max-id keys, ordered #1 → #5)
 *   goals:            top 3 of priority_ranking (for Home tiles)
 *   completed:        true
 */

import React, { useCallback, useRef, useState } from 'react';
import {
    Animated,
    Easing,
    Platform,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
    type LayoutChangeEvent,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { borderRadius, colors, fonts, spacing, typography } from '../../theme/dark';

/* ── Vocabulary ───────────────────────────────────────────────────────── */

type Gender = 'male' | 'female' | 'other' | 'prefer_not_to_say';
type UnitSystem = 'metric' | 'imperial';
type PriorityKey = 'bonemax' | 'skinmax' | 'heightmax' | 'fitmax' | 'hairmax';

const GENDERS: { id: Gender; label: string }[] = [
    { id: 'male', label: 'Male' },
    { id: 'female', label: 'Female' },
    { id: 'other', label: 'Other' },
    { id: 'prefer_not_to_say', label: 'Prefer not to say' },
];

const PRIORITIES: { id: PriorityKey; label: string; sub: string }[] = [
    { id: 'bonemax',   label: 'Bone structure', sub: 'jaw, midface, structure' },
    { id: 'skinmax',   label: 'Skin quality',   sub: 'skin, barrier, glow' },
    { id: 'heightmax', label: 'Height',         sub: 'posture, decompression' },
    { id: 'fitmax',    label: 'Physique',       sub: 'frame, leanness, v-taper' },
    { id: 'hairmax',   label: 'Hair quality',   sub: 'hairline, density, scalp' },
];

const STEP_TITLES = [
    'How do you identify?',
    'How old are you?',
    "How tall are you?",
    "What's your weight?",
    'What matters most?',
] as const;

const STEP_COUNT = STEP_TITLES.length;

/* ── Conversions ──────────────────────────────────────────────────────── */

const cmToFtIn = (cm: number) => {
    const totalIn = cm / 2.54;
    const ft = Math.floor(totalIn / 12);
    const inch = Math.round(totalIn - ft * 12);
    return inch === 12 ? { ft: ft + 1, inch: 0 } : { ft, inch };
};
const kgToLb = (kg: number) => Math.round(kg * 2.2046);

/* ── Component ────────────────────────────────────────────────────────── */

export default function OnboardingScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { refreshUser } = useAuth();

    /* ── Form state ──────────────────────────────────────────────────── */
    const [step, setStep] = useState(0);
    const [submitting, setSubmitting] = useState(false);

    const [gender, setGender] = useState<Gender | null>(null);
    const [age, setAge] = useState(22);
    const [unit, setUnit] = useState<UnitSystem>('imperial');
    const [heightCm, setHeightCm] = useState(178);  // ~5'10"
    const [weightKg, setWeightKg] = useState(72);   // ~159 lb
    const [priority, setPriority] = useState<PriorityKey[]>([]);

    const valid: boolean[] = [
        gender !== null,
        age >= 13 && age <= 100,
        heightCm >= 120 && heightCm <= 230,
        weightKg >= 30 && weightKg <= 230,
        priority.length === PRIORITIES.length,
    ];

    /* ── Slide transition (fade + tiny x) ───────────────────────────── */
    const fade = useRef(new Animated.Value(1)).current;
    const slide = useRef(new Animated.Value(0)).current;

    const animateOutThen = useCallback(
        (dir: 1 | -1, after: () => void) => {
            Animated.parallel([
                Animated.timing(fade, { toValue: 0, duration: 140, useNativeDriver: true, easing: Easing.out(Easing.quad) }),
                Animated.timing(slide, { toValue: -24 * dir, duration: 140, useNativeDriver: true, easing: Easing.out(Easing.quad) }),
            ]).start(() => {
                after();
                slide.setValue(24 * dir);
                Animated.parallel([
                    Animated.timing(fade, { toValue: 1, duration: 220, useNativeDriver: true, easing: Easing.out(Easing.cubic) }),
                    Animated.timing(slide, { toValue: 0, duration: 220, useNativeDriver: true, easing: Easing.out(Easing.cubic) }),
                ]).start();
            });
        },
        [fade, slide]
    );

    const goNext = useCallback(() => {
        if (!valid[step]) return;
        if (step >= STEP_COUNT - 1) {
            void submit();
            return;
        }
        animateOutThen(1, () => setStep((s) => s + 1));
    }, [valid, step, animateOutThen]);  // eslint-disable-line react-hooks/exhaustive-deps

    const goBack = useCallback(() => {
        if (step <= 0) {
            navigation.goBack();
            return;
        }
        animateOutThen(-1, () => setStep((s) => s - 1));
    }, [step, animateOutThen, navigation]);

    /* ── Submit ─────────────────────────────────────────────────────── */
    const submit = async () => {
        if (submitting) return;
        try {
            setSubmitting(true);
            const heightDisplay = unit === 'metric' ? heightCm : Math.round(heightCm / 2.54);
            const weightDisplay = unit === 'metric' ? weightKg : kgToLb(weightKg);
            const top3 = priority.slice(0, 3);
            await api.saveOnboarding({
                goals: top3,
                experience_level: 'beginner',
                gender: gender || undefined,
                age,
                height: heightDisplay,
                weight: weightDisplay,
                unit_system: unit,
                timezone:
                    typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC',
                completed: true,
                // Extra fields propagate via the JSONB onboarding column.
                // @ts-expect-error — backend allows passthrough fields
                priority_ranking: priority,
                // @ts-expect-error
                height_cm: heightCm,
                // @ts-expect-error
                weight_kg: weightKg,
            });
            await refreshUser();
            // Restore the original pre-pay flow:
            //   Onboarding → FeaturesIntro → FaceScan → FaceScanResults → Payment.
            // Only the *questions* on this screen were meant to change; the
            // post-onboarding sequence stays intact.
            navigation.reset({ index: 0, routes: [{ name: 'FeaturesIntro' }] });
        } catch (e: any) {
            console.error('onboarding save failed', e);
            setSubmitting(false);
        }
    };

    /* ── Step renderer ──────────────────────────────────────────────── */
    const renderStep = () => {
        switch (step) {
            case 0:
                return (
                    <GenderStep
                        value={gender}
                        onChange={(g) => {
                            setGender(g);
                            // small delay to show selection before auto-advance
                            setTimeout(() => goNext(), 220);
                        }}
                    />
                );
            case 1:
                return <AgeStep value={age} onChange={setAge} />;
            case 2:
                return (
                    <HeightStep cm={heightCm} unit={unit} onChangeCm={setHeightCm} onChangeUnit={setUnit} />
                );
            case 3:
                return (
                    <WeightStep kg={weightKg} unit={unit} onChangeKg={setWeightKg} onChangeUnit={setUnit} />
                );
            case 4:
                return <PriorityStep value={priority} onChange={setPriority} />;
        }
        return null;
    };

    return (
        <View style={[styles.root, { paddingTop: Math.max(insets.top + spacing.md, 44) }]}>
            <View style={styles.topBar}>
                <TouchableOpacity
                    onPress={goBack}
                    style={styles.backBtn}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    accessibilityLabel="Back"
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>
                <View style={styles.stepDots}>
                    {Array.from({ length: STEP_COUNT }).map((_, i) => (
                        <View
                            key={i}
                            style={[
                                styles.dot,
                                i === step && styles.dotActive,
                                i < step && styles.dotComplete,
                            ]}
                        />
                    ))}
                </View>
                <View style={{ width: 32 }} />
            </View>

            <Animated.View
                style={[
                    styles.slide,
                    { opacity: fade, transform: [{ translateX: slide }] },
                ]}
            >
                <Text style={styles.eyebrow}>
                    {`${String(step + 1).padStart(2, '0')} / ${String(STEP_COUNT).padStart(2, '0')}`}
                </Text>
                <Text style={styles.question}>{STEP_TITLES[step]}</Text>
                <View style={styles.questionRule} />
                <View style={styles.body}>{renderStep()}</View>
            </Animated.View>

            <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom + spacing.sm, spacing.md) }]}>
                <TouchableOpacity
                    style={[styles.cta, !valid[step] && styles.ctaDisabled]}
                    onPress={goNext}
                    disabled={!valid[step] || submitting}
                    activeOpacity={0.85}
                >
                    <Text style={styles.ctaText}>
                        {submitting ? 'Saving…' : step === STEP_COUNT - 1 ? 'Continue' : 'Next'}
                    </Text>
                    <Ionicons name="arrow-forward" size={15} color={colors.buttonText} />
                </TouchableOpacity>
            </View>
        </View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Step 1 — gender                                                        */
/* ─────────────────────────────────────────────────────────────────────── */

function GenderStep({ value, onChange }: { value: Gender | null; onChange: (g: Gender) => void }) {
    return (
        <View style={{ gap: spacing.sm }}>
            {GENDERS.map((g) => {
                const on = value === g.id;
                return (
                    <TouchableOpacity
                        key={g.id}
                        style={[styles.option, on && styles.optionOn]}
                        activeOpacity={0.65}
                        onPress={() => onChange(g.id)}
                    >
                        <Text style={[styles.optionLabel, on && styles.optionLabelOn]}>{g.label}</Text>
                        {on && <Ionicons name="checkmark" size={18} color={colors.foreground} />}
                    </TouchableOpacity>
                );
            })}
        </View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Step 2 — age                                                           */
/* ─────────────────────────────────────────────────────────────────────── */

function AgeStep({ value, onChange }: { value: number; onChange: (n: number) => void }) {
    return (
        <View style={{ alignItems: 'center', paddingTop: spacing.lg }}>
            <Text style={styles.bigNumber}>{value}</Text>
            <Text style={styles.bigUnit}>years</Text>
            <View style={styles.stepperRow}>
                <Stepper onPress={() => onChange(Math.max(13, value - 1))} icon="remove" />
                <Slider min={13} max={100} value={value} onChange={onChange} />
                <Stepper onPress={() => onChange(Math.min(100, value + 1))} icon="add" />
            </View>
        </View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Step 3 — height                                                        */
/* ─────────────────────────────────────────────────────────────────────── */

function HeightStep({
    cm, unit, onChangeCm, onChangeUnit,
}: {
    cm: number;
    unit: UnitSystem;
    onChangeCm: (cm: number) => void;
    onChangeUnit: (u: UnitSystem) => void;
}) {
    const { ft, inch } = cmToFtIn(cm);
    return (
        <View style={{ alignItems: 'center', paddingTop: spacing.md }}>
            <UnitToggle unit={unit} onChange={onChangeUnit} labels={['cm', 'ft / in']} />
            {unit === 'metric' ? (
                <>
                    <Text style={[styles.bigNumber, { marginTop: spacing.lg }]}>{cm}</Text>
                    <Text style={styles.bigUnit}>cm</Text>
                </>
            ) : (
                <View style={{ flexDirection: 'row', alignItems: 'baseline', marginTop: spacing.lg }}>
                    <Text style={styles.bigNumber}>{ft}</Text>
                    <Text style={[styles.bigUnit, { marginHorizontal: 8 }]}>ft</Text>
                    <Text style={styles.bigNumber}>{inch}</Text>
                    <Text style={[styles.bigUnit, { marginLeft: 8 }]}>in</Text>
                </View>
            )}
            <View style={styles.stepperRow}>
                <Stepper onPress={() => onChangeCm(Math.max(120, cm - 1))} icon="remove" />
                <Slider min={120} max={230} value={cm} onChange={onChangeCm} />
                <Stepper onPress={() => onChangeCm(Math.min(230, cm + 1))} icon="add" />
            </View>
        </View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Step 4 — weight                                                        */
/* ─────────────────────────────────────────────────────────────────────── */

function WeightStep({
    kg, unit, onChangeKg, onChangeUnit,
}: {
    kg: number;
    unit: UnitSystem;
    onChangeKg: (kg: number) => void;
    onChangeUnit: (u: UnitSystem) => void;
}) {
    const display = unit === 'metric' ? kg : kgToLb(kg);
    return (
        <View style={{ alignItems: 'center', paddingTop: spacing.md }}>
            <UnitToggle unit={unit} onChange={onChangeUnit} labels={['kg', 'lb']} />
            <Text style={[styles.bigNumber, { marginTop: spacing.lg }]}>{display}</Text>
            <Text style={styles.bigUnit}>{unit === 'metric' ? 'kg' : 'lb'}</Text>
            <View style={styles.stepperRow}>
                <Stepper onPress={() => onChangeKg(Math.max(30, kg - 1))} icon="remove" />
                <Slider min={30} max={230} value={kg} onChange={onChangeKg} />
                <Stepper onPress={() => onChangeKg(Math.min(230, kg + 1))} icon="add" />
            </View>
        </View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Step 5 — priority                                                      */
/* ─────────────────────────────────────────────────────────────────────── */

function PriorityStep({
    value, onChange,
}: {
    value: PriorityKey[];
    onChange: (next: PriorityKey[]) => void;
}) {
    const tap = (id: PriorityKey) => {
        if (value.includes(id)) {
            onChange(value.filter((v) => v !== id));
        } else {
            onChange([...value, id]);
        }
    };
    return (
        <View>
            <Text style={styles.helperLine}>Tap in order. First = highest priority.</Text>
            <View style={{ gap: spacing.sm, marginTop: spacing.md }}>
                {PRIORITIES.map((p) => {
                    const idx = value.indexOf(p.id);
                    const on = idx >= 0;
                    return (
                        <TouchableOpacity
                            key={p.id}
                            style={[styles.option, on && styles.optionOn]}
                            activeOpacity={0.65}
                            onPress={() => tap(p.id)}
                        >
                            <View style={{ flex: 1 }}>
                                <Text style={[styles.optionLabel, on && styles.optionLabelOn]}>
                                    {p.label}
                                </Text>
                                <Text style={styles.optionSub}>{p.sub}</Text>
                            </View>
                            <View style={[styles.rankBadge, on && styles.rankBadgeOn]}>
                                {on ? <Text style={styles.rankBadgeText}>{idx + 1}</Text> : null}
                            </View>
                        </TouchableOpacity>
                    );
                })}
            </View>
        </View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Primitives                                                             */
/* ─────────────────────────────────────────────────────────────────────── */

function UnitToggle({
    unit, onChange, labels,
}: {
    unit: UnitSystem;
    onChange: (u: UnitSystem) => void;
    labels: [string, string];
}) {
    return (
        <View style={styles.toggleWrap}>
            {(['metric', 'imperial'] as UnitSystem[]).map((u, i) => {
                const on = u === unit;
                return (
                    <TouchableOpacity
                        key={u}
                        style={[styles.togglePill, on && styles.togglePillOn]}
                        activeOpacity={0.7}
                        onPress={() => onChange(u)}
                    >
                        <Text style={[styles.togglePillText, on && styles.togglePillTextOn]}>
                            {labels[i]}
                        </Text>
                    </TouchableOpacity>
                );
            })}
        </View>
    );
}

function Stepper({ onPress, icon }: { onPress: () => void; icon: 'add' | 'remove' }) {
    return (
        <TouchableOpacity onPress={onPress} style={styles.stepper} activeOpacity={0.65}>
            <Ionicons name={icon} size={18} color={colors.foreground} />
        </TouchableOpacity>
    );
}

/**
 * Tiny custom slider — flat track + draggable thumb. Avoids
 * @react-native-community/slider which has spotty web support; uses
 * the responder system so it works on iOS / Android / web.
 */
function Slider({
    min, max, value, onChange,
}: {
    min: number; max: number; value: number; onChange: (n: number) => void;
}) {
    const [trackWidth, setTrackWidth] = useState(0);
    const onLayout = (e: LayoutChangeEvent) => setTrackWidth(e.nativeEvent.layout.width);
    const range = max - min;
    const ratio = trackWidth > 0 ? (value - min) / range : 0;
    const thumbX = ratio * trackWidth;

    const handle = useCallback(
        (locX: number) => {
            if (trackWidth <= 0) return;
            const clamped = Math.max(0, Math.min(trackWidth, locX));
            onChange(Math.round(min + (clamped / trackWidth) * range));
        },
        [trackWidth, min, range, onChange]
    );

    return (
        <View
            style={styles.sliderTrack}
            onLayout={onLayout}
            // @ts-ignore — onResponder* on View
            onStartShouldSetResponder={() => true}
            onMoveShouldSetResponder={() => true}
            onResponderGrant={(e) => handle(e.nativeEvent.locationX)}
            onResponderMove={(e) => handle(e.nativeEvent.locationX)}
        >
            <View style={[styles.sliderFill, { width: thumbX }]} />
            <View style={[styles.sliderThumb, { left: Math.max(0, thumbX - 11) }]} />
        </View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Styles                                                                 */
/* ─────────────────────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
    root: {
        flex: 1,
        backgroundColor: colors.background,
        paddingHorizontal: spacing.lg,
    },

    /* top bar */
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: spacing.lg,
    },
    backBtn: {
        width: 32,
        height: 32,
        alignItems: 'flex-start',
        justifyContent: 'center',
        marginLeft: -4,
    },
    stepDots: {
        flexDirection: 'row',
        gap: 6,
        alignItems: 'center',
    },
    dot: {
        width: 6,
        height: 6,
        borderRadius: 3,
        backgroundColor: colors.border,
    },
    dotActive: {
        width: 24,
        backgroundColor: colors.foreground,
    },
    dotComplete: {
        backgroundColor: colors.foreground,
    },

    /* slide */
    slide: { flex: 1 },
    eyebrow: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        letterSpacing: 1.6,
        color: colors.textMuted,
        marginBottom: 10,
    },
    question: {
        fontFamily: fonts.serif,
        fontSize: 32,
        fontWeight: '400',
        letterSpacing: -0.6,
        lineHeight: 38,
        color: colors.foreground,
        marginBottom: 12,
    },
    questionRule: {
        width: 28,
        height: 2,
        borderRadius: 1,
        backgroundColor: colors.foreground,
        marginBottom: spacing.xl,
    },
    body: { flex: 1 },

    helperLine: {
        fontFamily: fonts.sans,
        fontSize: 13,
        color: colors.textSecondary,
        lineHeight: 19,
    },

    /* options (gender + priority) */
    option: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.md,
        paddingVertical: 14,
        borderRadius: borderRadius.md,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        backgroundColor: colors.card,
    },
    optionOn: {
        borderColor: colors.foreground,
        backgroundColor: colors.surfaceLight,
    },
    optionLabel: {
        flex: 1,
        fontFamily: fonts.sansMedium,
        fontSize: 15,
        color: colors.textPrimary,
        letterSpacing: -0.05,
    },
    optionLabelOn: { color: colors.foreground },
    optionSub: {
        ...typography.caption,
        marginTop: 2,
        textTransform: 'none',
        letterSpacing: 0,
    },
    rankBadge: {
        width: 22,
        height: 22,
        borderRadius: 11,
        borderWidth: 1,
        borderColor: colors.border,
        alignItems: 'center',
        justifyContent: 'center',
    },
    rankBadgeOn: { borderColor: colors.foreground, backgroundColor: colors.foreground },
    rankBadgeText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        color: colors.buttonText,
    },

    /* big number display */
    bigNumber: {
        fontFamily: fonts.serif,
        fontSize: 88,
        fontWeight: '400',
        letterSpacing: -3,
        color: colors.foreground,
        lineHeight: 96,
    },
    bigUnit: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        letterSpacing: 1.6,
        textTransform: 'uppercase',
        color: colors.textMuted,
        marginTop: 4,
    },

    /* unit toggle */
    toggleWrap: {
        flexDirection: 'row',
        gap: 4,
        padding: 4,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
        marginBottom: 4,
    },
    togglePill: {
        paddingHorizontal: spacing.md,
        paddingVertical: 7,
        borderRadius: borderRadius.full,
    },
    togglePillOn: { backgroundColor: colors.foreground },
    togglePillText: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        letterSpacing: 0.4,
        color: colors.textSecondary,
    },
    togglePillTextOn: { color: colors.buttonText },

    /* slider + steppers */
    stepperRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        marginTop: spacing.xl,
        width: '100%',
        paddingHorizontal: 4,
    },
    stepper: {
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        backgroundColor: colors.card,
    },
    sliderTrack: {
        flex: 1,
        height: 22,
        justifyContent: 'center',
    },
    sliderFill: {
        position: 'absolute',
        left: 0,
        height: 2,
        backgroundColor: colors.foreground,
        borderRadius: 1,
    },
    sliderThumb: {
        position: 'absolute',
        top: 0,
        width: 22,
        height: 22,
        borderRadius: 11,
        backgroundColor: colors.foreground,
        ...(Platform.OS === 'ios'
            ? { shadowColor: '#18181b', shadowOpacity: 0.16, shadowRadius: 4, shadowOffset: { width: 0, height: 2 } }
            : { elevation: 3 }),
    },

    /* footer / CTA */
    footer: { paddingTop: spacing.md },
    cta: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        borderRadius: borderRadius.full,
    },
    ctaDisabled: { backgroundColor: colors.border },
    ctaText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.4,
        color: colors.buttonText,
    },
});
