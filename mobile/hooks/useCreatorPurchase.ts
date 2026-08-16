/**
 * Per-creator IAP purchase (production path), mirroring the fixed main
 * paywall (see hooks/useAppleSubscription.ios.ts + lib/purchaseOutcome.ts).
 *
 * Each creator has its OWN auto-renewable SKU in its own subscription group
 * (Apple subs within a group are mutually exclusive, and a user must be able
 * to hold several creator subs). iOS-only, react-native-iap v14: uses the
 * STANDALONE fetchProducts (the useIAP() version returns void), product id
 * is `p.id`/`p.productId`, and the purchase carries `appAccountToken = user.id`
 * so the backend resolves the account. In dev builds the caller uses the
 * dev-activate endpoint instead of this (see CreatorPaywallScreen).
 *
 * WHY THIS IS A HOOK (and not a plain async function, as it was before):
 * react-native-iap v14's requestPurchase() resolves `Promise<void>` (a
 * hardcoded `[]` on iOS) the instant the request reaches StoreKit — NOT when
 * the user finishes paying. The previous implementation awaited that return
 * value and derived a transaction id from it, so `result` was ALWAYS
 * undefined and every purchase threw "Purchase did not return a transaction
 * id" — after the user had already been charged, with no entitlement ever
 * granted. The real outcome only ever arrives via
 * onPurchaseSuccess/onPurchaseError, so this hook mounts those listeners with
 * useIAP() and awaits a createPurchaseOutcome() promise that they settle once
 * the REAL StoreKit transaction id is known and verified with the backend.
 * See lib/purchaseOutcome.ts (unit-tested in __tests__/purchaseOutcome.test.ts).
 */
import { useCallback, useRef } from 'react';
import { Platform } from 'react-native';
import {
    useIAP,
    ErrorCode,
    // STANDALONE fetchProducts resolves to the array; the useIAP() wrapper of
    // the same name returns Promise<void> and only pushes results into the
    // hook's internal state.
    fetchProducts as fetchProductsRaw,
    type Purchase,
} from 'react-native-iap';
import { createPurchaseOutcome, type PurchaseOutcome } from '../lib/purchaseOutcome';
import api from '../services/api';

// Same backstop as the main paywall: Apple reports cancel/failure within
// seconds via the listeners; this only guards a StoreKit callback that never
// arrives, so a stuck "Processing…" state can't hang forever.
const PURCHASE_OUTCOME_TIMEOUT_MS = 5 * 60_000;

export type CreatorSubscribeResult = {
    status: string;
    schedule_created?: boolean;
    schedule_blocked?: string | null;
};

type ArmedPurchase = { maxxId: string; productId: string };

export function useCreatorPurchase() {
    const armedRef = useRef<ArmedPurchase | null>(null);
    const requestInFlightRef = useRef(false);
    const processedTids = useRef<Set<string>>(new Set());
    const resultRef = useRef<CreatorSubscribeResult | null>(null);
    const errorRef = useRef<unknown>(null);

    // ── Real purchase outcome ───────────────────────────────────────────────
    // See hooks/useAppleSubscription.ios.ts for the full rationale — this
    // mirrors it exactly.
    const purchaseOutcomeRef = useRef<PurchaseOutcome | null>(null);

    /** Settle the in-flight purchase promise exactly once. No-ops when nothing
     *  is waiting (a stray/replayed transaction with no live caller). */
    const settlePurchase = useCallback((ok: boolean) => {
        const pending = purchaseOutcomeRef.current;
        if (!pending) return;
        purchaseOutcomeRef.current = null;
        pending.settle(ok);
    }, []);

    const { requestPurchase, finishTransaction } = useIAP({
        onPurchaseSuccess: async (purchase: Purchase) => {
            if (Platform.OS !== 'ios') return;
            const p = purchase as { transactionId?: string; id?: string; productId?: string };
            const tid = String(p.transactionId ?? p.id ?? '').trim();
            const incomingProductId = p.productId || undefined;
            // Capture the armed purchase SYNCHRONOUSLY, before any `await`
            // below — armedRef can be reassigned by a NEW
            // purchaseCreatorSubscription() call while this listener is still
            // mid-flight. This event resolves the LIVE in-flight purchase only
            // if it's for the same product the caller is actually waiting on
            // (or the SDK reported no productId at all, in which case there's
            // nothing to disambiguate against). A replayed/stray transaction
            // for a DIFFERENT product must still be verified+finalized below,
            // but must NEVER settle or clear a different, still-pending
            // purchase — same correlation fix as useAppleSubscription.ios.ts.
            const armed = armedRef.current;
            const isArmedMatch = !!armed && (!incomingProductId || incomingProductId === armed.productId);

            const finalize = async () => {
                try { await finishTransaction({ purchase }); } catch (err) {
                    console.warn('[CreatorIAP] finishTransaction error (non-fatal):', err);
                }
            };

            let verified = false;
            try {
                if (!tid) {
                    console.error('[CreatorIAP] Missing transaction id from StoreKit purchase:', JSON.stringify(p));
                    if (isArmedMatch) errorRef.current = new Error('Purchase did not return a transaction id.');
                    await finalize();
                    return;
                }
                if (processedTids.current.has(tid)) {
                    console.log('[CreatorIAP] Duplicate tid, finishing:', tid);
                    await finalize();
                    return;
                }
                processedTids.current.add(tid);

                const maxxId = isArmedMatch ? armed?.maxxId : undefined;
                if (!maxxId) {
                    // Stray/replayed transaction with no live creator purchase
                    // waiting on it — finalize so StoreKit stops replaying it;
                    // there's nothing to verify against or settle.
                    console.warn('[CreatorIAP] No armed creator purchase for incoming transaction:', tid);
                    await finalize();
                    return;
                }

                console.log('[CreatorIAP] Verifying transaction:', tid, 'product:', incomingProductId, 'maxx:', maxxId);
                let result: CreatorSubscribeResult | undefined;
                try {
                    result = await api.verifyCreatorSubscription(maxxId, tid, incomingProductId);
                } catch (e: unknown) {
                    console.error('[CreatorIAP] Purchase verification failed:', e);
                    errorRef.current = e;
                    await finalize();
                    return;
                }
                await finalize();
                resultRef.current = result ?? null;
                verified = true;
            } finally {
                // Settling — and clearing the in-flight refs — only happens for
                // the event that corresponds to the ARMED purchase. A
                // non-matching replay must never resolve (or clear the state
                // of) a different purchase that's still awaiting its own
                // outcome.
                if (isArmedMatch) {
                    settlePurchase(verified);
                    requestInFlightRef.current = false;
                    armedRef.current = null;
                }
            }
        },
        onPurchaseError: (error: { code?: string; message: string; productId?: string | null }) => {
            const armed = armedRef.current;
            const isArmedMatch = !!armed && (!error.productId || error.productId === armed.productId);
            if (!isArmedMatch) {
                // Not the purchase we're waiting on (or nothing is in flight) —
                // a stray/replayed error must not touch the live request's state.
                console.warn('[CreatorIAP] Ignoring non-matching purchase error:', error.code, error.productId);
                return;
            }
            requestInFlightRef.current = false;
            armedRef.current = null;
            if (error.code === ErrorCode.UserCancelled) {
                errorRef.current = new Error('Purchase was cancelled.');
                settlePurchase(false);
                return;
            }
            console.error('[CreatorIAP] Purchase error:', error.code, error.message);
            errorRef.current = new Error(error.message || 'Something went wrong.');
            settlePurchase(false);
        },
    });

    /**
     * Buy `productId` for creator `maxxId`. Resolves the VERIFIED backend
     * result — never the raw StoreKit return value (v14's requestPurchase()
     * resolves before the user has actually paid). Throws on cancel, failure,
     * or timeout — using the original backend error object when available, so
     * the caller's existing `e?.response?.data?.detail` handling keeps working
     * unchanged.
     */
    const purchaseCreatorSubscription = useCallback(
        async (maxxId: string, productId: string, appAccountToken: string): Promise<CreatorSubscribeResult> => {
            if (Platform.OS !== 'ios') {
                throw new Error('Creator subscriptions are only available on iOS right now.');
            }
            if (requestInFlightRef.current) {
                throw new Error('A purchase is already in progress.');
            }

            // Ensure the product is loaded so the sheet has price/terms; the
            // request below still surfaces a real error if the SKU is bad.
            try {
                await fetchProductsRaw({ skus: [productId], type: 'subs' });
            } catch {
                /* non-fatal */
            }

            requestInFlightRef.current = true;
            armedRef.current = { maxxId, productId };
            resultRef.current = null;
            errorRef.current = null;

            // Arm the outcome promise BEFORE requesting, so a listener that
            // fires synchronously still finds somewhere to report to.
            const outcome = createPurchaseOutcome(PURCHASE_OUTCOME_TIMEOUT_MS, () => {
                console.warn('[CreatorIAP] No purchase outcome within timeout — treating as not purchased.');
                purchaseOutcomeRef.current = null;
                requestInFlightRef.current = false;
                armedRef.current = null;
            });
            purchaseOutcomeRef.current = outcome;

            try {
                await requestPurchase({
                    type: 'subs',
                    request: { apple: { sku: productId, appAccountToken } },
                });
                // NOTE: requestPurchase resolving only means the request
                // reached StoreKit — NOT that the user bought anything. Wait
                // for the listeners above to report the real, verified outcome.
                const ok = await outcome.promise;
                if (!ok || !resultRef.current) {
                    throw errorRef.current || new Error('Could not verify purchase.');
                }
                return resultRef.current;
            } catch (e) {
                settlePurchase(false);
                requestInFlightRef.current = false;
                armedRef.current = null;
                throw e;
            }
        },
        [requestPurchase, settlePurchase],
    );

    return { purchaseCreatorSubscription };
}
