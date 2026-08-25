import { useCallback, useEffect, useRef, useState } from 'react';
import { InteractionManager } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useIsFocused } from '@react-navigation/native';
import { useAuth } from '../../context/AuthContext';
import { useFlag } from '../../constants/featureFlags';
import api from '../../services/api';

// Local "seen" flag, written the moment the walkthrough SHOWS (not only on a
// clean finish). A frozen / force-quit session never reaches the finish
// handler, so without this the server `main_app_tour_completed` stays false
// and the walkthrough re-fires on every launch. Key kept from the old
// spotlight tour on purpose: users who saw THAT must not also see THIS.
export const MAIN_TOUR_SEEN_KEY = 'main_app_tour_seen_v1';

// ── Cross-tree visibility signal ─────────────────────────────────────────────
// The auto-enroll pass earns "First Steps" DURING the walkthrough, and the
// achievement celebration host would stack its overlay on top of ours — two
// scrims, two CTAs, on the user's very first screen. The host subscribes here
// and holds celebrations until the walkthrough closes (its queue survives).
let _walkthroughVisible = false;
const _visListeners = new Set<(v: boolean) => void>();

function setWalkthroughVisible(v: boolean) {
    if (_walkthroughVisible === v) return;
    _walkthroughVisible = v;
    _visListeners.forEach((l) => l(v));
}

/** Reactive: true while the first-run walkthrough overlay is on screen. */
export function useWalkthroughVisible(): boolean {
    const [v, setV] = useState(_walkthroughVisible);
    useEffect(() => {
        _visListeners.add(setV);
        setV(_walkthroughVisible);
        return () => { _visListeners.delete(setV); };
    }, []);
    return v;
}

/**
 * Visibility brain for the first-run walkthrough (the guided-first-actions
 * overlay that replaced the react-native-spotlight-tour spotlight tour).
 *
 * The old tour spotlighted five UI regions, which meant anchor refs, measure
 * retries, and a zero-spot watchdog to escape an untouchable backdrop. The
 * walkthrough is a self-contained bottom card with real actions (open your
 * first task / open chat), so all of that machinery is gone — this hook is
 * ONLY the gating:
 *  - `mainAppTour` kill-switch flag (name kept for backend override compat),
 *  - user is paid, Home focused,
 *  - not still in the post-subscription scan flow, no post-pay redirect
 *    in flight,
 *  - not already seen (local key OR server `main_app_tour_completed`).
 *
 * Show/seen semantics match the old tour exactly: mark seen (local + server,
 * best-effort) the instant it becomes visible, and converge the server flag
 * again on finish.
 */
export function useFirstRunWalkthrough(opts: { redirectPending: boolean }) {
    const { user, isPaid, refreshUser } = useAuth();
    const isFocused = useIsFocused();
    const enabled = useFlag('mainAppTour');
    const { redirectPending } = opts;

    const [visible, setVisible] = useState(false);
    // Once shown (or ruled out for this session), never re-fire.
    const decidedRef = useRef(false);
    // null = still reading the local seen key; boolean once known.
    const [seenLocally, setSeenLocally] = useState<boolean | null>(null);

    useEffect(() => {
        let cancelled = false;
        AsyncStorage.getItem(MAIN_TOUR_SEEN_KEY)
            .then((v) => { if (!cancelled) setSeenLocally(v === '1'); })
            .catch(() => { if (!cancelled) setSeenLocally(false); });
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        if (decidedRef.current || visible) return;
        if (!enabled || !isPaid || !isFocused) return;
        if (seenLocally !== false) return;   // unknown yet, or already seen
        const ob = user?.onboarding as Record<string, unknown> | undefined;
        if (ob?.post_subscription_onboarding) return;   // scan reveal still pending
        if (ob?.main_app_tour_completed) return;        // server says seen
        if (redirectPending) return;
        // Let the post-pay navigation dust settle, then re-check and show.
        const task = InteractionManager.runAfterInteractions(() => {
            if (decidedRef.current) return;
            const ob2 = user?.onboarding as Record<string, unknown> | undefined;
            if (ob2?.post_subscription_onboarding) return;
            decidedRef.current = true;
            // Persist "seen" the instant we show — survives a crash before the
            // finish handler. Local first (authoritative), server best-effort.
            AsyncStorage.setItem(MAIN_TOUR_SEEN_KEY, '1').catch(() => {});
            api.completeMainAppTour().catch(() => {});
            setWalkthroughVisible(true);
            setVisible(true);
        });
        return () => task.cancel();
    }, [enabled, isPaid, isFocused, seenLocally, user?.onboarding, redirectPending, visible]);

    // Belt-and-braces: if the hosting screen unmounts with the overlay up,
    // release the celebration hold too.
    useEffect(() => () => setWalkthroughVisible(false), []);

    const finish = useCallback(() => {
        setVisible(false);
        setWalkthroughVisible(false);
        // Converge the server flag + refresh so `main_app_tour_completed`
        // reaches this device's user object (and any other device).
        void api.completeMainAppTour().then(() => refreshUser()).catch(() => {});
    }, [refreshUser]);

    return { visible, finish };
}
