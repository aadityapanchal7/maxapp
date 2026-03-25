import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, LayoutChangeEvent } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography, borderRadius } from '../../theme/dark';

interface Props {
    currentStep: number;
}

const ANALYSIS_STEPS = [
    'Uploading your photos',
    'Scoring your facial metrics',
    'Preparing your scan summary',
];

/** Map discrete step → target % (Cal-AI style milestones) */
function targetProgressForStep(step: number): number {
    if (step <= 0) return 22;
    if (step === 1) return 58;
    return 94;
}

/** Slow climb with pauses: moves a bit, “hangs”, then continues (repeat) */
function buildStutterSequence(anim: Animated.Value, from: number, to: number, pieceCount: number): Animated.CompositeAnimation {
    if (to <= from + 0.5) {
        return Animated.timing(anim, { toValue: to, duration: 400, useNativeDriver: false });
    }
    const anims: Animated.CompositeAnimation[] = [];
    for (let i = 1; i <= pieceCount; i++) {
        const next = from + ((to - from) * i) / pieceCount;
        anims.push(
            Animated.timing(anim, {
                toValue: next,
                duration: 950 + i * 110,
                useNativeDriver: false,
            }),
        );
        // “Caught up” pause — varies so it feels uneven, not mechanical
        const pauseMs = 320 + (i % 4) * 140 + (i % 2) * 90;
        anims.push(Animated.delay(pauseMs));
    }
    return Animated.sequence(anims);
}

export default function AnalyzingScreen({ currentStep = 0 }: Props) {
    const insets = useSafeAreaInsets();
    const [trackWidth, setTrackWidth] = useState(0);
    const progressAnim = useRef(new Animated.Value(0)).current;
    const displayedPct = useRef(0);
    const [pctLabel, setPctLabel] = useState(0);
    const stutterHandle = useRef<Animated.CompositeAnimation | null>(null);

    const [dots] = useState([new Animated.Value(1), new Animated.Value(0.3), new Animated.Value(0.3)]);

    useEffect(() => {
        const listenerId = progressAnim.addListener(({ value }) => {
            const p = Math.min(100, Math.max(0, Math.round(value)));
            if (p !== displayedPct.current) {
                displayedPct.current = p;
                setPctLabel(p);
            }
        });
        return () => progressAnim.removeListener(listenerId);
    }, [progressAnim]);

    useEffect(() => {
        const target = targetProgressForStep(currentStep);
        stutterHandle.current?.stop?.();

        progressAnim.stopAnimation((startVal) => {
            const from = typeof startVal === 'number' ? Math.min(100, Math.max(0, startVal)) : 0;
            if (from > target) {
                const snap = Animated.timing(progressAnim, { toValue: target, duration: 350, useNativeDriver: false });
                stutterHandle.current = snap;
                snap.start();
                return;
            }
            const pieceCount = currentStep >= 2 ? 7 : 6;
            const main = buildStutterSequence(progressAnim, from, target, pieceCount);
            stutterHandle.current = main;
            main.start(({ finished }) => {
                if (!finished) return;
                // After the last pipeline step, crawl to 100% with extra stutters (upload may finish first)
                if (currentStep >= 2 && target >= 94) {
                    progressAnim.stopAnimation((v) => {
                        const v0 = typeof v === 'number' ? v : 94;
                        const to100 = buildStutterSequence(progressAnim, Math.max(v0, 94), 100, 8);
                        stutterHandle.current = to100;
                        to100.start();
                    });
                }
            });
        });

        return () => {
            stutterHandle.current?.stop?.();
        };
    }, [currentStep, progressAnim]);

    useEffect(() => {
        const animateDots = () => {
            Animated.sequence([
                Animated.timing(dots[0], { toValue: 1, duration: 300, useNativeDriver: true }),
                Animated.timing(dots[1], { toValue: 1, duration: 300, useNativeDriver: true }),
                Animated.timing(dots[2], { toValue: 1, duration: 300, useNativeDriver: true }),
            ]).start(() => {
                dots.forEach((d) => d.setValue(0.3));
                animateDots();
            });
        };
        animateDots();
    }, []);

    const onTrackLayout = (e: LayoutChangeEvent) => {
        setTrackWidth(e.nativeEvent.layout.width);
    };

    const fillWidth =
        trackWidth > 0
            ? progressAnim.interpolate({
                  inputRange: [0, 100],
                  outputRange: [0, trackWidth],
                  extrapolate: 'clamp',
              })
            : 0;

    return (
        <View style={styles.container}>
            <View
                style={[
                    styles.progressHeader,
                    { paddingTop: Math.max(insets.top, 12) + 28 },
                ]}
            >
                <View style={styles.progressTopRow}>
                    <Text style={styles.progressTitle}>Analyzing</Text>
                    <Text style={styles.progressPct}>{pctLabel}%</Text>
                </View>
                <View style={styles.trackWrap}>
                    <View style={styles.track} onLayout={onTrackLayout}>
                        <Animated.View style={[styles.trackFill, { width: fillWidth }]} />
                    </View>
                </View>
            </View>

            <View style={styles.gridBox}>
                <View style={styles.gridInner}>
                    {[...Array(6)].map((_, row) => (
                        <View key={row} style={styles.gridRow}>
                            {[...Array(6)].map((_, col) => (
                                <View key={col} style={styles.gridCell} />
                            ))}
                        </View>
                    ))}
                </View>
            </View>

            <View style={styles.stepsContainer}>
                {ANALYSIS_STEPS.map((step, index) => {
                    const isCompleted = index < currentStep;
                    const isActive = index === currentStep;
                    return (
                        <View key={index} style={styles.stepRow}>
                            {isCompleted ? (
                                <Ionicons name="checkmark" size={16} color={colors.foreground} />
                            ) : isActive ? (
                                <Ionicons name="sync" size={16} color={colors.foreground} />
                            ) : (
                                <View style={styles.emptyIcon} />
                            )}
                            <Text
                                style={[
                                    styles.stepText,
                                    isCompleted && styles.stepTextCompleted,
                                    isActive && styles.stepTextActive,
                                    !isCompleted && !isActive && styles.stepTextPending,
                                ]}
                            >
                                {step}
                            </Text>
                        </View>
                    );
                })}
            </View>

            <View style={styles.dotsContainer}>
                {dots.map((opacity, index) => (
                    <Animated.View key={index} style={[styles.dot, { opacity }]} />
                ))}
            </View>

            <View style={[styles.footer, { bottom: Math.max(insets.bottom, 20) + 24 }]}>
                <Text style={styles.footerText}>
                    AI is generating your maximum potential based on{'\n'}
                    <Text style={styles.footerHighlight}>50k+ successful transformations</Text>
                </Text>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, alignItems: 'center', paddingHorizontal: spacing.lg, backgroundColor: colors.background },
    progressHeader: {
        alignSelf: 'stretch',
        marginBottom: spacing.lg,
    },
    progressTopRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: 4,
    },
    trackWrap: {
        marginTop: 22,
    },
    progressTitle: { ...typography.h3, fontSize: 20 },
    progressPct: { fontSize: 22, fontWeight: '800', color: colors.foreground, letterSpacing: -0.5 },
    track: {
        height: 10,
        borderRadius: borderRadius.full,
        backgroundColor: colors.borderLight,
        overflow: 'hidden',
    },
    trackFill: {
        height: '100%',
        borderRadius: borderRadius.full,
        backgroundColor: colors.foreground,
    },
    gridBox: { width: 260, height: 260, borderWidth: 1, borderColor: colors.border, borderStyle: 'dashed', borderRadius: 8, padding: 20, marginBottom: spacing.xl },
    gridInner: { flex: 1, justifyContent: 'space-between' },
    gridRow: { flexDirection: 'row', justifyContent: 'space-between' },
    gridCell: { width: 4, height: 4, backgroundColor: colors.border, borderRadius: 2 },
    stepsContainer: { alignItems: 'flex-start', marginBottom: spacing.xl },
    stepRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md, gap: spacing.sm },
    emptyIcon: { width: 16, height: 16 },
    stepText: { fontSize: 15, color: colors.textMuted },
    stepTextCompleted: { color: colors.foreground },
    stepTextActive: { color: colors.foreground, fontWeight: '600' },
    stepTextPending: { color: colors.textMuted },
    dotsContainer: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xxl },
    dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.foreground },
    footer: { position: 'absolute', paddingHorizontal: spacing.lg },
    footerText: { fontSize: 13, color: colors.textMuted, textAlign: 'center', lineHeight: 20 },
    footerHighlight: { fontWeight: '600', color: colors.foreground },
});
