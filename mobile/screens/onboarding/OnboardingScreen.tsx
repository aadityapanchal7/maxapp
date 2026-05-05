/**
 * Onboarding — minimalist, centered, one question per page.
 *
 * Layout principles:
 *   - Content vertically centered in the viewport
 *   - Max-width container (~380 px) so the content never sprawls
 *   - One visual focus per page: title + input. No fluff.
 *   - Tiny progress dots at top, sticky CTA at bottom
 *   - Big Playfair serif for the question; sans for everything else
 *   - Soft fade-in on each step (no slide), 220 ms
 *
 * Steps: gender → age → height → weight → priority ranking
 *
 * Data shape on save:
 *   gender:           'male' | 'female' | 'other' | 'prefer_not_to_say'
 *   age:              number (13–100)
 *   height_cm:        canonical metric height
 *   weight_kg:        canonical metric weight
 *   unit_system:      'metric' | 'imperial'
 *   priority_ranking: string[]   (max-id keys, ordered #1 → #5)
 *   goals:            top 3 of priority_ranking
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

const PRIORITIES: { id: PriorityKey; label: string }[] = [
    { id: 'bonemax',   label: 'Bone structure' },
    { id: 'skinmax',   label: 'Skin quality' },
    { id: 'heightmax', label: 'Height' },
    { id: 'fitmax',    label: 'Physique' },
    { id: 'hairmax',   label: 'Hair quality' },
];

const STEP_TITLES = [
    'How do you identify?',
    'How old are you?',
    'How tall are you?',
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

    const [step, setStep] = useState(0);
    const [submitting, setSubmitting] = useState(false);

    const [gender, setGender] = useState<Gender | null>(null);
    const [age, setAge] = useState(22);
    const [unit, setUnit] = useState<UnitSystem>('imperial');
    const [heightCm, setHeightCm] = useState(178);
    const [weightKg, setWeightKg] = useState(72);
    const [priority, setPriority] = useState<PriorityKey[]>([]);

    const valid: boolean[] = [
        gender !== null,
        age >= 13 && age <= 100,
        heightCm >= 120 && heightCm <= 230,
        weightKg >= 30 && weightKg <= 230,
        priority.length === PRIORITIES.length,
    ];

    /* Soft fade between steps — no horizontal motion. Quieter than a slide,
       reads as a gentle transition rather than navigation. */
    const fade = useRef(new Animated.Value(1)).current;
    const animate = useCallback(
        (after: () => void) => {
            Animated.timing(fade, {
                toValue: 0,
                duration: 130,
                useNativeDriver: true,
                easing: Easing.out(Easing.quad),
            }).start(() => {
                after();
                Animated.timing(fade, {
                    toValue: 1,
                    duration: 220,
                    useNativeDriver: true,
                    easing: Easing.out(Easing.cubic),
                }).start();
            });
        },
        [fade]
    );

    const goNext = useCallback(() => {
        if (!valid[step]) return;
        if (step >= STEP_COUNT - 1) {
            void submit();
            return;
        }
        animate(() => setStep((s) => s + 1));
    }, [valid, step, animate]);  // eslint-disable-line react-hooks/exhaustive-deps

    const goBack = useCallback(() => {
        if (step <= 0) {
            navigation.goBack();
            return;
        }
        animate(() => setStep((s) => s - 1));
    }, [step, animate, navigation]);

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
                // @ts-expect-error — backend allows passthrough fields
                priority_ranking: priority,
                // @ts-expect-error
                height_cm: heightCm,
                // @ts-expect-error
                weight_kg: weightKg,
            });
            await refreshUser();
            navigation.reset({ index: 0, routes: [{ name: 'FeaturesIntro' }] });
        } catch (e) {
            console.error('onboarding save failed', e);
            setSubmitting(false);
        }
    };

    const renderStep = () => {
        switch (step) {
            case 0:
                return (
                    <GenderStep
                        value={gender}
                        onChange={(g) => {
                            setGender(g);
                            // light delay so the selection registers visually
                            setTimeout(goNext, 200);
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
        <View style={styles.root}>
            {/* ── Top: back + dots ─────────────────────────────────── */}
            <View style={[styles.topBar, { paddingTop: Math.max(insets.top + spacing.md, 44) }]}>
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

            {/* ── Centered content ─────────────────────────────────── */}
            <View style={styles.center}>
                <Animated.View style={[styles.card, { opacity: fade }]}>
                    <Text style={styles.question}>{STEP_TITLES[step]}</Text>
                    <View style={styles.body}>{renderStep()}</View>
                </Animated.View>
            </View>

            {/* ── CTA ───────────────────────────────────────────────── */}
            <View
                style={[
                    styles.footer,
                    { paddingBottom: Math.max(insets.bottom + spacing.sm, spacing.lg) },
                ]}
            >
                <TouchableOpacity
                    style={[styles.cta, !valid[step] && styles.ctaDisabled]}
                    onPress={goNext}
                    disabled={!valid[step] || submitting}
                    activeOpacity={0.85}
                >
                    <Text style={styles.ctaText}>
                        {submitting ? 'Saving…' : step === STEP_COUNT - 1 ? 'Continue' : 'Next'}
                    </Text>
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
        <View style={{ gap: 10, alignSelf: 'stretch' }}>
            {GENDERS.map((g) => {
                const on = value === g.id;
                return (
                    <TouchableOpacity
                        key={g.id}
                        style={[styles.option, on && styles.optionOn]}
                        activeOpacity={0.6}
                        onPress={() => onChange(g.id)}
                    >
                        <Text style={[styles.optionLabel, on && styles.optionLabelOn]}>{g.label}</Text>
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
        <View style={styles.numberStep}>
            <Text style={styles.bigNumber}>{value}</Text>
            <Text style={styles.unit}>years</Text>
            <Slider min={13} max={100} value={value} onChange={onChange} />
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
        <View style={styles.numberStep}>
            <UnitToggle unit={unit} onChange={onChangeUnit} labels={['cm', 'ft / in']} />
            {unit === 'metric' ? (
                <>
                    <Text style={styles.bigNumber}>{cm}</Text>
                    <Text style={styles.unit}>cm</Text>
                </>
            ) : (
                <View style={styles.inlineUnits}>
                    <Text style={styles.bigNumber}>{ft}</Text>
                    <Text style={[styles.unit, styles.unitInline]}>ft</Text>
                    <Text style={styles.bigNumber}>{inch}</Text>
                    <Text style={[styles.unit, styles.unitInline]}>in</Text>
                </View>
            )}
            <Slider min={120} max={230} value={cm} onChange={onChangeCm} />
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
        <View style={styles.numberStep}>
            <UnitToggle unit={unit} onChange={onChangeUnit} labels={['kg', 'lb']} />
            <Text style={styles.bigNumber}>{display}</Text>
            <Text style={styles.unit}>{unit === 'metric' ? 'kg' : 'lb'}</Text>
            <Slider min={30} max={230} value={kg} onChange={onChangeKg} />
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
        <View style={{ alignSelf: 'stretch' }}>
            <Text style={styles.helperLine}>tap in order — first = top priority</Text>
            <View style={{ gap: 10, marginTop: spacing.lg }}>
                {PRIORITIES.map((p) => {
                    const idx = value.indexOf(p.id);
                    const on = idx >= 0;
                    return (
                        <TouchableOpacity
                            key={p.id}
                            style={[styles.option, on && styles.optionOn]}
                            activeOpacity={0.6}
                            onPress={() => tap(p.id)}
                        >
                            <Text style={[styles.optionLabel, on && styles.optionLabelOn]}>
                                {p.label}
                            </Text>
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

/**
 * Tiny custom slider — flat track + draggable thumb. Works on iOS, Android,
 * and web via the responder system; no community-slider dependency.
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

const CARD_MAX_WIDTH = 380;

const styles = StyleSheet.create({
    root: {
        flex: 1,
        backgroundColor: colors.background,
    },

    /* top bar */
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
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

    /* centered content */
    center: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: spacing.lg,
    },
    card: {
        width: '100%',
        maxWidth: CARD_MAX_WIDTH,
        alignItems: 'center',
    },
    question: {
        fontFamily: fonts.serif,
        fontSize: 30,
        fontWeight: '400',
        letterSpacing: -0.6,
        lineHeight: 36,
        color: colors.foreground,
        textAlign: 'center',
        marginBottom: spacing.xl,
    },
    body: {
        alignSelf: 'stretch',
        alignItems: 'center',
    },

    /* shared per-step number layout */
    numberStep: {
        alignItems: 'center',
        alignSelf: 'stretch',
    },
    bigNumber: {
        fontFamily: fonts.serif,
        fontSize: 88,
        fontWeight: '400',
        letterSpacing: -3,
        color: colors.foreground,
        lineHeight: 96,
    },
    unit: {
        fontFamily: fonts.sansMedium,
        fontSize: 11,
        letterSpacing: 1.6,
        textTransform: 'uppercase',
        color: colors.textMuted,
        marginTop: 6,
    },
    unitInline: {
        marginHorizontal: 6,
        marginTop: 0,
    },
    inlineUnits: {
        flexDirection: 'row',
        alignItems: 'baseline',
    },

    /* helper text */
    helperLine: {
        fontFamily: fonts.sans,
        fontSize: 12.5,
        color: colors.textSecondary,
        textAlign: 'center',
        letterSpacing: 0.1,
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
        textAlign: 'left',
    },
    optionLabelOn: {
        color: colors.foreground,
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
    rankBadgeOn: {
        borderColor: colors.foreground,
        backgroundColor: colors.foreground,
    },
    rankBadgeText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        color: colors.buttonText,
    },

    /* unit toggle */
    toggleWrap: {
        flexDirection: 'row',
        gap: 4,
        padding: 4,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
        marginBottom: spacing.lg,
    },
    togglePill: {
        paddingHorizontal: spacing.md,
        paddingVertical: 7,
        borderRadius: borderRadius.full,
    },
    togglePillOn: {
        backgroundColor: colors.foreground,
    },
    togglePillText: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        letterSpacing: 0.4,
        color: colors.textSecondary,
    },
    togglePillTextOn: {
        color: colors.buttonText,
    },

    /* slider */
    sliderTrack: {
        marginTop: spacing.xl,
        alignSelf: 'stretch',
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
    footer: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
        alignItems: 'center',
    },
    cta: {
        width: '100%',
        maxWidth: CARD_MAX_WIDTH,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        borderRadius: borderRadius.full,
    },
    ctaDisabled: {
        backgroundColor: colors.border,
    },
    ctaText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.4,
        color: colors.buttonText,
    },
});
