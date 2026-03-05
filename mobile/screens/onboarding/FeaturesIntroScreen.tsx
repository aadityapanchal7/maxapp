import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const FEATURES = [
    { icon: 'scan', title: 'AI Face Scan', desc: 'Get a detailed analysis of your facial features using cutting-edge AI technology' },
    { icon: 'school', title: 'Structured Courses', desc: 'Follow expert-designed programs for jawline, skin, posture and more' },
    { icon: 'videocam', title: 'Live Events', desc: 'Join exclusive live sessions for tips, Q&A, and community motivation' },
    { icon: 'trending-up', title: 'Track Progress', desc: 'Monitor your improvement over time with detailed metrics and insights' },
];

export default function FeaturesIntroScreen() {
    const navigation = useNavigation<any>();
    const [currentIndex, setCurrentIndex] = useState(0);
    const fadeAnim = useRef(new Animated.Value(1)).current;

    const animateTransition = (next: number) => {
        Animated.timing(fadeAnim, { toValue: 0, duration: 150, useNativeDriver: true }).start(() => {
            setCurrentIndex(next);
            Animated.timing(fadeAnim, { toValue: 1, duration: 300, useNativeDriver: true }).start();
        });
    };

    const handleNext = () => {
        if (currentIndex < FEATURES.length - 1) animateTransition(currentIndex + 1);
        else navigation.navigate('FaceScan');
    };

    const feature = FEATURES[currentIndex];

    return (
        <View style={styles.container}>
            <View style={styles.top}>
                <Text style={styles.stepLabel}>STEP 2 OF 2</Text>
            </View>

            <Animated.View style={[styles.content, { opacity: fadeAnim }]}>
                <View style={styles.iconRing}>
                    <Ionicons name={feature.icon as any} size={36} color={colors.foreground} />
                </View>
                <Text style={styles.title}>{feature.title}</Text>
                <Text style={styles.desc}>{feature.desc}</Text>
            </Animated.View>

            <View style={styles.bottom}>
                <View style={styles.dots}>
                    {FEATURES.map((_, i) => (
                        <View key={i} style={[styles.dot, i === currentIndex && styles.dotActive]} />
                    ))}
                </View>
                <TouchableOpacity style={styles.button} onPress={handleNext} activeOpacity={0.7}>
                    <Text style={styles.buttonText}>{currentIndex < FEATURES.length - 1 ? 'Next' : 'Start Face Scan'}</Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background, padding: spacing.lg, justifyContent: 'space-between' },
    top: { paddingTop: 80 },
    stepLabel: { ...typography.label, color: colors.textMuted },
    content: { alignItems: 'center', paddingHorizontal: spacing.lg },
    iconRing: {
        width: 96, height: 96, borderRadius: 48,
        backgroundColor: colors.card,
        justifyContent: 'center', alignItems: 'center',
        marginBottom: spacing.xl,
        ...shadows.md,
    },
    title: { ...typography.h1, textAlign: 'center', marginBottom: spacing.md },
    desc: { fontSize: 15, color: colors.textSecondary, textAlign: 'center', lineHeight: 24, maxWidth: 320 },
    bottom: { gap: spacing.xl, paddingBottom: spacing.lg },
    dots: { flexDirection: 'row', justifyContent: 'center', gap: spacing.sm },
    dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.borderLight },
    dotActive: { backgroundColor: colors.foreground, width: 24 },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: 16,
        alignItems: 'center',
        ...shadows.md,
    },
    buttonText: { ...typography.button },
});
