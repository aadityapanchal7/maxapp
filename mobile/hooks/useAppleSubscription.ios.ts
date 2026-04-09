import { useCallback, useEffect, useState } from 'react';
import { Alert, Platform } from 'react-native';
import { finishTransaction, isUserCancelledError, useIAP, type Purchase } from 'react-native-iap';
import { APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU } from '../constants/appleIap';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

type Tier = 'basic' | 'premium';

/** iOS App Store subscriptions (StoreKit via react-native-iap). */
export function useAppleSubscription() {
    const { user, refreshUser } = useAuth();
    const [loading, setLoading] = useState<Tier | null>(null);

    const onPurchaseSuccess = useCallback(
        async (purchase: Purchase) => {
            if (Platform.OS !== 'ios') return;
            try {
                const tid = (purchase as { transactionId?: string }).transactionId;
                if (!tid) {
                    throw new Error('Missing transaction id from StoreKit.');
                }
                await api.verifyAppleIapTransaction(String(tid));
                await finishTransaction({ purchase });
                await refreshUser();
            } catch (e: unknown) {
                const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
                const msg =
                    typeof d === 'string'
                        ? d
                        : Array.isArray(d)
                          ? d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join('\n') ||
                            'Could not verify purchase.'
                          : (e as Error)?.message || 'Could not verify purchase.';
                Alert.alert('Purchase', String(msg));
            } finally {
                setLoading(null);
            }
        },
        [refreshUser],
    );

    const onPurchaseError = useCallback((error: { code?: string; message: string }) => {
        setLoading(null);
        if (isUserCancelledError(error)) return;
        Alert.alert('Purchase', error.message || 'Something went wrong.');
    }, []);

    const { connected, fetchProducts, requestPurchase } = useIAP({
        onPurchaseSuccess,
        onPurchaseError,
    });

    useEffect(() => {
        if (Platform.OS !== 'ios' || !connected) return;
        void fetchProducts({
            skus: [APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU],
            type: 'subs',
        });
    }, [connected, fetchProducts]);

    const subscribeTier = useCallback(
        async (tier: Tier): Promise<boolean> => {
            if (Platform.OS !== 'ios') return false;
            if (!user?.id) {
                Alert.alert('Sign in', 'Log in to subscribe.');
                return false;
            }
            setLoading(tier);
            const sku = tier === 'premium' ? APPLE_IAP_PREMIUM_SKU : APPLE_IAP_BASIC_SKU;
            try {
                await requestPurchase({
                    type: 'subs',
                    request: {
                        apple: { sku, appAccountToken: user.id },
                    },
                });
                return true;
            } catch (e: unknown) {
                setLoading(null);
                Alert.alert('Error', (e as Error)?.message || 'Could not start purchase.');
                return false;
            }
        },
        [user?.id, requestPurchase],
    );

    const subscribeBasic = useCallback(() => subscribeTier('basic'), [subscribeTier]);
    const subscribePremium = useCallback(() => subscribeTier('premium'), [subscribeTier]);

    return {
        loading,
        subscribeBasic,
        subscribePremium,
        subscribeTier,
        storeConnected: connected,
    };
}
