import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Platform } from 'react-native';
import { useIAP, ErrorCode, type Purchase, type Product } from 'react-native-iap';
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
    const [products, setProducts] = useState<Product[]>([]);
    const [storeError, setStoreError] = useState<string | null>(null);

    const { connected, fetchProducts, requestPurchase, finishTransaction, getAvailablePurchases } =
        useIAP({
            onPurchaseSuccess: async (purchase: Purchase) => {
                if (Platform.OS !== 'ios') return;
                try {
                    const p = purchase as { transactionId?: string; id?: string; productId?: string };
                    const tid = String(p.transactionId ?? p.id ?? '').trim();
                    if (!tid) {
                        console.error('[AppleIAP] Missing transaction id from StoreKit purchase:', JSON.stringify(p));
                        throw new Error('Missing transaction id from StoreKit.');
                    }

                    if (processedTids.current.has(tid)) {
                        console.log('[AppleIAP] Duplicate tid, finishing:', tid);
                        try { await finishTransaction({ purchase }); } catch {}
                        setLoading(null);
                        pendingSkuRef.current = null;
                        return;
                    }
                    processedTids.current.add(tid);

                    const productId = p.productId || pendingSkuRef.current || undefined;
                    console.log('[AppleIAP] Verifying transaction:', tid, 'product:', productId);

                    await api.verifyAppleIapTransaction(tid, productId);

                    try {
                        await finishTransaction({ purchase });
                    } catch (finishErr) {
                        console.warn('[AppleIAP] finishTransaction error (non-fatal):', finishErr);
                    }

                    await refreshUser();
                    Alert.alert('Subscribed!', 'Your plan is now active.');
                } catch (e: unknown) {
                    console.error('[AppleIAP] Purchase verification failed:', e);
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
                console.error('[AppleIAP] Purchase error:', error.code, error.message);
                Alert.alert('Purchase error', error.message || 'Something went wrong.');
            },
        });

    // Fetch products once connected
    useEffect(() => {
        if (Platform.OS !== 'ios' || !connected) return;
        const skus = [APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU];
        console.log('[AppleIAP] Store connected, fetching products:', skus);
        void fetchProducts({ skus, type: 'subs' })
            .then((fetched) => {
                const list = (fetched ?? []) as Product[];
                setProducts(list);
                if (list.length === 0) {
                    const msg = 'No subscription products found in App Store. Check App Store Connect product IDs and agreements.';
                    console.error('[AppleIAP]', msg);
                    setStoreError(msg);
                } else {
                    console.log('[AppleIAP] Products loaded:', list.map((p) => p.productId));
                    setStoreError(null);
                }
            })
            .catch((err) => {
                const msg = `Failed to load products: ${(err as Error)?.message || err}`;
                console.error('[AppleIAP]', msg);
                setStoreError(msg);
            });
    }, [connected, fetchProducts]);

    // Recover pending transactions
    useEffect(() => {
        if (Platform.OS !== 'ios' || !connected || recoveringRef.current) return;
        recoveringRef.current = true;
        const recoverPending = async () => {
            try {
                const purchases = await getAvailablePurchases();
                console.log('[AppleIAP] Recovering pending purchases:', purchases.length);
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
                console.warn('[AppleIAP] recoverPending:', e);
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

            // Check store connectivity
            if (!connected) {
                console.error('[AppleIAP] Store not connected');
                Alert.alert(
                    'App Store unavailable',
                    'Cannot connect to the App Store. Please check your internet connection and try again.',
                );
                return false;
            }

            const sku = tier === 'premium' ? APPLE_IAP_PREMIUM_SKU : APPLE_IAP_BASIC_SKU;

            // Check product availability
            const productAvailable = products.some((p) => p.productId === sku);
            if (!productAvailable) {
                console.error('[AppleIAP] Product not available:', sku, 'loaded products:', products.map((p) => p.productId));
                Alert.alert(
                    'Plan unavailable',
                    'This subscription plan could not be loaded from the App Store. '
                    + 'Please try again later or contact support.',
                );
                return false;
            }

            setLoading(tier);
            pendingSkuRef.current = sku;
            console.log('[AppleIAP] Requesting purchase:', sku);
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
                console.error('[AppleIAP] requestPurchase failed:', msg);
                if (!msg.includes('cancelled') && !msg.includes('canceled')) {
                    Alert.alert('Error', msg);
                }
                return false;
            }
        },
        [user?.id, requestPurchase, connected, products],
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
        storeError,
        products,
    };
}
