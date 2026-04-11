import { useCallback, useEffect, useState } from 'react';
import { Alert, Platform } from 'react-native';
import { useIAP, ErrorCode, type Purchase } from 'react-native-iap';
import { APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU } from '../constants/appleIap';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

type Tier = 'basic' | 'premium';

export function useAppleSubscription() {
    const { user, refreshUser } = useAuth();
    const [loading, setLoading] = useState<Tier | null>(null);

    const { connected, subscriptions, fetchProducts, requestPurchase, finishTransaction } =
        useIAP({
            onPurchaseSuccess: async (purchase: Purchase) => {
                if (Platform.OS !== 'ios') return;
                try {
                    const p = purchase as { transactionId?: string; id?: string };
                    const tid = String(p.transactionId ?? p.id ?? '').trim();
                    if (!tid) {
                        throw new Error('Missing transaction id from StoreKit.');
                    }
                    await api.verifyAppleIapTransaction(tid);
                    await finishTransaction({ purchase });
                    await refreshUser();
                    Alert.alert('Subscribed!', 'Your plan is now active.');
                } catch (e: unknown) {
                    const d = (e as { response?: { data?: { detail?: unknown } } })?.response
                        ?.data?.detail;
                    const msg =
                        typeof d === 'string'
                            ? d
                            : Array.isArray(d)
                              ? d
                                    .map((x: { msg?: string }) => x?.msg)
                                    .filter(Boolean)
                                    .join('\n') || 'Could not verify purchase.'
                              : (e as Error)?.message || 'Could not verify purchase.';
                    Alert.alert('Purchase', String(msg));
                } finally {
                    setLoading(null);
                }
            },
            onPurchaseError: (error: { code?: string; message: string }) => {
                setLoading(null);
                if (error.code === ErrorCode.UserCancelled) return;
                Alert.alert('Purchase', error.message || 'Something went wrong.');
            },
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
            const sku =
                tier === 'premium' ? APPLE_IAP_PREMIUM_SKU : APPLE_IAP_BASIC_SKU;
            try {
                await requestPurchase({
                    type: 'subs',
                    request: {
                        ios: { sku },
                    },
                });
                return true;
            } catch (e: unknown) {
                setLoading(null);
                Alert.alert(
                    'Error',
                    (e as Error)?.message || 'Could not start purchase.',
                );
                return false;
            }
        },
        [user?.id, requestPurchase],
    );

    const subscribeBasic = useCallback(
        () => subscribeTier('basic'),
        [subscribeTier],
    );
    const subscribePremium = useCallback(
        () => subscribeTier('premium'),
        [subscribeTier],
    );

    return {
        loading,
        subscribeBasic,
        subscribePremium,
        subscribeTier,
        storeConnected: connected,
    };
}
