import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, LayoutChangeEvent, Easing } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, spacing, fonts } from '../../theme/dark';

interface Props {
    currentStep: number;
}

const STEP_LABELS = [
    'Uploading your photos',
    'Building your facial profile',
    'Preparing your results',
];

function targetForStep(step: number): number {
    if (step <= 0) return 22;
    if (step === 1) return 58;
    return 94;
}

function creepCeiling(step: number): number {
    if (step <= 0) return 38;
    if (step === 1) return 80;
    return 100;
}

export default function AnalyzingScreen({ currentStep = 0 }: Props) {
    const insets = useSafeAreaInsets();
    const [trackWidth, setTrackWidth] = useState(0);
    const progressAnim = useRef(new Animated.Value(0)).current;
    const [pct, setPct] = useState(0);
    const highWater = useRef(0);
    const activeAnim = useRef<Animated.CompositeAnimation | null>(null);

    const fadeAnim = useRef(new Animated.Value(0.4)).current;
    const ringSpin = useRef(new Animated.Value(0)).current;
    const ringSpinRev = useRef(new Animated.Value(0)).current;
    const heroBreath = useRef(new Animated.Value(1)).current;

    // Listen to animated value and keep displayed % monotonically increasing
    useEffect(() => {
        const id = progressAnim.addListener(({ value }) => {
            const clamped = Math.min(100, Math.max(0, value));
            const safe = Math.max(clamped, highWater.current);
            const rounded = Math.round(safe);
            if (rounded > highWater.current) highWater.current = rounded;
            if (rounded !== pct) setPct(rounded);
        });
        return () => progressAnim.removeListener(id);
    }, [progressAnim]);

    // Animate progress toward target when step changes, then slowly creep beyond
    useEffect(() => {
        const target = targetForStep(currentStep);
        const ceiling = creepCeiling(currentStep);
        activeAnim.current?.stop();

        const startTail = (from: number) => {
            if (from >= ceiling) return;
            const remaining = ceiling - from;
            const tailDur = currentStep >= 2
                ? Math.max(8000, remaining * 600)
                : Math.max(20000, remaining * 1400);
            const tail = Animated.timing(progressAnim, {
                toValue: ceiling,
                duration: tailDur,
                easing: Easing.out(Easing.quad),
                useNativeDriver: false,
            });
            activeAnim.current = tail;
            tail.start();
        };

        progressAnim.stopAnimation((raw) => {
            const from = Math.max(typeof raw === 'number' ? raw : 0, highWater.current);
            if (from >= target) {
                startTail(from);
                return;
            }

            const dist = target - from;
            const dur = currentStep >= 2
                ? Math.max(4000, dist * 150)
                : Math.max(10000, dist * 260);

            const ramp = Animated.timing(progressAnim, {
                toValue: target, duration: dur, useNativeDriver: false,
            });
            activeAnim.current = ramp;
            ramp.start(({ finished }) => {
                if (!finished) return;
                startTail(target);
            });
        });

        return () => { activeAnim.current?.stop(); };
    }, [currentStep, progressAnim]);

    // Subtle breathing on the step label
    useEffect(() => {
        const loop = Animated.loop(
            Animated.sequence([
                Animated.timing(fadeAnim, { toValue: 0.8, duration: 2000, useNativeDriver: true }),
                Animated.timing(fadeAnim, { toValue: 0.4, duration: 2000, useNativeDriver: true }),
            ]),
        );
        loop.start();
        return () => loop.stop();
    }, [fadeAnim]);

    // Slow counter-rotating rings — calm, premium motion (native driver)
    useEffect(() => {
        const cw = Animated.loop(
            Animated.timing(ringSpin, {
                toValue: 1,
                duration: 28000,
                easing: Easing.linear,
                useNativeDriver: true,
            }),
        );
        const ccw = Animated.loop(
            Animated.timing(ringSpinRev, {
                toValue: 1,
                duration: 22000,
                easing: Easing.linear,
                useNativeDriver: true,
            }),
        );
        cw.start();
        ccw.start();
        return () => {
            cw.stop();
            ccw.stop();
        };
    }, [ringSpin, ringSpinRev]);

    // Very gentle scale pulse on the hero number cluster
    useEffect(() => {
        const loop = Animated.loop(
            Animated.sequence([
                Animated.timing(heroBreath, {
                    toValue: 1.02,
                    duration: 3200,
                    easing: Easing.inOut(Easing.quad),
                    useNativeDriver: true,
                }),
                Animated.timing(heroBreath, {
                    toValue: 1,
                    duration: 3200,
                    easing: Easing.inOut(Easing.quad),
                    useNativeDriver: true,
                }),
            ]),
        );
        loop.start();
        return () => loop.stop();
    }, [heroBreath]);

    const onTrackLayout = (e: LayoutChangeEvent) => setTrackWidth(e.nativeEvent.layout.width);

    const fillWidth = trackWidth > 0
        ? progressAnim.interpolate({ inputRange: [0, 100], outputRange: [0, trackWidth], extrapolate: 'clamp' })
        : 0;

    const label = STEP_LABELS[Math.min(currentStep, STEP_LABELS.length - 1)];

    const rotOuter = ringSpin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
    const rotInner = ringSpinRev.interpolate({ inputRange: [0, 1], outputRange: ['360deg', '0deg'] });

    return (
        <View style={st.container}>
            {/* Centered hero — decorative rings + large serif percentage */}
            <View style={[st.hero, { paddingTop: insets.top + 40 }]}>
                <View style={st.heroArt} pointerEvents="none">
                    <Animated.View style={[st.decorRing, st.decorRingOuter, { transform: [{ rotate: rotOuter }] }]} />
                    <Animated.View style={[st.decorRing, st.decorRingMid, { transform: [{ rotate: rotInner }] }]} />
                    <Animated.View style={[st.decorRing, st.decorRingInner, { transform: [{ rotate: rotOuter }] }]} />
                </View>
                <Animated.View style={[st.heroNums, { transform: [{ scale: heroBreath }] }]}>
                    <Text style={st.num}>{pct}</Text>
                    <Text style={st.pctSign}>%</Text>
                </Animated.View>
            </View>

            {/* Bottom strip */}
            <View style={[st.foot, { paddingBottom: Math.max(insets.bottom, 20) + 32 }]}>
                {/* Thin progress line */}
                <View style={st.barWrap} onLayout={onTrackLayout}>
                    <View style={st.barTrack}>
                        <Animated.View style={[st.barFill, { width: fillWidth }]} />
                    </View>
                </View>

                <Animated.Text style={[st.stepText, { opacity: fadeAnim }]}>
                    {label}
                </Animated.Text>

                <Text style={st.hint}>
                    Keep the app open — this takes a moment.
                </Text>
            </View>
        </View>
    );
}

const st = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.background,
    },

    hero: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
    },
    heroArt: {
        ...StyleSheet.absoluteFillObject,
        justifyContent: 'center',
        alignItems: 'center',
    },
    decorRing: {
        position: 'absolute',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.borderLight,
        borderRadius: 9999,
        opacity: 0.55,
    },
    decorRingOuter: {
        width: 280,
        height: 280,
    },
    decorRingMid: {
        width: 220,
        height: 220,
        opacity: 0.4,
    },
    decorRingInner: {
        width: 164,
        height: 164,
        opacity: 0.35,
    },
    heroNums: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    num: {
        fontFamily: fonts.serif,
        fontSize: 108,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -6,
        includeFontPadding: false,
    },
    pctSign: {
        fontFamily: fonts.serif,
        fontSize: 32,
        fontWeight: '400',
        color: colors.textMuted,
        marginLeft: 4,
        marginTop: -36,
        opacity: 0.5,
    },

    foot: {
        paddingHorizontal: spacing.xl + spacing.lg,
    },
    barWrap: {
        marginBottom: spacing.lg,
    },
    barTrack: {
        height: 1.5,
        backgroundColor: colors.borderLight,
        overflow: 'hidden',
    },
    barFill: {
        height: '100%',
        backgroundColor: colors.foreground,
    },
    stepText: {
        fontSize: 13,
        fontWeight: '400',
        color: colors.foreground,
        textAlign: 'center',
        letterSpacing: 0.2,
    },
    hint: {
        fontSize: 11,
        fontWeight: '400',
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: 6,
        opacity: 0.5,
    },
});
