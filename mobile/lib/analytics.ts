/**
 * Lightweight product analytics (spec 0.9). Fire-and-forget with a tiny
 * batch queue - analytics must never slow down or break a user action.
 * Event names mirror the backend allowlist exactly.
 */
import api from '../services/api';

export type AnalyticsEvent =
    | 'reveal_completed'
    | 'done_tapped'
    | 'snooze'
    | 'nudge_acted'
    | 'paywall_view'
    | 'enter'
    | 'day_closed'
    | 'lock_in'
    | 'freeze_used'
    | 'review_confirmed'
    | 'onboarding_step'
    | 'onboarding_chat_setup'
    // Paywall / purchase funnel. onboarding_step (with a `step` prop) carries
    // every pre-paywall milestone; these capture the paywall→purchase leg.
    | 'plan_selected'
    | 'purchase_started'
    | 'purchase_success'
    | 'purchase_failed'
    // Sheet dismissed / cancelled / verification declined — distinct from
    // purchase_failed (an error): the user simply didn't complete the buy.
    | 'purchase_not_completed';

let queue: { event: AnalyticsEvent; props?: Record<string, unknown> }[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

async function flush() {
    flushTimer = null;
    if (!queue.length) return;
    const batch = queue.splice(0, 25);
    try {
        await api.trackEvents(batch);
    } catch {
        // drop on failure - analytics never retries into a user's data plan
    }
}

export function track(event: AnalyticsEvent, props?: Record<string, unknown>) {
    queue.push({ event, props });
    if (queue.length >= 10) {
        void flush();
        return;
    }
    if (!flushTimer) {
        flushTimer = setTimeout(() => void flush(), 3000);
    }
}
