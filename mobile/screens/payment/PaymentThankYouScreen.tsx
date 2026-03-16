import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function PaymentThankYouScreen() {
    const navigation = useNavigation<any>();
    const { refreshUser } = useAuth();
    const [loading, setLoading] = useState(false);

    const handleGoHome = async () => {
        try {
            setLoading(true);
            await refreshUser();
            // Navigator will re-render; if isPaid is true we show Main stack
        } finally {
            setLoading(false);
        }
    };

    return (
        <View style={styles.container}>
            <View style={styles.card}>
                <View style={styles.iconWrap}>
                    <Ionicons name="checkmark-circle" size={64} color={colors.primary} />
                </View>
                <Text style={styles.title}>Thank you</Text>
                <Text style={styles.subtitle}>
                    Your payment was received. Tap below to enter the app. If you just paid, your account may take a moment to update.
                </Text>
                <TouchableOpacity
                    style={[styles.button, loading && styles.buttonDisabled]}
                    onPress={handleGoHome}
                    disabled={loading}
                    activeOpacity={0.8}
                >
                    {loading ? (
                        <ActivityIndicator color={colors.background} />
                    ) : (
                        <>
                            <Text style={styles.buttonText}>Go to Home</Text>
                            <Ionicons name="arrow-forward" size={20} color={colors.background} />
                        </>
                    )}
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.background,
        justifyContent: 'center',
        alignItems: 'center',
        padding: spacing.lg,
    },
    card: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        alignItems: 'center',
        maxWidth: 360,
        ...shadows.md,
    },
    iconWrap: {
        marginBottom: spacing.lg,
    },
    title: {
        ...typography.h2,
        color: colors.foreground,
        marginBottom: spacing.sm,
    },
    subtitle: {
        ...typography.body,
        color: colors.textMuted,
        textAlign: 'center',
        marginBottom: spacing.xl,
    },
    button: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.primary,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.lg,
        borderRadius: borderRadius.lg,
        minWidth: 200,
    },
    buttonDisabled: {
        opacity: 0.7,
    },
    buttonText: {
        ...typography.button,
        color: colors.background,
    },
});
