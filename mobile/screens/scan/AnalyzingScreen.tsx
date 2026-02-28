import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography, shadows } from '../../theme/dark';

interface Props {
    currentStep: number;
    onComplete?: () => void;
}

const ANALYSIS_STEPS = [
    'Analysing your features',
    'Calculating looksmax potential',
    'Generating your transformation',
];

export default function AnalyzingScreen({ currentStep = 0, onComplete }: Props) {
    const [dots] = useState([new Animated.Value(1), new Animated.Value(0.3), new Animated.Value(0.3)]);

    useEffect(() => {
        const animateDots = () => {
            Animated.sequence([
                Animated.timing(dots[0], { toValue: 1, duration: 300, useNativeDriver: true }),
                Animated.timing(dots[1], { toValue: 1, duration: 300, useNativeDriver: true }),
                Animated.timing(dots[2], { toValue: 1, duration: 300, useNativeDriver: true }),
            ]).start(() => {
                dots.forEach(d => d.setValue(0.3));
                animateDots();
            });
        };
        animateDots();
    }, []);

    return (
        <View style={styles.container}>
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
                                <Ionicons name="checkmark" size={16} color={colors.textPrimary} />
                            ) : isActive ? (
                                <Ionicons name="sync" size={16} color={colors.accent} />
                            ) : (
                                <View style={styles.emptyIcon} />
                            )}
                            <Text style={[
                                styles.stepText,
                                isCompleted && styles.stepTextCompleted,
                                isActive && styles.stepTextActive,
                                !isCompleted && !isActive && styles.stepTextPending
                            ]}>{step}</Text>
                        </View>
                    );
                })}
            </View>

            <View style={styles.dotsContainer}>
                {dots.map((opacity, index) => (
                    <Animated.View key={index} style={[styles.dot, { opacity }]} />
                ))}
            </View>

            <View style={styles.footer}>
                <Text style={styles.footerText}>
                    AI is generating your maximum potential based on{'\n'}
                    <Text style={styles.footerHighlight}>50k+ successful transformations</Text>
                </Text>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.lg, backgroundColor: colors.background },
    gridBox: { width: 280, height: 280, borderWidth: 1, borderColor: colors.border, borderStyle: 'dashed', borderRadius: 8, padding: 20, marginBottom: spacing.xl },
    gridInner: { flex: 1, justifyContent: 'space-between' },
    gridRow: { flexDirection: 'row', justifyContent: 'space-between' },
    gridCell: { width: 4, height: 4, backgroundColor: colors.border, borderRadius: 2 },
    stepsContainer: { alignItems: 'flex-start', marginBottom: spacing.xl },
    stepRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md, gap: spacing.sm },
    emptyIcon: { width: 16, height: 16 },
    stepText: { fontFamily: 'Matter-Regular', fontSize: 16, color: colors.textMuted },
    stepTextCompleted: { color: colors.textPrimary },
    stepTextActive: { color: colors.accent },
    stepTextPending: { color: colors.textMuted },
    dotsContainer: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xxl },
    dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.accent },
    footer: { position: 'absolute', bottom: 60, paddingHorizontal: spacing.lg },
    footerText: { fontFamily: 'Matter-Regular', fontSize: 14, color: colors.textMuted, textAlign: 'center', lineHeight: 22 },
    footerHighlight: { fontFamily: 'Matter-Medium', color: colors.accent },
});
