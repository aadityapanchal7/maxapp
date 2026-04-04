import { useState, useCallback, useRef } from 'react';
import { Alert, Platform } from 'react-native';
import { useStripe } from '@stripe/stripe-react-native';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

type Tier = 'basic' | 'premium';

const POLL_MS = 2000;
const POLL_MAX = 20;

export function useStripeSubscription() {
    const { initPaymentSheet, presentPaymentSheet } = useStripe();
    const { refreshUser } = useAuth();

    const [loading, setLoading] = useState<Tier | null>(null);
    const [error, setError] = useState<string | null>(null);
    const pollingRef = useRef(false);

    const pollUntilPaid = useCallback(async (): Promise<boolean> => {
        if (pollingRef.current) return false;
        pollingRef.current = true;
        try {
            for (let i = 0; i < POLL_MAX; i++) {
                try {
                    const u = await refreshUser();
                    if (u?.is_paid) return true;
                } catch { /* retry */ }
                await new Promise((r) => setTimeout(r, POLL_MS));
            }
            return false;
        } finally {
            pollingRef.current = false;
        }
    }, [refreshUser]);

    const subscribeTier = useCallback(
        async (tier: Tier): Promise<boolean> => {
            setLoading(tier);
            setError(null);

            try {
                const preview = await api.getBillingPreview(tier);

                const weeklyAmount = tier === 'premium' ? '5.99' : '3.99';
                const planLabel = tier === 'premium' ? 'Max Premium (weekly)' : 'Max Basic (weekly)';

                const { error: initError } = await initPaymentSheet({
                    customerId: preview.customer_id,
                    customerEphemeralKeySecret: preview.ephemeral_key_secret,
                    setupIntentClientSecret: preview.setup_intent_client_secret,
                    merchantDisplayName: 'Max',
                    returnURL: 'cannon://stripe-redirect',
                    ...(Platform.OS === 'ios'
                        ? {
                              applePay: {
                                  merchantCountryCode: 'US',
                                  cartItems: [
                                      {
                                          paymentType: 'Immediate' as const,
                                          label: planLabel,
                                          amount: weeklyAmount,
                                      },
                                  ],
                              },
                          }
                        : {}),
                    ...(Platform.OS === 'android'
                        ? {
                              googlePay: { merchantCountryCode: 'US', testEnv: __DEV__ },
                          }
                        : {}),
                });

                if (initError) {
                    setError(initError.message);
                    Alert.alert('Setup error', initError.message);
                    return false;
                }

                const { error: presentError } = await presentPaymentSheet();

                if (presentError) {
                    if (presentError.code !== 'Canceled') {
                        setError(presentError.message);
                        Alert.alert('Payment error', presentError.message);
                    }
                    return false;
                }

                const sub = await api.subscribe(tier, preview.setup_intent_id);

                if (sub.status === 'active') {
                    await refreshUser();
                    return true;
                }

                const ok = await pollUntilPaid();
                if (ok) {
                    await refreshUser();
                    return true;
                }

                return false;
            } catch (e: any) {
                const msg =
                    e?.response?.data?.detail || e?.message || 'Subscription failed';
                setError(msg);
                Alert.alert('Error', msg);
                return false;
            } finally {
                setLoading(null);
            }
        },
        [initPaymentSheet, presentPaymentSheet, refreshUser, pollUntilPaid],
    );

    const subscribeBasic = useCallback(() => subscribeTier('basic'), [subscribeTier]);
    const subscribePremium = useCallback(() => subscribeTier('premium'), [subscribeTier]);

    return { loading, error, subscribeBasic, subscribePremium, subscribeTier };
}
