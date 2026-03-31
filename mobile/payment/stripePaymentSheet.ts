/**
 * Web / fallback: native Payment Sheet lives in stripePaymentSheet.native.ts (Metro resolution).
 */

export type SubscriptionTier = 'chadlite' | 'chad';

export type PresentSubscriptionResult =
    | { kind: 'skipped' }
    | { kind: 'paid' }
    | { kind: 'canceled' }
    | { kind: 'error'; message: string };

export async function presentSubscriptionPaymentSheet(_params: {
    tier: SubscriptionTier;
    finishAfterPayment: () => Promise<void>;
}): Promise<PresentSubscriptionResult> {
    return { kind: 'skipped' };
}
