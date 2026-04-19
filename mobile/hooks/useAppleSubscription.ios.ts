import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Platform } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { useIAP, ErrorCode, type Purchase, type Product } from 'react-native-iap';
import { APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU } from '../constants/appleIap';
import { useAuth } from '../context/AuthContext';
import { prefetchMainTabData } from '../lib/prefetchMainTabData';
import { queryKeys } from '../lib/queryClient';
import api from '../services/api';

type Tier = 'basic' | 'premium';

export function useAppleSubscription() {
    const { user, refreshUser } = useAuth();
    const queryClient = useQueryClient();
    const [loading, setLoading] = useState<Tier | null>(null);
    const pendingSkuRef = useRef<string | null>(null);
    const requestInFlightRef = useRef(false);
    const processedTids = useRef<Set<string>>(new Set());
    const recoveringRef = useRef(false);
    const [products, setProducts] = useState<Product[]>([]);

    const { connected, fetchProducts, requestPurchase, finishTransaction, getAvailablePurchases } =
        useIAP({
            onPurchaseSuccess: async (purchase: Purchase) => {
                if (Platform.OS !== 'ios') return;
                const p = purchase as { transactionId?: string; id?: string; productId?: string };
                const tid = String(p.transactionId ?? p.id ?? '').trim();
                const isUserInitiated = pendingSkuRef.current !== null;

                // Always attempt to finalize the transaction at the end so
                // StoreKit stops replaying it on every launch, even when the
                // backend rejects verification (e.g. stale / expired txn from
                // a previous sandbox session).
                const finalize = async () => {
                    try { await finishTransaction({ purchase }); } catch (err) {
                        console.warn('[AppleIAP] finishTransaction error (non-fatal):', err);
                    }
                };

                try {
                    if (!tid) {
                        console.error('[AppleIAP] Missing transaction id from StoreKit purchase:', JSON.stringify(p));
                        await finalize();
                        return;
                    }

                    if (processedTids.current.has(tid)) {
                        console.log('[AppleIAP] Duplicate tid, finishing:', tid);
                        await finalize();
                        return;
                    }
                    processedTids.current.add(tid);

                    const productId = p.productId || pendingSkuRef.current || undefined;
                    console.log('[AppleIAP] Verifying transaction:', tid, 'product:', productId);

                    let result: { status?: string; tier?: string } | undefined;
                    try {
                        result = await api.verifyAppleIapTransaction(tid, productId);
                    } catch (e: unknown) {
                        console.error('[AppleIAP] Purchase verification failed:', e);
                        await finalize();
                        if (isUserInitiated) {
                            const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
                            const msg =
                                typeof d === 'string'
                                    ? d
                                    : Array.isArray(d)
                                      ? d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join('\n') || 'Could not verify purchase.'
                                      : (e as Error)?.message || 'Could not verify purchase.';
                            Alert.alert('Purchase error', String(msg));
                        }
                        return;
                    }

                    await finalize();

                    if (result?.status === 'expired') {
                        console.log('[AppleIAP] Cleared stale expired transaction:', tid);
                        return;
                    }

                    await refreshUser();
                    void queryClient.invalidateQueries({ queryKey: queryKeys.maxes });
                    prefetchMainTabData(queryClient);
                } finally {
                    requestInFlightRef.current = false;
                    setLoading(null);
                    pendingSkuRef.current = null;
                }
            },
            onPurchaseError: (error: { code?: string; message: string }) => {
                requestInFlightRef.current = false;
                setLoading(null);
                pendingSkuRef.current = null;
                if (error.code === ErrorCode.UserCancelled) return;
                console.error('[AppleIAP] Purchase error:', error.code, error.message);
                Alert.alert('Purchase error', error.message || 'Something went wrong.');
            },
        });

    // Fetch products with retry — Apple sandbox occasionally returns an empty
    // list on the first request even when products are fully configured.
    const loadProducts = useCallback(
        async (attempt = 0): Promise<Product[]> => {
            const skus = [APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU];
            console.log(`[AppleIAP] Fetching products (attempt ${attempt + 1}):`, skus);
            try {
                const fetched = await fetchProducts({ skus, type: 'subs' });
                const list = (fetched ?? []) as Product[];
                if (list.length > 0) {
                    console.log('[AppleIAP] Products loaded:', list.map((p) => p.productId));
                    setProducts(list);
                    return list;
                }
                if (attempt < 3) {
                    const delay = 1000 * Math.pow(2, attempt);
                    console.warn(`[AppleIAP] Empty product list, retrying in ${delay}ms`);
                    await new Promise((r) => setTimeout(r, delay));
                    return loadProducts(attempt + 1);
                }
                const msg = 'No subscription products found in App Store. Check App Store Connect product IDs and agreements.';
                console.error('[AppleIAP]', msg);
                setProducts([]);
                return [];
            } catch (err) {
                if (attempt < 3) {
                    const delay = 1000 * Math.pow(2, attempt);
                    console.warn(`[AppleIAP] fetchProducts threw, retrying in ${delay}ms:`, err);
                    await new Promise((r) => setTimeout(r, delay));
                    return loadProducts(attempt + 1);
                }
                const msg = `Failed to load products: ${(err as Error)?.message || err}`;
                console.error('[AppleIAP]', msg);
                return [];
            }
        },
        [fetchProducts],
    );

    useEffect(() => {
        if (Platform.OS !== 'ios' || !connected) return;
        void loadProducts();
    }, [connected, loadProducts]);

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
            if (requestInFlightRef.current || pendingSkuRef.current) {
                console.log('[AppleIAP] Purchase request ignored; one is already in flight.');
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

            // Try to warm the cache, but do not block the purchase flow on it.
            // In TestFlight / sandbox, fetchProducts can intermittently return
            // an empty list even though StoreKit can still present the purchase
            // sheet for a valid SKU.
            let productList = products;
            if (!productList.some((p) => p.productId === sku)) {
                console.warn('[AppleIAP] Product missing at subscribe time, re-fetching:', sku);
                productList = await loadProducts();
            }
            if (!productList.some((p) => p.productId === sku)) {
                console.warn(
                    '[AppleIAP] Proceeding with requestPurchase despite empty product cache:',
                    sku,
                    'loaded products:',
                    productList.map((p) => p.productId),
                );
            }

            requestInFlightRef.current = true;
            setLoading(tier);
            pendingSkuRef.current = sku;
            console.log('[AppleIAP] Requesting purchase:', sku);
            try {
                await requestPurchase({
                    type: 'subs',
                    request: {
                        apple: {
                            sku,
                            appAccountToken: user.id,
                        },
                    },
                });
                return true;
            } catch (e: unknown) {
                requestInFlightRef.current = false;
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
        [user?.id, requestPurchase, connected, products, loadProducts],
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
        products,
    };
}
