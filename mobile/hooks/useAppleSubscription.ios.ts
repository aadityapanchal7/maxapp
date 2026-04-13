import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Platform } from 'react-native';
import { useIAP, ErrorCode, type Purchase } from 'react-native-iap';
import { APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU } from '../constants/appleIap';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

type Tier = 'basic' | 'premium';

export function useAppleSubscription() {
    const { user, refreshUser } = useAuth();
    const [loading, setLoading] = useState<Tier | null>(null);
    const pendingSkuRef = useRef<string | null>(null);
    const processedTids = useRef<Set<string>>(new Set());
    const recoveringRef = useRef(false);

    const { connected, fetchProducts, requestPurchase, finishTransaction, getAvailablePurchases } =
        useIAP({
            onPurchaseSuccess: async (purchase: Purchase) => {
                if (Platform.OS !== 'ios') return;
                try {
                    const p = purchase as { transactionId?: string; id?: string; productId?: string };
                    const tid = String(p.transactionId ?? p.id ?? '').trim();
                    if (!tid) {
                        throw new Error('Missing transaction id from StoreKit.');
                    }

                    if (processedTids.current.has(tid)) {
                        try { await finishTransaction({ purchase }); } catch {}
                        setLoading(null);
                        pendingSkuRef.current = null;
                        return;
                    }
                    processedTids.current.add(tid);

                    const productId = p.productId || pendingSkuRef.current || undefined;

                    await api.verifyAppleIapTransaction(tid, productId);

                    try {
                        await finishTransaction({ purchase });
                    } catch (finishErr) {
                        if (__DEV__) console.warn('[AppleIAP] finishTransaction error (non-fatal):', finishErr);
                    }

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
                    Alert.alert('Purchase error', String(msg));
                } finally {
                    setLoading(null);
                    pendingSkuRef.current = null;
                }
            },
            onPurchaseError: (error: { code?: string; message: string }) => {
                setLoading(null);
                pendingSkuRef.current = null;
                if (error.code === ErrorCode.UserCancelled) return;
                Alert.alert('Purchase error', error.message || 'Something went wrong.');
            },
        });

    useEffect(() => {
        if (Platform.OS !== 'ios' || !connected) return;
        void fetchProducts({
            skus: [APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU],
            type: 'subs',
        });
    }, [connected, fetchProducts]);

    useEffect(() => {
        if (Platform.OS !== 'ios' || !connected || recoveringRef.current) return;
        recoveringRef.current = true;
        const recoverPending = async () => {
            try {
                const purchases = await getAvailablePurchases();
                for (const purchase of purchases) {
                    const p = purchase as { transactionId?: string; id?: string; productId?: string };
                    const tid = String(p.transactionId ?? p.id ?? '').trim();
                    if (!tid || processedTids.current.has(tid)) continue;
                    processedTids.current.add(tid);
                    try {
                        await api.verifyAppleIapTransaction(tid, p.productId || undefined);
                        await finishTransaction({ purchase });
                        await refreshUser();
                    } catch {
                        try { await finishTransaction({ purchase }); } catch {}
                    }
                }
            } catch (e) {
                if (__DEV__) console.warn('[AppleIAP] recoverPending:', e);
            }
        };
        void recoverPending();
    }, [connected, getAvailablePurchases, finishTransaction, refreshUser]);

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
            pendingSkuRef.current = sku;
            try {
                await requestPurchase({
                    type: 'subs',
                    request: {
                        apple: { sku },
                    },
                });
                return true;
            } catch (e: unknown) {
                setLoading(null);
                pendingSkuRef.current = null;
                const msg = (e as Error)?.message || 'Could not start purchase.';
                if (!msg.includes('cancelled') && !msg.includes('canceled')) {
                    Alert.alert('Error', msg);
                }
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
