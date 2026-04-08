import React, { useState, useEffect, useRef, useMemo } from 'react';
import { View, Text, StyleSheet, Animated, LayoutChangeEvent } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography, borderRadius, fonts } from '../../theme/dark';

interface Props {
    currentStep: number;
}

const ANALYSIS_STEPS = [
    'Uploading your photos',
    'Building your facial ratings',
    'Preparing your scan summary',
];

const GRID_N = 7;

function targetProgressForStep(step: number): number {
    if (step <= 0) return 22;
    if (step === 1) return 58;
    return 94;
}

function ScanningGrid() {
    const cellOpacities = useMemo(
        () => Array.from({ length: GRID_N * GRID_N }, () => new Animated.Value(0.18)),
        [],
    );

    useEffect(() => {
        const wave = Animated.loop(
            Animated.sequence([
                Animated.stagger(
                    32,
                    cellOpacities.map((v) =>
                        Animated.sequence([
                            Animated.timing(v, { toValue: 1, duration: 340, useNativeDriver: true }),
                            Animated.timing(v, { toValue: 0.2, duration: 380, useNativeDriver: true }),
                        ]),
                    ),
                ),
                Animated.delay(180),
            ]),
        );
        wave.start();
        return () => wave.stop();
    }, [cellOpacities]);

    return (
        <View style={gridStyles.shell}>
            <View style={gridStyles.glow} />
            <View style={gridStyles.grid}>
                {Array.from({ length: GRID_N }).map((_, row) => (
                    <View key={row} style={gridStyles.row}>
                        {Array.from({ length: GRID_N }).map((_, col) => {
                            const idx = row * GRID_N + col;
                            return (
                                <Animated.View key={idx} style={[gridStyles.cell, { opacity: cellOpacities[idx] }]} />
                            );
                        })}
                    </View>
                ))}
            </View>
        </View>
    );
}

const gridStyles = StyleSheet.create({
    shell: {
        width: 240,
        height: 240,
        borderRadius: borderRadius.xl,
        padding: 18,
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderStyle: 'dashed',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'stretch',
        overflow: 'hidden',
    },
    glow: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(17, 17, 19, 0.03)',
        borderRadius: borderRadius.xl,
    },
    grid: {
        width: '100%',
        flex: 1,
        justifyContent: 'center',
        rowGap: 6,
    },
    row: {
        flexDirection: 'row',
        justifyContent: 'center',
        columnGap: 6,
    },
    cell: {
        width: 24,
        height: 24,
        borderRadius: 4,
        backgroundColor: colors.foreground,
    },
});

export default function AnalyzingScreen({ currentStep = 0 }: Props) {
    const insets = useSafeAreaInsets();
    const [trackWidth, setTrackWidth] = useState(0);
    const progressAnim = useRef(new Animated.Value(0)).current;
    const [pctLabel, setPctLabel] = useState(0);
    const highWaterMark = useRef(0);
    const runningAnim = useRef<Animated.CompositeAnimation | null>(null);

    const [dots] = useState([new Animated.Value(1), new Animated.Value(0.3), new Animated.Value(0.3)]);

    useEffect(() => {
        const listenerId = progressAnim.addListener(({ value }) => {
            const clamped = Math.min(100, Math.max(0, value));
            const safe = Math.max(clamped, highWaterMark.current);
            const rounded = Math.round(safe);
            if (rounded > highWaterMark.current) highWaterMark.current = rounded;
            if (rounded !== pctLabel) setPctLabel(rounded);
        });
        return () => progressAnim.removeListener(listenerId);
    }, [progressAnim]);

    useEffect(() => {
        const target = targetProgressForStep(currentStep);
        runningAnim.current?.stop();

        progressAnim.stopAnimation((rawVal) => {
            const from = Math.max(
                typeof rawVal === 'number' ? rawVal : 0,
                highWaterMark.current,
            );
            if (from >= target) {
                if (currentStep >= 2 && from < 100) {
                    const toFull = Animated.timing(progressAnim, {
                        toValue: 100,
                        duration: 12000,
                        useNativeDriver: false,
                    });
                    runningAnim.current = toFull;
                    toFull.start();
                }
                return;
            }

            const distance = target - from;
            const duration = currentStep >= 2
                ? Math.max(3000, distance * 120)
                : Math.max(6000, distance * 180);

            const ramp = Animated.timing(progressAnim, {
                toValue: target,
                duration,
                useNativeDriver: false,
            });

            runningAnim.current = ramp;
            ramp.start(({ finished }) => {
                if (!finished) return;
                if (currentStep >= 2) {
                    const toFull = Animated.timing(progressAnim, {
                        toValue: 100,
                        duration: 12000,
                        useNativeDriver: false,
                    });
                    runningAnim.current = toFull;
                    toFull.start();
                }
            });
        });

        return () => {
            runningAnim.current?.stop();
        };
    }, [currentStep, progressAnim]);

    useEffect(() => {
        let alive = true;
        const animateDots = () => {
            if (!alive) return;
            Animated.sequence([
                Animated.timing(dots[0], { toValue: 1, duration: 300, useNativeDriver: true }),
                Animated.timing(dots[1], { toValue: 1, duration: 300, useNativeDriver: true }),
                Animated.timing(dots[2], { toValue: 1, duration: 300, useNativeDriver: true }),
            ]).start(() => {
                if (!alive) return;
                dots.forEach((d) => d.setValue(0.3));
                animateDots();
            });
        };
        animateDots();
        return () => {
            alive = false;
        };
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
                    <Text style={styles.progressTitle} numberOfLines={1} ellipsizeMode="tail">
                        Analyzing your scan
                    </Text>
                    <Text style={styles.progressPct}>{pctLabel}%</Text>
                </View>
                <View style={styles.trackWrap}>
                    <View style={styles.track} onLayout={onTrackLayout}>
                        <Animated.View style={[styles.trackFill, { width: fillWidth }]} />
                    </View>
                </View>
                <Text style={styles.stepHint}>
                    {ANALYSIS_STEPS[Math.min(currentStep, ANALYSIS_STEPS.length - 1)]}…
                </Text>
                <Text style={styles.stayInAppNotice}>
                    Stay in the app until this finishes—leaving can delay or interrupt your results.
                </Text>
            </View>

            <View style={styles.centerStage}>
                <ScanningGrid />
            </View>

            <View style={styles.dotsContainer}>
                {dots.map((opacity, index) => (
                    <Animated.View key={index} style={[styles.dot, { opacity }]} />
                ))}
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
        justifyContent: 'center',
        alignItems: 'baseline',
        gap: spacing.md,
        marginBottom: 4,
    },
    trackWrap: {
        marginTop: 22,
    },
    progressTitle: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.3,
    },
    progressPct: { fontSize: 22, fontWeight: '600', color: colors.foreground, letterSpacing: -0.5 },
    track: {
        height: 4,
        borderRadius: borderRadius.full,
        backgroundColor: colors.surface,
        overflow: 'hidden',
    },
    trackFill: {
        height: '100%',
        borderRadius: borderRadius.full,
        backgroundColor: colors.foreground,
    },
    stepHint: {
        marginTop: spacing.md,
        fontSize: 15,
        fontWeight: '500',
        color: colors.foreground,
        textAlign: 'center',
    },
    stayInAppNotice: {
        marginTop: spacing.sm,
        fontSize: 12,
        lineHeight: 18,
        color: colors.textMuted,
        textAlign: 'center',
        paddingHorizontal: spacing.sm,
    },
    centerStage: {
        flex: 1,
        width: '100%',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: 200,
    },
    dotsContainer: {
        flexDirection: 'row',
        justifyContent: 'center',
        gap: spacing.sm,
        marginBottom: spacing.xxl,
        alignSelf: 'center',
    },
    dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.foreground },
});
