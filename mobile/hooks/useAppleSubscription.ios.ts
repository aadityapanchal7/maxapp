import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native'
import { Alert } from '../components/InAppAlert';
import { useQueryClient } from '@tanstack/react-query';
import {
    useIAP,
    ErrorCode,
    // Use the STANDALONE fetchProducts/getAvailablePurchases — they RESOLVE to the
    // arrays. The useIAP() wrappers of the same name return Promise<void> and only
    // push results into the hook's internal state, so `await hookFetchProducts()`
    // is always undefined → the paywall saw 0 products ("Plan not available yet").
    fetchProducts as fetchProductsRaw,
    getAvailablePurchases as getAvailablePurchasesRaw,
    type Purchase,
    type Product,
} from 'react-native-iap';
import { APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU } from '../constants/appleIap';
import { useAuth } from '../context/AuthContext';
import { prefetchMainTabData } from '../lib/prefetchMainTabData';
import { createPurchaseOutcome, type PurchaseOutcome } from '../lib/purchaseOutcome';
import { queryKeys } from '../lib/queryClient';
import { markPostPayPending } from '../lib/postPayNav';
import { reconcileOwnedSubscriptions } from '../lib/entitlementReconciler';
import api from '../services/api';

// Backstop only. Apple reports cancel/failure through onPurchaseError within
// seconds; this exists so a StoreKit callback that never arrives can't leave the
// paywall's await hanging forever. Long enough to never fire during a real
// purchase (password prompts, 2FA, Ask-to-Buy can be slow).
const PURCHASE_OUTCOME_TIMEOUT_MS = 5 * 60_000;

type Tier = 'basic' | 'premium';

// react-native-iap v14 exposes the StoreKit product identifier as `id`
// (ProductCommon.id); older shapes used `productId`. The pre-purchase gate must
// match on EITHER — matching only `productId` made every check fail on v14
// (productId is undefined there) and surfaced a false "Plan not available yet"
// even when the App Store returned the products correctly.
const productSku = (p: unknown): string | undefined => {
    const o = p as { id?: string; productId?: string } | null | undefined;
    return o?.id ?? o?.productId;
};

export function useAppleSubscription() {
    const { user, refreshUser } = useAuth();
    const queryClient = useQueryClient();
    const [loading, setLoading] = useState<Tier | null>(null);
    const [restoring, setRestoring] = useState(false);
    const pendingSkuRef = useRef<string | null>(null);
    const requestInFlightRef = useRef(false);
    const processedTids = useRef<Set<string>>(new Set());
    const recoveringRef = useRef(false);
    const [products, setProducts] = useState<Product[]>([]);

    // ── Real purchase outcome ───────────────────────────────────────────────
    // react-native-iap's requestPurchase() resolves as soon as the request is
    // HANDED TO StoreKit — not when the purchase completes. Awaiting it therefore
    // reported "success" while Apple's sheet was still open, so a CANCELLED or
    // FAILED purchase still walked the user forward into account creation.
    // The true outcome only ever arrives via onPurchaseSuccess/onPurchaseError,
    // so subscribeTier returns a promise that those listeners settle.
    // See lib/purchaseOutcome.ts (unit-tested in __tests__/purchaseOutcome.test.ts).
    const purchaseOutcomeRef = useRef<PurchaseOutcome | null>(null);

    /** Settle the in-flight purchase promise exactly once. No-ops for StoreKit
     *  replays/restores, which have no waiting caller. */
    const settlePurchase = useCallback((ok: boolean) => {
        const pending = purchaseOutcomeRef.current;
        if (!pending) return;
        purchaseOutcomeRef.current = null;
        pending.settle(ok);
    }, []);

    const { connected, requestPurchase, finishTransaction } =
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

                // Only a fully verified, non-expired entitlement counts as a
                // purchase for the awaiting caller — every other exit settles false.
                let verified = false;

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

                    // Mark BEFORE refreshUser so the flag is already set when
                    // refreshUser flips isPaid and App.tsx's effect fires. Only
                    // for a real user-initiated purchase — never a StoreKit
                    // replay/restore — so existing subscribers aren't dropped
                    // into the post-pay flow on launch.
                    if (isUserInitiated) markPostPayPending();
                    await refreshUser();
                    void queryClient.invalidateQueries({ queryKey: queryKeys.maxes });
                    prefetchMainTabData(queryClient);
                    verified = true;
                } finally {
                    // Settling in `finally` guarantees exactly one settle on every
                    // path — including an unexpected throw — so the caller can
                    // never hang waiting on a purchase that already resolved.
                    settlePurchase(verified);
                    requestInFlightRef.current = false;
                    setLoading(null);
                    pendingSkuRef.current = null;
                }
            },
            onPurchaseError: (error: { code?: string; message: string }) => {
                requestInFlightRef.current = false;
                setLoading(null);
                pendingSkuRef.current = null;
                if (error.code === ErrorCode.UserCancelled) {
                    // The user backed out of Apple's sheet: NOT a purchase. The
                    // caller must stay on the paywall.
                    settlePurchase(false);
                    return;
                }

                // FAILSAFE: the Apple ID already owns this subscription (new
                // phone / reinstall / different app account) — StoreKit refuses
                // to re-sell, which used to strand the user at the paywall.
                // Reconcile the owned entitlement with the backend instead: a
                // successful verify flips isPaid and routes them forward like a
                // normal purchase.
                const alreadyOwned =
                    error.code === ErrorCode.AlreadyOwned ||
                    /already\s+(own|subscrib|purchas)/i.test(error.message || '');
                if (alreadyOwned) {
                    console.log('[AppleIAP] Already owned — reconciling entitlement instead of erroring');
                    void (async () => {
                        try {
                            const granted = await reconcileOwnedSubscriptions({ force: true });
                            if (granted) {
                                markPostPayPending(); // BEFORE refreshUser flips isPaid
                                await refreshUser();
                                void queryClient.invalidateQueries({ queryKey: queryKeys.maxes });
                                prefetchMainTabData(queryClient);
                                settlePurchase(true); // entitlement is real — proceed
                                return;
                            }
                            settlePurchase(false);
                            Alert.alert(
                                'Subscription found',
                                "Your Apple ID already has a Max subscription, but it couldn't be activated for this account. Tap Restore Purchases below, or try again in a moment.",
                            );
                        } catch (e) {
                            console.warn('[AppleIAP] already-owned reconcile failed:', e);
                            settlePurchase(false);
                            Alert.alert(
                                'Subscription found',
                                'Your Apple ID already has a Max subscription. Tap Restore Purchases to activate it on this account.',
                            );
                        }
                    })();
                    return;
                }

                console.error('[AppleIAP] Purchase error:', error.code, error.message);
                settlePurchase(false);
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
                let list = ((await fetchProductsRaw({ skus, type: 'subs' })) ?? []) as Product[];
                // Fallback: some react-native-iap v14 setups return [] for
                // type:'subs' on TestFlight even when the subscriptions are
                // approved. Re-query type:'all' and filter to our skus — this
                // sidesteps any subscription-type classification mismatch.
                if (list.length === 0) {
                    console.warn('[AppleIAP] subs fetch empty; retrying as type:all');
                    const all = ((await fetchProductsRaw({ skus, type: 'all' })) ?? []) as Product[];
                    list = all.filter((p) => skus.includes(productSku(p) ?? ''));
                }
                if (list.length > 0) {
                    console.log('[AppleIAP] Products loaded:', list.map((p) => productSku(p)));
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
        [],
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
                // `getAvailablePurchases()` can resolve to `undefined` on iOS
                // when the StoreKit queue is empty or not yet initialised; normalise
                // to an array so downstream `.length` / `for..of` never crash.
                const purchases = (await getAvailablePurchasesRaw()) ?? [];
                console.log('[AppleIAP] Recovering pending purchases:', purchases.length);
                for (const purchase of purchases) {
                    const p = purchase as { transactionId?: string; id?: string; productId?: string };
                    const tid = String(p.transactionId ?? p.id ?? '').trim();
                    if (!tid || processedTids.current.has(tid)) continue;
                    try {
                        await api.verifyAppleIapTransaction(tid, p.productId || undefined);
                        // Only a SUCCESSFUL verify consumes the transaction. A
                        // failed one (network blip, backend 503, signed-out race)
                        // must stay in the queue and stay retryable — the old
                        // finish-and-mark-anyway behavior permanently stranded
                        // "owned but locked out" users for the session.
                        processedTids.current.add(tid);
                        try { await finishTransaction({ purchase }); } catch {}
                        await refreshUser();
                    } catch (err) {
                        console.warn('[AppleIAP] recover verify failed (left retryable):', tid, err);
                    }
                }
            } catch (e) {
                console.warn('[AppleIAP] recoverPending:', e);
            }
        };
        void recoverPending();
    }, [connected, finishTransaction, refreshUser]);

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

            // If the product is already cached, fire requestPurchase immediately
            // so StoreKit opens its sheet with no perceptible delay.
            // If it is NOT cached, do ONE bounded fetch first and confirm THIS
            // sku is actually available before requesting. Firing a purchase for
            // a sku StoreKit doesn't know (e.g. a just-approved product still
            // propagating to sandbox, or a transient empty fetch) silently does
            // nothing — no sheet, no error — which reads as a dead button. A
            // bounded check lets us give real feedback instead.
            let productCached = products.some((p) => productSku(p) === sku);
            if (!productCached) {
                console.log('[AppleIAP] Cache miss at subscribe time; fetching before purchase:', sku);
                try {
                    const list = await loadProducts();
                    productCached = list.some((p) => productSku(p) === sku);
                } catch (err) {
                    console.warn('[AppleIAP] product fetch before purchase failed:', err);
                }
                if (!productCached) {
                    console.error('[AppleIAP] Product not available from StoreKit, aborting purchase:', sku);
                    Alert.alert(
                        'Plan not available yet',
                        "This plan isn't available from the App Store right now. If it was just set up, it can take a little while to appear — please try again shortly.",
                    );
                    return false;
                }
            }

            requestInFlightRef.current = true;
            setLoading(tier);
            pendingSkuRef.current = sku;
            console.log('[AppleIAP] Requesting purchase:', sku);

            // Arm the outcome promise BEFORE requesting, so a listener that fires
            // synchronously still finds somewhere to report to.
            const outcome = createPurchaseOutcome(PURCHASE_OUTCOME_TIMEOUT_MS, () => {
                // StoreKit never reported back — release the UI so the paywall
                // isn't left stuck on "Processing…".
                console.warn('[AppleIAP] No purchase outcome within timeout — treating as not purchased.');
                purchaseOutcomeRef.current = null;
                requestInFlightRef.current = false;
                setLoading(null);
                pendingSkuRef.current = null;
            });
            purchaseOutcomeRef.current = outcome;

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
                // NOTE: requestPurchase resolving means the request reached
                // StoreKit — NOT that the user bought anything. Wait for the
                // listeners to report the real outcome.
                return await outcome.promise;
            } catch (e: unknown) {
                settlePurchase(false);
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
        [user?.id, requestPurchase, connected, products, loadProducts, settlePurchase],
    );

    const subscribeBasic = useCallback(
        () => subscribeTier('basic'),
        [subscribeTier],
    );
    const subscribePremium = useCallback(
        () => subscribeTier('premium'),
        [subscribeTier],
    );

    // User-initiated "Restore Purchases" flow required by Apple
    // (App Review Guideline 3.1.1). Queries StoreKit for the user's
    // prior purchases, re-verifies each with the backend, finalizes
    // the transactions, and refreshes the account.
    const restorePurchases = useCallback(async (): Promise<boolean> => {
        if (Platform.OS !== 'ios') return false;
        if (restoring) return false;
        if (!user?.id) {
            Alert.alert('Sign in', 'Log in to restore purchases.');
            return false;
        }
        if (!connected) {
            Alert.alert(
                'App Store unavailable',
                'Cannot connect to the App Store. Please check your internet connection and try again.',
            );
            return false;
        }

        setRestoring(true);
        let restoredActive = false;
        let attempted = 0;
        try {
            // Normalise to an array — `react-native-iap` has been observed to
            // resolve to `undefined` when there are no prior purchases on the
            // Apple ID, which would otherwise throw "Cannot read property
            // 'length' of undefined" and surface a misleading "Restore failed".
            const purchases = (await getAvailablePurchasesRaw()) ?? [];
            console.log('[AppleIAP] restorePurchases: found', purchases.length, 'purchase(s)');

            for (const purchase of purchases) {
                const p = purchase as { transactionId?: string; id?: string; productId?: string };
                const tid = String(p.transactionId ?? p.id ?? '').trim();
                if (!tid) continue;
                attempted += 1;

                try {
                    const result = await api.verifyAppleIapTransaction(tid, p.productId || undefined);
                    if (result?.status && result.status !== 'expired') {
                        restoredActive = true;
                    }
                } catch (err) {
                    console.warn('[AppleIAP] restore verify failed for', tid, err);
                } finally {
                    try { await finishTransaction({ purchase }); } catch {}
                    processedTids.current.add(tid);
                }
            }

            await refreshUser();
            void queryClient.invalidateQueries({ queryKey: queryKeys.maxes });
            prefetchMainTabData(queryClient);

            if (restoredActive) {
                Alert.alert('Purchases restored', 'Your subscription has been restored on this device.');
            } else if (attempted === 0) {
                Alert.alert(
                    'Nothing to restore',
                    'No previous purchases were found for your Apple ID on this device. If you believe this is wrong, make sure you are signed in to the App Store with the Apple ID used for the original purchase.',
                );
            } else {
                Alert.alert(
                    'No active subscription',
                    'We found previous transactions, but none are currently active. If your subscription expired, please subscribe again.',
                );
            }
            return restoredActive;
        } catch (e: unknown) {
            console.error('[AppleIAP] restorePurchases failed:', e);
            const msg = (e as Error)?.message || 'Could not restore purchases. Please try again.';
            Alert.alert('Restore failed', String(msg));
            return false;
        } finally {
            setRestoring(false);
        }
    }, [
        restoring,
        user?.id,
        connected,
        finishTransaction,
        refreshUser,
        queryClient,
    ]);

    return {
        loading,
        restoring,
        subscribeBasic,
        subscribePremium,
        subscribeTier,
        restorePurchases,
        storeConnected: connected,
        products,
    };
}
