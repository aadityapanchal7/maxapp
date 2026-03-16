import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert, ScrollView } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const PLANS = [
    {
        id: 'basic',
        name: 'Basic',
        price: 20,
        stripeUrl: 'https://buy.stripe.com/9B64gzazZgDmaVL7vKbII01',
        features: [
            'Core course modules',
            'Basic progress tracking',
            'Standard community access',
            'Standard support',
        ],
    },
    {
        id: 'premium',
        name: 'Premium',
        price: 29,
        stripeUrl: 'https://buy.stripe.com/dRmdR9gYn72Me7X9DSbII00',
        features: [
            'Full course library access',
            'AI schedule + reminders',
            'Community & forums',
            'Priority support',
        ],
    },
];

export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const { refreshUser } = useAuth();
    const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
    const [devLoading, setDevLoading] = useState(false);

    const handleOpenStripe = async (planId: string, url: string) => {
        try {
            setLoadingPlan(planId);
            const result = await WebBrowser.openBrowserAsync(url);
            if (result.type === 'cancel' || result.type === 'dismiss') {
                navigation.navigate('PaymentThankYou');
            }
        } catch (e) {
            Alert.alert('Error', 'Could not open checkout.');
        } finally {
            setLoadingPlan(null);
        }
    };

    const handleDevSkip = async () => {
        try {
            setDevLoading(true);
            await api.testActivateSubscription();
            await refreshUser();
            navigation.navigate('PaymentThankYou');
        } catch (error: any) {
            const msg = error?.response?.data?.detail
                || error?.message
                || (error?.response?.status === 401 ? 'Please log in first.' : 'Failed to activate dev subscription.');
            Alert.alert('Error', String(msg));
        } finally {
            setDevLoading(false);
        }
    };

    return (
        <View style={styles.container}>
            <ScrollView contentContainerStyle={styles.content}>
                <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>

                <View style={styles.header}>
                    <Text style={styles.title}>Choose your plan</Text>
                    <Text style={styles.subtitle}>Dummy comparison for now — both redirect to Stripe links you provided.</Text>
                </View>

                {PLANS.map((plan) => (
                    <View key={plan.id} style={styles.planCard}>
                        <View style={styles.planHeader}>
                            <Text style={styles.planName}>{plan.name}</Text>
                            <View style={styles.priceRow}>
                                <Text style={styles.price}>${plan.price}</Text>
                                <Text style={styles.priceLabel}>/month</Text>
                            </View>
                        </View>

                        <View style={styles.featureList}>
                            {plan.features.map((feature, idx) => (
                                <View key={idx} style={styles.featureItem}>
                                    <Ionicons name="checkmark" size={16} color={colors.foreground} />
                                    <Text style={styles.featureText}>{feature}</Text>
                                </View>
                            ))}
                        </View>

                        <TouchableOpacity
                            style={styles.button}
                            activeOpacity={0.85}
                            onPress={() => handleOpenStripe(plan.id, plan.stripeUrl)}
                            disabled={!!loadingPlan || devLoading}
                        >
                            <Text style={styles.buttonText}>
                                {loadingPlan === plan.id ? 'Opening...' : `Continue with ${plan.name}`}
                            </Text>
                        </TouchableOpacity>
                    </View>
                ))}

                <Text style={styles.disclaimer}>You can change or cancel your plan any time from your account settings.</Text>

                <TouchableOpacity
                    style={styles.devButton}
                    activeOpacity={0.85}
                    onPress={handleDevSkip}
                    disabled={devLoading || !!loadingPlan}
                >
                    <Text style={styles.devButtonText}>{devLoading ? 'Activating...' : 'DEV: Skip payment & unlock'}</Text>
                </TouchableOpacity>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg, paddingTop: 64, paddingBottom: 40 },
    backButton: { position: 'absolute', top: 54, left: spacing.lg, zIndex: 10, padding: spacing.sm },
    header: { alignItems: 'flex-start', marginBottom: spacing.xl, marginTop: spacing.xl },
    title: { fontSize: 28, fontWeight: '600', color: colors.foreground, letterSpacing: -0.5, marginBottom: spacing.xs },
    subtitle: { fontSize: 13, color: colors.textSecondary },
    planCard: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.lg,
        marginBottom: spacing.lg,
        ...shadows.md,
    },
    planHeader: {
        flexDirection: 'row',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        marginBottom: spacing.md,
    },
    planName: {
        fontSize: 18,
        fontWeight: '600',
        color: colors.foreground,
        textTransform: 'uppercase',
    },
    priceRow: {
        flexDirection: 'row',
        alignItems: 'baseline',
        gap: 4,
    },
    price: { fontSize: 28, fontWeight: '700', color: colors.foreground },
    priceLabel: { fontSize: 14, fontWeight: '400', color: colors.textMuted },
    featureList: {
        marginBottom: spacing.lg,
        gap: spacing.sm,
    },
    featureItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    featureText: { fontSize: 14, color: colors.foreground },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.md,
        alignItems: 'center',
        ...shadows.md,
    },
    buttonText: { ...typography.button },
    disclaimer: { fontSize: 12, color: colors.textMuted, textAlign: 'center', marginTop: spacing.md },
    devButton: {
        marginTop: spacing.lg,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.sm,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
    },
    devButtonText: {
        fontSize: 13,
        fontWeight: '600',
        color: colors.textSecondary,
    },
});
