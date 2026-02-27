/**
 * Features Intro Screen
 */

import React, { useState } from 'react';
import { View, Text, StyleSheet, Dimensions, TouchableOpacity } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

const { width } = Dimensions.get('window');

const FEATURES = [
    { icon: 'scan', title: 'AI Face Scan', desc: 'Get a detailed analysis of your facial features using cutting-edge AI' },
    { icon: 'school', title: 'Structured Courses', desc: 'Follow expert-designed programs for jawline, skin, posture and more' },
    { icon: 'videocam', title: 'Live Events', desc: 'Join Cannon\'s TikTok Live sessions for exclusive tips and Q&A' },
    { icon: 'trending-up', title: 'Track Progress', desc: 'Monitor your improvement over time with detailed metrics' },
];

export default function FeaturesIntroScreen() {
    const navigation = useNavigation<any>();
    const [currentIndex, setCurrentIndex] = useState(0);

    const handleNext = () => {
        if (currentIndex < FEATURES.length - 1) {
            setCurrentIndex(currentIndex + 1);
        } else {
            navigation.navigate('FaceScan');
        }
    };

    const feature = FEATURES[currentIndex];

    return (
        <View style={styles.container}>
            <View style={styles.content}>
                <View style={styles.iconContainer}>
                    <Ionicons name={feature.icon as any} size={80} color={colors.primary} />
                </View>
                <Text style={styles.title}>{feature.title}</Text>
                <Text style={styles.desc}>{feature.desc}</Text>
            </View>

            <View style={styles.dots}>
                {FEATURES.map((_, i) => (
                    <View key={i} style={[styles.dot, i === currentIndex && styles.dotActive]} />
                ))}
            </View>

            <TouchableOpacity style={styles.button} onPress={handleNext}>
                <Text style={styles.buttonText}>{currentIndex < FEATURES.length - 1 ? 'Next' : 'Start Face Scan'}</Text>
                <Ionicons name="arrow-forward" size={20} color={colors.textPrimary} />
            </TouchableOpacity>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background, padding: spacing.lg, justifyContent: 'space-between', paddingTop: 100 },
    content: { alignItems: 'center' },
    iconContainer: { width: 160, height: 160, borderRadius: 80, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center', marginBottom: spacing.xl },
    title: { ...typography.h1, textAlign: 'center', marginBottom: spacing.md },
    desc: { ...typography.body, color: colors.textSecondary, textAlign: 'center', paddingHorizontal: spacing.lg },
    dots: { flexDirection: 'row', justifyContent: 'center', gap: spacing.sm },
    dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.border },
    dotActive: { backgroundColor: colors.primary, width: 24 },
    button: { flexDirection: 'row', backgroundColor: colors.primary, borderRadius: borderRadius.md, padding: spacing.md, alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
    buttonText: { ...typography.button },
});
