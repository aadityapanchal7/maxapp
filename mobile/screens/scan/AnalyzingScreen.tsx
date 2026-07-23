import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, Easing, TouchableOpacity } from 'react-native';
import { Image as ExpoImage } from 'expo-image';
import Svg, { Circle } from 'react-native-svg';
import { colors, fonts } from '../../theme/dark';

interface Props {
    currentStep: number;
    /** Escape hatch: shown as a muted "Cancel" link after a grace period so a
     *  hung upload/analysis can never hard-trap the user on this screen. */
    onCancel?: () => void;
}

// How long the screen stays escape-free before the Cancel link fades in.
const CANCEL_GRACE_MS = 45_000;

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

// The rotating stylized head (Higgsfield turntable, green-keyed to a TRANSPARENT
// animated WebP). An animated WebP via expo-image auto-plays (no video-autoplay
// flakiness), so it always rotates. A thin progress ring is drawn AROUND it.
const BUST = require('../../assets/bust_rotate.webp');
const BUST_SIZE = 264;
const RING = 300;
const R = 142;
const STROKE = 4;
const CIRC = 2 * Math.PI * R;
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

export default function AnalyzingScreen({ currentStep = 0, onCancel }: Props) {
    const progressAnim = useRef(new Animated.Value(0)).current;
    const [pct, setPct] = useState(0);
    const highWater = useRef(0);
    const activeAnim = useRef<Animated.CompositeAnimation | null>(null);
    const fadeAnim = useRef(new Animated.Value(0.5)).current;
    const [showCancel, setShowCancel] = useState(false);

    // Reveal the escape hatch only after the grace period — a normal scan
    // never sees it, but a hung one always gets a way out.
    useEffect(() => {
        if (!onCancel) return;
        const t = setTimeout(() => setShowCancel(true), CANCEL_GRACE_MS);
        return () => clearTimeout(t);
    }, [onCancel]);

    // Keep the displayed % monotonically increasing.
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

    // Ramp toward the step target, then slowly creep beyond it.
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

    // Gentle breathing on the caption.
    useEffect(() => {
        const loop = Animated.loop(
            Animated.sequence([
                Animated.timing(fadeAnim, { toValue: 0.9, duration: 1900, useNativeDriver: true }),
                Animated.timing(fadeAnim, { toValue: 0.5, duration: 1900, useNativeDriver: true }),
            ]),
        );
        loop.start();
        return () => loop.stop();
    }, [fadeAnim]);

    const dashOffset = progressAnim.interpolate({
        inputRange: [0, 100], outputRange: [CIRC, 0], extrapolate: 'clamp',
    });
    const label = STEP_LABELS[Math.min(currentStep, STEP_LABELS.length - 1)];

    return (
        <View style={st.container}>
            <View style={st.center}>
                {/* Rotating head inside a thin progress ring. */}
                <View style={st.ringWrap}>
                    <Svg width={RING} height={RING} style={st.ringSvg}>
                        <Circle
                            cx={RING / 2}
                            cy={RING / 2}
                            r={R}
                            stroke="rgba(0,0,0,0.10)"
                            strokeWidth={STROKE}
                            fill="none"
                        />
                        <AnimatedCircle
                            cx={RING / 2}
                            cy={RING / 2}
                            r={R}
                            stroke="#000000"
                            strokeWidth={STROKE}
                            strokeLinecap="round"
                            fill="none"
                            strokeDasharray={CIRC}
                            strokeDashoffset={dashOffset}
                        />
                    </Svg>
                    <ExpoImage
                        style={st.bust}
                        source={BUST}
                        contentFit="contain"
                        autoplay
                        pointerEvents="none"
                    />
                </View>

                <Text style={st.pct}>{pct}%</Text>

                <Animated.Text style={[st.label, { opacity: fadeAnim }]}>{label}</Animated.Text>

                <Text style={st.hint}>Keep the app open. This takes a second.</Text>

                {onCancel && showCancel ? (
                    <TouchableOpacity
                        onPress={onCancel}
                        activeOpacity={0.7}
                        hitSlop={{ top: 12, bottom: 12, left: 24, right: 24 }}
                        style={st.cancelBtn}
                    >
                        <Text style={st.cancelText}>Taking longer than usual? Cancel</Text>
                    </TouchableOpacity>
                ) : null}
            </View>
        </View>
    );
}

const st = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#FFFFFF',
    },
    center: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: 32,
    },
    ringWrap: {
        width: RING,
        height: RING,
        alignItems: 'center',
        justifyContent: 'center',
    },
    ringSvg: {
        position: 'absolute',
        transform: [{ rotate: '-90deg' }],
    },
    bust: {
        width: BUST_SIZE,
        height: BUST_SIZE,
        backgroundColor: 'transparent',
    },
    pct: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 34,
        color: '#000000',
        letterSpacing: -1.4,
        marginTop: 26,
        textAlign: 'center',
        includeFontPadding: false,
    },
    label: {
        fontFamily: fonts.sansMedium,
        fontSize: 14.5,
        color: '#444444',
        letterSpacing: 0.2,
        marginTop: 8,
        textAlign: 'center',
    },
    hint: {
        fontFamily: fonts.sans,
        fontSize: 12,
        color: '#888888',
        textAlign: 'center',
        marginTop: 14,
        opacity: 0.7,
    },
    cancelBtn: {
        marginTop: 28,
        paddingVertical: 8,
        paddingHorizontal: 16,
    },
    cancelText: {
        fontFamily: fonts.sansMedium,
        fontSize: 13,
        color: '#888888',
        textAlign: 'center',
        textDecorationLine: 'underline',
    },
});
