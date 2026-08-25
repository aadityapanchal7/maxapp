/**
 * Feature flags — built-in DEFAULTS that can be OVERRIDDEN from the backend at
 * runtime (GET /config/flags), so features can be toggled without an app rebuild.
 *
 * Safety: the app ALWAYS starts from DEFAULT_FLAGS and only lets the server override
 * known boolean keys. If the flags endpoint is slow, unreachable, or returns junk,
 * every `useFlag`/`getFlag` reads the built-in default — i.e. today's exact behavior.
 * Toggle a flag from the DB (system_prompts row `feature_flags_json`, a JSON object
 * like {"newNav": true}); the change reaches clients on their next flags fetch.
 */
import React, { createContext, useContext, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../services/api';

export type FlagName =
    | 'faceScan'
    | 'personalizedUI'
    | 'referrals'
    | 'mainAppTour';

const DEFAULT_FLAGS: Record<FlagName, boolean> = {
    faceScan: true,
    // Referral / promo codes. Must match the backend `referrals_enabled` flag.
    referrals: true,
    // Tasteful, additive on-screen personalization; each surface degrades to
    // today's copy when its signal is absent, so ON is cold-start-identical.
    personalizedUI: true,
    // Post-onboarding first-run walkthrough (features/mainTour).
    mainAppTour: true,
};

// Module mirror of the currently-active (merged) flags, kept in sync by the
// provider so the non-hook getFlag()/allFlags() helpers reflect remote values too.
let CURRENT: Record<FlagName, boolean> = { ...DEFAULT_FLAGS };

const FlagsContext = createContext<Record<FlagName, boolean>>(DEFAULT_FLAGS);

/**
 * Fetches remote flag overrides once (cached) and provides the merged flag set to
 * the tree. Wrap the app in this (inside the React Query provider). On any error
 * the merged set equals DEFAULT_FLAGS, so it can never break the app.
 */
export function FeatureFlagsProvider({ children }: { children: React.ReactNode }) {
    const { data } = useQuery({
        queryKey: ['feature-flags'],
        queryFn: () => api.getFeatureFlags(),
        staleTime: 5 * 60 * 1000, // re-check at most every 5 min
        gcTime: 24 * 60 * 60 * 1000,
        retry: 1,
    });

    const merged = useMemo(() => {
        const m: Record<FlagName, boolean> = { ...DEFAULT_FLAGS };
        if (data && typeof data === 'object') {
            (Object.keys(DEFAULT_FLAGS) as FlagName[]).forEach((k) => {
                const v = (data as Record<string, unknown>)[k];
                if (typeof v === 'boolean') m[k] = v;
            });
        }
        return m;
    }, [data]);

    useEffect(() => {
        CURRENT = merged;
    }, [merged]);

    return <FlagsContext.Provider value={merged}>{children}</FlagsContext.Provider>;
}

/** Hook: reactive flag value. Reads the merged remote+default set (default outside provider). */
export function useFlag(name: FlagName): boolean {
    return useContext(FlagsContext)[name] ?? DEFAULT_FLAGS[name];
}

/** Non-hook accessor for use outside React (returns the latest merged value). */
export function getFlag(name: FlagName): boolean {
    return CURRENT[name] ?? DEFAULT_FLAGS[name];
}

