/**
 * AchievementCelebrationHost — fires the celebration the moment a badge is earned.
 *
 * The day-state endpoint (/schedules/active/full) returns `newly_earned_achievements`
 * exactly once, on the response where the badge was first awarded. This host
 * reads that query's cache (it does NOT drive fetching — Today/Home do), catches
 * the transient value, queues a CelebrationOverlay, and marks the badges seen so
 * it never double-fires. Mount once inside the authenticated app.
 *
 * Timing: the badge is captured immediately, but the overlay is HELD while the
 * user is in a focused flow (mid face-scan, onboarding, auth) so it never pops
 * over the camera. It appears once they land on a calm screen.
 */
import React, { useEffect, useRef, useState } from 'react';
import { InteractionManager } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import api, { EarnedAchievement } from '../../services/api';
import { queryKeys } from '../../lib/queryClient';
import { navigationRef } from '../../lib/navigationRef';
import { useWalkthroughVisible } from '../../features/mainTour/useMainAppTour';
import CelebrationOverlay from './CelebrationOverlay';

// Screens where a full-screen celebration would interrupt — the camera/scan
// flow, the onboarding + paywall funnel, auth, and setup flows. The badge still
// gets captured + marked seen; the overlay just waits until the user is elsewhere.
const SUPPRESS_ROUTES = new Set<string>([
    'FaceScan', 'FaceScanResults', 'FaceScanArchive', 'ModuleSelect',
    'Onboarding', 'RoutineReveal', 'FeaturesIntro', 'Payment',
    'Landing', 'Login', 'Signup', 'ForgotPassword',
    // TaskGuide is a fullScreenModal: presenting the celebration's transparent
    // RN Modal while it is mid-presentation collides on iOS and can strand an
    // invisible touch-eating Modal window (verified in the sim: the whole app
    // stopped responding). It's also an immersive guide — never celebrate
    // over it; the overlay waits for the user to come back out.
    'TaskGuide',
]);

function useCurrentRouteName(): string | undefined {
    const [name, setName] = useState<string | undefined>(
        () => (navigationRef.isReady() ? navigationRef.getCurrentRoute()?.name : undefined),
    );
    useEffect(() => {
        const update = () => setName(navigationRef.isReady() ? navigationRef.getCurrentRoute()?.name : undefined);
        update();
        // The container ref is ready by the time this host mounts (user is in
        // the app), so the 'state' subscription fires on every navigation.
        const unsub = navigationRef.isReady() ? navigationRef.addListener('state', update) : undefined;
        return unsub;
    }, []);
    return name;
}

export default function AchievementCelebrationHost() {
    // enabled:false — purely reads the cache Today/Home populate, never fetches.
    const { data } = useQuery({
        queryKey: queryKeys.schedulesActiveFull,
        queryFn: () => api.getActiveSchedulesFull(),
        enabled: false,
    });
    const shown = useRef<Set<string>>(new Set());
    const [queue, setQueue] = useState<EarnedAchievement[]>([]);
    // The frozen batch currently being celebrated. Freezing it (rather than
    // handing the live, growing `queue` to the overlay and clearing it wholesale
    // on done) means a badge that arrives mid-celebration is NOT dropped by the
    // done handler — it stays queued and gets its own celebration next.
    const [showing, setShowing] = useState<EarnedAchievement[] | null>(null);
    const routeName = useCurrentRouteName();

    const fresh = (data as any)?.newly_earned_achievements as EarnedAchievement[] | undefined;
    useEffect(() => {
        const list = (fresh || []).filter((a) => a && !shown.current.has(a.code));
        if (!list.length) return;
        list.forEach((a) => shown.current.add(a.code));
        setQueue((q) => [...q, ...list]);
        // NOTE: mark-seen is deferred until the badge is actually displayed
        // (the promote effect below), not fired here at capture.
    }, [fresh]);

    // Hold the celebration until the user is on a calm screen (not mid-scan etc.)
    // — and never underneath/on top of the first-run walkthrough (the auto-enroll
    // pass earns "First Steps" while it's up; the queue survives and promotes
    // the moment the walkthrough closes).
    const walkthroughUp = useWalkthroughVisible();
    const onSafeScreen = !!routeName && !SUPPRESS_ROUTES.has(routeName) && !walkthroughUp;

    // Promote the pending queue to a frozen "showing" batch once we're on a safe
    // screen and nothing is currently celebrating. Mark those seen now (they're
    // about to be displayed).
    //
    // Deferred past the interaction settle, with the route RE-CHECKED after:
    // promoting in the same tick as a navigation (e.g. the walkthrough's
    // "open it" both closes the walkthrough — releasing this hold — and
    // presents TaskGuide) races our transparent Modal against the screen's own
    // modal presentation, which iOS resolves by stranding an invisible
    // touch-eating Modal window. Never present mid-transition.
    useEffect(() => {
        if (showing || !onSafeScreen || !queue.length) return;
        let cancelled = false;
        const task = InteractionManager.runAfterInteractions(() => {
            if (cancelled) return;
            const route = navigationRef.isReady()
                ? (navigationRef.getCurrentRoute() as { name?: string } | undefined)?.name
                : undefined;
            if (!route || SUPPRESS_ROUTES.has(route)) return; // re-runs on next route change
            const batch = queue;
            setShowing(batch);
            api.markAchievementsSeen(batch.map((a) => a.code)).catch(() => {});
        });
        return () => { cancelled = true; task.cancel(); };
    }, [showing, onSafeScreen, queue]);

    if (!showing || !onSafeScreen) return null;
    return (
        <CelebrationOverlay
            queue={showing}
            onDone={() => {
                // Drop exactly the celebrated codes — anything appended during
                // the celebration survives and triggers the next batch.
                const shownCodes = new Set(showing.map((a) => a.code));
                setQueue((q) => q.filter((a) => !shownCodes.has(a.code)));
                setShowing(null);
            }}
        />
    );
}
