import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert, ScrollView } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const FEATURES = [
    'Full facial analysis with 50+ metrics',
    'Personalized improvement plans',
    'Access to all courses',
    'Join TikTok Live events',
    'Track your progress over time',
    'Climb the leaderboard',
    'Chat with Cannon AI',
    'Community forums access',
];

export default function PaymentScreen() {
    const navigation = useNavigation<any>();
    const { refreshUser } = useAuth();
    const [loading, setLoading] = useState(false);

    const handleSubscribe = async () => {
        setLoading(true);
        try {
            const returnUrl = Linking.createURL('/payment-success');
            const cancelUrl = Linking.createURL('/payment-cancel');
            const { checkout_url } = await api.createCheckoutSession(returnUrl, cancelUrl);
            const result = await WebBrowser.openBrowserAsync(checkout_url);
            if (result.type === 'cancel') await refreshUser();
        } catch (e) { Alert.alert('Error', 'Could not start checkout'); }
        finally { setLoading(false); }
    };

    return (
        <View style={styles.container}>
            <ScrollView contentContainerStyle={styles.content}>
                <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()}>
                    <Ionicons name="arrow-back" size={24} color={colors.textPrimary} />
                </TouchableOpacity>

                <View style={styles.header}>
                    <Ionicons name="diamond" size={48} color={colors.accent} />
                    <Text style={styles.title}>Cannon Premium</Text>
                    <Text style={styles.subtitle}>Unlock your full potential</Text>
                </View>

                <View style={styles.features}>
                    {FEATURES.map((feature, i) => (
                        <View key={i} style={styles.featureItem}>
                            <Ionicons name="checkmark-circle" size={20} color={colors.success} />
                            <Text style={styles.featureText}>{feature}</Text>
                        </View>
                    ))}
                </View>

                <View style={styles.priceCard}>
                    <Text style={styles.price}>$9.99</Text>
                    <Text style={styles.priceLabel}>/month</Text>
                </View>

                <TouchableOpacity style={styles.button} onPress={handleSubscribe} disabled={loading}>
                    <Text style={styles.buttonText}>{loading ? 'Loading...' : 'Subscribe Now'}</Text>
                </TouchableOpacity>

                <Text style={styles.disclaimer}>Cancel anytime. No commitment.</Text>

                <TouchableOpacity style={styles.devButton} onPress={async () => {
                    try { setLoading(true); await api.testActivateSubscription(); await refreshUser(); Alert.alert('Success', 'Subscription activated!'); }
                    catch (error: any) { Alert.alert('Error', error.response?.data?.detail || 'Failed to activate'); }
                    finally { setLoading(false); }
                }} disabled={loading}>
                    <Text style={styles.devButtonText}>DEV: Skip Payment</Text>
                </TouchableOpacity>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    content: { padding: spacing.lg, paddingTop: 60, paddingBottom: 40 },
    backButton: { position: 'absolute', top: 50, left: spacing.lg, zIndex: 10, padding: spacing.sm },
    header: { alignItems: 'center', marginBottom: spacing.xl, marginTop: spacing.xl },
    title: { ...typography.h1, marginTop: spacing.md },
    subtitle: { ...typography.bodySmall },
    features: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.lg, gap: spacing.md, ...shadows.sm },
    featureItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    featureText: { ...typography.body },
    priceCard: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', marginTop: spacing.xl },
    price: { fontSize: 48, fontFamily: 'Matter-Medium', fontWeight: '500', color: colors.accent },
    priceLabel: { ...typography.h3, color: colors.textMuted },
    button: { backgroundColor: colors.accent, borderRadius: borderRadius.md, padding: spacing.md, alignItems: 'center', marginTop: spacing.xl },
    buttonText: { ...typography.button },
    disclaimer: { ...typography.caption, textAlign: 'center', marginTop: spacing.md },
    devButton: { backgroundColor: colors.surface, borderRadius: borderRadius.md, padding: spacing.sm, alignItems: 'center', marginTop: spacing.lg, borderWidth: 1, borderColor: colors.border },
    devButtonText: { ...typography.bodySmall, fontWeight: '700' },
});
