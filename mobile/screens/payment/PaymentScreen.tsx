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
    'Chat with Max AI',
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
                <TouchableOpacity style={styles.backButton} onPress={() => navigation.goBack()} activeOpacity={0.7}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>

                <View style={styles.header}>
                    <Text style={styles.title}>max premium</Text>
                    <Text style={styles.subtitle}>Unlock your full potential</Text>
                </View>

                <View style={styles.features}>
                    {FEATURES.map((feature, i) => (
                        <View key={i} style={styles.featureItem}>
                            <Ionicons name="checkmark" size={16} color={colors.foreground} />
                            <Text style={styles.featureText}>{feature}</Text>
                        </View>
                    ))}
                </View>

                <View style={styles.priceCard}>
                    <Text style={styles.price}>$9.99</Text>
                    <Text style={styles.priceLabel}>/month</Text>
                </View>

                <TouchableOpacity style={styles.button} onPress={handleSubscribe} disabled={loading} activeOpacity={0.7}>
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
    content: { padding: spacing.lg, paddingTop: 64, paddingBottom: 40 },
    backButton: { position: 'absolute', top: 54, left: spacing.lg, zIndex: 10, padding: spacing.sm },
    header: { alignItems: 'center', marginBottom: spacing.xl, marginTop: spacing.xl },
    title: { fontSize: 32, fontWeight: '400', color: colors.foreground, letterSpacing: -1, marginBottom: spacing.xs },
    subtitle: { fontSize: 14, color: colors.textSecondary },
    features: {
        backgroundColor: colors.card, borderRadius: borderRadius['2xl'],
        padding: spacing.lg, gap: spacing.md,
        ...shadows.md,
    },
    featureItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    featureText: { fontSize: 14, color: colors.foreground },
    priceCard: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', marginTop: spacing.xl },
    price: { fontSize: 44, fontWeight: '700', color: colors.foreground },
    priceLabel: { fontSize: 18, fontWeight: '400', color: colors.textMuted },
    button: { backgroundColor: colors.foreground, borderRadius: borderRadius.full, padding: spacing.md, alignItems: 'center', marginTop: spacing.xl, ...shadows.md },
    buttonText: { ...typography.button },
    disclaimer: { fontSize: 12, color: colors.textMuted, textAlign: 'center', marginTop: spacing.md },
    devButton: { backgroundColor: colors.surface, borderRadius: borderRadius.full, padding: spacing.sm, alignItems: 'center', marginTop: spacing.lg, borderWidth: 1, borderColor: colors.border },
    devButtonText: { fontSize: 13, fontWeight: '600', color: colors.textSecondary },
});
