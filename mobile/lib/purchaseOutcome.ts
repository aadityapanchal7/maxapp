/**
 * A one-shot "did the purchase actually happen?" promise.
 *
 * WHY THIS EXISTS: react-native-iap's `requestPurchase()` resolves as soon as the
 * request is handed to StoreKit — NOT when the user finishes paying. Awaiting it
 * reported success while Apple's sheet was still open, so a cancelled or failed
 * purchase still walked the user forward into account creation (a paywall
 * bypass). The real result only ever arrives asynchronously on the
 * onPurchaseSuccess / onPurchaseError listeners, so the caller must await
 * something those listeners settle. That is this.
 *
 * Guarantees:
 *  - resolves EXACTLY once (later settles are ignored — StoreKit replays a
 *    transaction more than once, and both a success and an error can arrive),
 *  - never hangs forever: if no listener reports back within `timeoutMs` it
 *    resolves `false` (treat as NOT purchased — never assume payment),
 *  - `false` is always the safe default, so every failure mode keeps the user
 *    on the paywall rather than granting access.
 */
export type PurchaseOutcome = {
    /** Await this for the REAL result: true only for a verified entitlement. */
    promise: Promise<boolean>;
    /** Report the outcome. Safe to call multiple times; only the first wins. */
    settle: (ok: boolean) => void;
    /** True until something has settled it. */
    isPending: () => boolean;
};

export function createPurchaseOutcome(
    timeoutMs: number,
    onTimeout?: () => void,
): PurchaseOutcome {
    let settled = false;
    let resolveFn: (ok: boolean) => void = () => undefined;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const promise = new Promise<boolean>((resolve) => {
        resolveFn = resolve;
    });

    const settle = (ok: boolean): void => {
        if (settled) return;
        settled = true;
        if (timer !== null) {
            clearTimeout(timer);
            timer = null;
        }
        resolveFn(ok);
    };

    timer = setTimeout(() => {
        if (settled) return;
        // Nothing reported back. Do NOT assume a purchase.
        onTimeout?.();
        settle(false);
    }, timeoutMs);

    return { promise, settle, isPending: () => !settled };
}
