/**
 * GradientBackground Component
 * Applies the Figma gradient (#171840 to #6D37D4) to screen backgrounds
 */

import React from 'react';
import { StyleSheet, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors } from '../theme/dark';

interface Props {
    children: React.ReactNode;
    style?: ViewStyle;
}

export default function GradientBackground({ children, style }: Props) {
    return (
        <LinearGradient
            colors={[colors.gradientStart, colors.gradientEnd]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[styles.gradient, style]}
        >
            {children}
        </LinearGradient>
    );
}

const styles = StyleSheet.create({
    gradient: {
        flex: 1,
    },
});
