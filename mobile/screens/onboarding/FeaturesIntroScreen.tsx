import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { useAuth } from '../../context/AuthContext';

/** Single pre-scan screen (carousel removed — only face scan intro). */
export default function FeaturesIntroScreen() {
    const navigation = useNavigation<any>();
    const { user, isPaid } = useAuth();

    return (
        <View style={styles.container}>
            <View style={styles.top}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={styles.backWrap}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                    accessibilityLabel="Back"
                >
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.stepLabel}>FACE SCAN</Text>
                <View style={{ width: 28 }} />
            </View>

            <View style={styles.content}>
                <View style={styles.iconRing}>
                    <Ionicons name="scan" size={36} color={colors.foreground} />
                </View>
                <Text style={styles.title}>AI Face Scan</Text>
                <Text style={styles.desc}>
                    Get a detailed analysis using three quick photos — front and both profiles — then see your scores
                    before you subscribe.
                </Text>
            </View>

            <View style={styles.bottom}>
                {user?.first_scan_completed && !isPaid ? (
                    <TouchableOpacity
                        style={styles.button}
                        onPress={() => navigation.navigate('FaceScanResults')}
                        activeOpacity={0.7}
                    >
                        <Text style={styles.buttonText}>View my results</Text>
                    </TouchableOpacity>
                ) : (
                    <TouchableOpacity
                        style={styles.button}
                        onPress={() => navigation.navigate('FaceScan')}
                        activeOpacity={0.7}
                    >
                        <Text style={styles.buttonText}>Start Face Scan</Text>
                    </TouchableOpacity>
                )}
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background, padding: spacing.lg, justifyContent: 'space-between' },
    top: {
        paddingTop: 56,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    backWrap: { width: 40, height: 40, justifyContent: 'center' },
    stepLabel: { ...typography.label, color: colors.textMuted, flex: 1, textAlign: 'center' },
    content: { alignItems: 'center', paddingHorizontal: spacing.lg },
    iconRing: {
        width: 96,
        height: 96,
        borderRadius: 48,
        backgroundColor: colors.card,
        justifyContent: 'center',
        alignItems: 'center',
        marginBottom: spacing.xl,
        ...shadows.md,
    },
    title: { ...typography.h1, textAlign: 'center', marginBottom: spacing.md },
    desc: { fontSize: 15, color: colors.textSecondary, textAlign: 'center', lineHeight: 24, maxWidth: 320 },
    bottom: { gap: spacing.xl, paddingBottom: spacing.lg },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: 16,
        alignItems: 'center',
        ...shadows.md,
    },
    buttonText: { ...typography.button },
});
