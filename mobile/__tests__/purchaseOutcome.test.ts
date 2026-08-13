/**
 * Purchase-gate invariants. These guard a REVENUE path: the only way a user
 * should reach account creation is a genuinely completed, verified purchase.
 * Every failure mode must resolve `false` so the paywall holds.
 */
import assert from 'assert';
import { createPurchaseOutcome } from '../lib/purchaseOutcome';

export const tests: Record<string, () => void | Promise<void>> = {
    'a verified purchase resolves true': async () => {
        const o = createPurchaseOutcome(1000);
        o.settle(true);
        assert.strictEqual(await o.promise, true);
    },

    'a cancelled purchase resolves false': async () => {
        const o = createPurchaseOutcome(1000);
        o.settle(false);
        assert.strictEqual(await o.promise, false);
    },

    'only the FIRST settle wins (StoreKit can replay a transaction)': async () => {
        const o = createPurchaseOutcome(1000);
        o.settle(false); // user cancelled
        o.settle(true);  // a late/duplicate success must NOT grant access
        assert.strictEqual(await o.promise, false);
    },

    'a duplicate success cannot be downgraded by a later false': async () => {
        const o = createPurchaseOutcome(1000);
        o.settle(true);
        o.settle(false);
        assert.strictEqual(await o.promise, true);
    },

    'isPending flips once settled': () => {
        const o = createPurchaseOutcome(1000);
        assert.strictEqual(o.isPending(), true);
        o.settle(true);
        assert.strictEqual(o.isPending(), false);
    },

    'no listener callback => resolves FALSE, never hangs': async () => {
        let timedOut = false;
        const o = createPurchaseOutcome(10, () => { timedOut = true; });
        assert.strictEqual(await o.promise, false, 'must default to NOT purchased');
        assert.strictEqual(timedOut, true, 'timeout hook should fire for cleanup');
    },

    'settling before the timeout cancels it (no late false)': async () => {
        let timedOut = false;
        const o = createPurchaseOutcome(10, () => { timedOut = true; });
        o.settle(true);
        assert.strictEqual(await o.promise, true);
        await new Promise((r) => setTimeout(r, 30)); // outlive the timer
        assert.strictEqual(timedOut, false, 'timeout must not fire after settle');
        assert.strictEqual(await o.promise, true, 'result must stay true');
    },
};
