import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
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

    const handleNext = () => {
        if (currentIndex < FEATURES.length - 1) setCurrentIndex(currentIndex + 1);
        else navigation.navigate('FaceScan');
    };

    const feature = FEATURES[currentIndex];

    return (
        <View style={styles.container}>
            <View style={styles.topSection}>
                <Text style={styles.stepLabel}>STEP 2 OF 2</Text>
            </View>

            <View style={styles.content}>
                <View style={styles.iconContainer}>
                    <View style={styles.iconRing}>
                        <Ionicons name={feature.icon as any} size={48} color={colors.accent} />
                    </View>
                </View>
                <Text style={styles.title}>{feature.title}</Text>
                <Text style={styles.desc}>{feature.desc}</Text>
            </View>

            <View style={styles.bottom}>
                <View style={styles.dots}>
                    {FEATURES.map((_, i) => (
                        <View key={i} style={[styles.dot, i === currentIndex && styles.dotActive]} />
                    ))}
                </View>

                <TouchableOpacity style={styles.button} onPress={handleNext} activeOpacity={0.85}>
                    <Text style={styles.buttonText}>{currentIndex < FEATURES.length - 1 ? 'Next' : 'Start Face Scan'}</Text>
                    <Ionicons name="arrow-forward" size={18} color={colors.buttonText} />
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background, padding: spacing.lg, justifyContent: 'space-between' },
    topSection: { paddingTop: 60 },
    stepLabel: { ...typography.caption, letterSpacing: 2, textTransform: 'uppercase', color: colors.accent, fontWeight: '600' },
    content: { alignItems: 'center', paddingHorizontal: spacing.md },
    iconContainer: { marginBottom: spacing.xl },
    iconRing: {
        width: 120, height: 120, borderRadius: 60,
        backgroundColor: colors.accentMuted,
        borderWidth: 1.5, borderColor: colors.accent,
        justifyContent: 'center', alignItems: 'center',
    },
    title: { ...typography.h1, textAlign: 'center', marginBottom: spacing.md },
    desc: { ...typography.body, color: colors.textSecondary, textAlign: 'center', lineHeight: 24, paddingHorizontal: spacing.md },
    bottom: { gap: spacing.xl, paddingBottom: spacing.lg },
    dots: { flexDirection: 'row', justifyContent: 'center', gap: spacing.sm },
    dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.border },
    dotActive: { backgroundColor: colors.accent, width: 28, borderRadius: 4 },
    button: {
        flexDirection: 'row',
        backgroundColor: colors.primary,
        borderRadius: borderRadius.md,
        paddingVertical: 16,
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        ...shadows.md,
    },
    buttonText: { ...typography.button },
});
