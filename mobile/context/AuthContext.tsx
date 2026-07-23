/**
 * Auth Context - Global authentication state
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { AppState, type AppStateStatus, Platform } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { getItemAsync } from '../services/storage';
import { ensureFirstRunClean } from '../lib/firstRunGuard';
import api, { subscribeAuthLost } from '../services/api';
import { clearFaceScanDraft, clearPendingFaceScanSubmit } from '../lib/faceScanDraft';
import { clearOnboardingDraft } from '../lib/onboardingDraft';
import { clearRestoredTab } from '../lib/navState';
import { clearTodayWidget } from '../lib/widgetSync';
import { loadFreeTierChoice, saveFreeTierChoice, clearFreeTierChoice } from '../lib/freeTier';
import {
    clearPersistedQueryCache,
    getPersistedCacheUserId,
    setPersistUserId,
} from '../lib/queryPersist';
import { getIosApnsDeviceTokenForBackend } from '../services/registerIosPushToken';

type SubscriptionTier = 'basic' | 'premium' | null;

interface User {
    id: string;
    email: string;
    /** 'password' | 'google'. OAuth accounts have no password to confirm with. */
    auth_provider?: string;
    /** Present when account was created with phone; read-only in profile. */
    phone_number?: string;
    first_name?: string;
    last_name?: string;
    username?: string;
    /** ISO timestamp — used for 2-week username change cooldown */
    last_username_change?: string | null;
    is_paid: boolean;
    subscription_tier?: SubscriptionTier;
    subscription_status?: string | null;
    subscription_end_date?: string | null;
    onboarding: {
        completed: boolean;
        goals: string[];
        experience_level: string;
        age?: number;
        gender?: string;
        /** Metric users: cm/kg. Imperial users: inches/lbs. */
        height?: number;
        /** Metric users: kg. Imperial users: lbs. */
        weight?: number;
        /** Canonical always-metric values (populated by backend; may be missing for legacy users). */
        height_cm?: number;
        weight_kg?: number;
        activity_level?: string;
        skin_type?: string;
        equipment?: string[];
        unit_system?: string;
        timezone?: string;
        post_subscription_onboarding?: boolean;
        /** True after user finishes (or dismisses) the post-pay spotlight tour */
        main_app_tour_completed?: boolean;
        /** False after payment until user completes in-app Sendblue SMS step */
        sendblue_connect_completed?: boolean;
        /** True after user texts the Sendblue line; enables automated SMS from the server */
        sendblue_sms_engaged?: boolean;
        /** Chat reply verbosity preference — concise | medium | detailed (missing = medium default) */
        response_length?: 'concise' | 'medium' | 'detailed';
        facial_scan_summary?: {
            overall_score?: number;
            potential_score?: number;
            archetype?: string;
            suggested_modules?: string[];
            scan_completed_at?: string;
        };
        [key: string]: unknown;
    };
    profile: {
        current_level: number;
        rank: number;
        streak_days: number;
        bio?: string;
        avatar_url?: string;
        master_schedule_streak?: number;
        master_schedule_streak_last_perfect_date?: string | null;
    };
    first_scan_completed: boolean;
    is_admin: boolean;
    is_scan_user: boolean;
    /** True for an approved+provisioned creator (unlocks the Creator Studio tab). */
    is_creator?: boolean;
    /** Bot tone preference. Drawer surfaces this as hardcore/mediumcore/softcore. */
    coaching_tone?: 'default' | 'hardcore' | 'gentle' | 'influencer';
    /** Server has an APNs token on file (iOS push). */
    has_apns_token?: boolean;
}

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    isPaid: boolean;
    isPremium: boolean;
    isScanUser: boolean;
    /** True for an approved creator — unlocks the Creator Studio. */
    isCreator: boolean;
    /** True for an unclaimed anonymous "guest" account — must claim an account before the paywall/app. */
    isAnonymous: boolean;
    /**
     * User tapped "Continue with the free plan" on the paywall. Grants UI access
     * only — every real action is bounced to Payment by usePaywallGate, and the
     * backend still treats the user as unpaid. Always false once isPaid.
     */
    isFreeTier: boolean;
    /** Persist the free-plan choice and enter the main app unpaid. */
    chooseFreeTier: () => Promise<void>;
    subscriptionTier: SubscriptionTier;
    login: (identifier: string, password: string) => Promise<void>;
    signup: (email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) => Promise<void>;
    fauxSignup: () => Promise<void>;
    fauxSkipSignup: () => Promise<void>;
    /** DEV: throwaway account with EMPTY onboarding (lands on step 1). */
    fauxFreshSignup: () => Promise<void>;
    /** DEV: flip the CURRENT account's admin flag (jump into/out of the admin
     *  view as the same user). Returns the new is_admin value. */
    devToggleAdmin: () => Promise<boolean>;
    startAnon: () => Promise<void>;
    claimAccount: (email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) => Promise<void>;
    /** Sign in / up with a verified Google ID token (find-or-create). Returns the
     *  resolved user so callers can tell a CLAIM (same id) from an account switch. */
    signInWithGoogle: (idToken: string) => Promise<User>;
    /** DEV-only Google identity path (no real token) for localhost testing. */
    signInWithGoogleDev: (email: string, name?: string) => Promise<User>;
    /** Sign in / up with a verified Sign in with Apple identity token (find-or-create). */
    signInWithApple: (identityToken: string, opts?: { givenName?: string; familyName?: string; email?: string }) => Promise<User>;
    logout: () => Promise<void>;
    /** Returns latest user from API (e.g. after payment) so callers can branch before next render. */
    refreshUser: () => Promise<User>;
    /** Permanently delete the signed-in account (App Store account-deletion requirement). */
    deleteAccount: (password?: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Best-effort reset of the native Google Sign-In SDK session. Without this, after
// an app logout the SDK keeps its cached Google session, and a later signIn() can
// return a null idToken → "Google did not return a token" (can't re-sign-in).
async function resetGoogleNativeSession(): Promise<void> {
    if (Platform.OS === 'web') return;
    try {
        const { GoogleSignin } = require('@react-native-google-signin/google-signin');
        await GoogleSignin.signOut();
    } catch {
        /* not signed in via Google / module unavailable — harmless no-op */
    }
}

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [freeTierChosen, setFreeTierChosen] = useState(false);
    const queryClient = useQueryClient();

    // Restore the per-user "continue free" choice whenever the signed-in user
    // changes (boot restore, login, claim). A different account never inherits it.
    useEffect(() => {
        let cancelled = false;
        if (!user?.id) {
            setFreeTierChosen(false);
            return;
        }
        void loadFreeTierChoice(user.id).then((chosen) => {
            if (!cancelled) setFreeTierChosen(chosen);
        });
        return () => {
            cancelled = true;
        };
    }, [user?.id]);

    const checkAuth = useCallback(async () => {
        if (__DEV__) {
            const base = api.getBaseUrl();
            // Physical devices cannot reach the host machine via 127.0.0.1 / localhost.
            if (Platform.OS !== 'web' && /127\.0\.0\.1|localhost/i.test(base)) {
                console.warn(
                    '[Max] EXPO_PUBLIC_API_BASE_URL points at loopback on a native build. ' +
                        'Use your computer’s LAN IP (e.g. http://10.x.x.x:8000/api/) and `npx expo start --lan`, ' +
                        'or use the hosted API URL from mobile/.env comments.',
                );
            }
            // Do not await — health check used to block boot for up to 12s on web and felt like a hang.
            void api.checkBackendHealth({ timeoutMs: 4_000 }).then((healthy) => {
                if (!healthy) {
                    const root = base.replace(/\/?api\/?$/i, '').replace(/\/+$/, '');
                    console.warn(
                        `[Max] Backend unreachable at ${base} (${root}/health failed). ` +
                            'Start uvicorn (maxapp/backend, port 8000), set EXPO_PUBLIC_API_BASE_URL in mobile/.env ' +
                            '(must end with /api/). On a phone, use your Mac LAN IP, not 127.0.0.1.',
                    );
                } else {
                    console.log(`[Max] API OK — ${base}`);
                }
            });
        }
        try {
            // Clear an inherited token on a genuine fresh (re)install so the app
            // starts at Landing, not mid-funnel from a prior install's session.
            // Memoized + shared with App.tsx boot; runs before persistence writes
            // and before we read the token here. See lib/firstRunGuard.
            await ensureFirstRunClean();
            const token = await getItemAsync('access_token');
            if (token) {
                // Generous timeout + one retry on the boot restore so a cold-Render
                // wake or a transient blip resumes the session instead of throwing
                // and dropping the user to Landing for that launch.
                let userData: User;
                try {
                    userData = await api.getMe({ timeout: 45_000 });
                } catch (firstErr: any) {
                    const s = firstErr?.response?.status;
                    if (s === 403) throw firstErr;  // definitive (blocked) — let the catch below handle it
                    // Everything else gets one more try — INCLUDING 401: the api
                    // layer refreshes on 401, and a refresh that failed transiently
                    // (cold-Render wake outliving the timeout, brief offline)
                    // surfaces here as a 401 even though the session is still
                    // valid. The retry runs a fresh refresh attempt.
                    await new Promise((r) => setTimeout(r, 1200));
                    userData = await api.getMe({ timeout: 45_000 });
                }
                // Cross-user guard: the query cache was hydrated at boot before
                // we knew who's logged in. If the persisted blob belongs to a
                // DIFFERENT user (a prior session that ended without teardown),
                // drop it now — before this user's screens mount — so we never
                // flash the previous user's data.
                try {
                    const cachedUid = await getPersistedCacheUserId();
                    if (cachedUid && userData?.id && cachedUid !== userData.id) {
                        await clearPersistedQueryCache().catch(() => undefined);
                        queryClient.clear();
                    }
                } catch {
                    /* ignore — worst case is a brief stale flash, refetch fixes it */
                }
                setUser(userData);
            }
        } catch (e: any) {
            // Only DESTROY the durable tokens on a DEFINITIVE auth failure
            // (deleted user / rotated key → 401, or 403). A transient failure —
            // a cold-Render timeout, a 5xx, or being briefly offline at boot —
            // must NOT clear tokens: the access token is valid 24h and the
            // refresh token 300 days, and they live in secure storage, so a
            // quit/reopen should resume the session. Clearing here permanently
            // stranded users on Landing — and an anon "Get started" account has
            // no email/password to log back in with, so it was unrecoverable.
            // (A real 401 is already handled by the response interceptor, which
            // attempts a refresh and, on refresh failure, clears + emits authLost.)
            const status = e?.response?.status;
            if (status === 403) {
                await api.clearTokens();
            }
            // 401 is deliberately NOT cleared here: the refresh interceptor is
            // the authority — when the refresh token is definitively rejected it
            // clears storage + emits authLost itself. A 401 that reaches us with
            // tokens still on disk means the refresh failed TRANSIENTLY (cold
            // backend, offline blip) and the session must survive for the next
            // attempt. Clearing on 401 here was how mid-funnel users got dumped
            // to Landing — and an anon "Get started" account is unrecoverable.
            // else: keep the durable tokens; the next boot (or the foreground
            // resume below, or a refetch once the backend is reachable) resumes
            // the session.
        } finally {
            setIsLoading(false);
        }
    }, [queryClient]);

    useEffect(() => {
        void checkAuth();
    }, [checkAuth]);

    // Boot can end logged-out while a durable session token still exists — a
    // transiently-failed restore (cold backend wake, brief offline). The user
    // is sitting on Landing with a perfectly valid session on disk. Retry the
    // restore once shortly after boot and whenever the app foregrounds, so
    // they get their session (and their mid-funnel progress) back.
    useEffect(() => {
        if (isLoading || user) return;
        let cancelled = false;
        const tryResume = async () => {
            try {
                const token = await getItemAsync('access_token');
                if (!cancelled && token) void checkAuth();
            } catch {
                /* secure-store hiccup — next trigger retries */
            }
        };
        const timer = setTimeout(() => void tryResume(), 8_000);
        const sub = AppState.addEventListener('change', (s: AppStateStatus) => {
            if (s === 'active') void tryResume();
        });
        return () => {
            cancelled = true;
            clearTimeout(timer);
            sub.remove();
        };
    }, [isLoading, user, checkAuth]);

    // Stamp the persisted query cache with the current user so a different
    // user's cold start can detect + drop a stale blob. Covers every path that
    // sets `user` (login, signup, faux, refresh, logout→null).
    useEffect(() => {
        setPersistUserId(user?.id ?? null);
    }, [user?.id]);

    // When the api layer detects a permanently-invalid session (refresh 401'd,
    // account deleted, key rotated), tear down auth state so React Query hooks
    // on the authenticated stack unmount. Without this the app loops — every
    // mounted useQuery retries, each retry hits 401, each 401 tries refresh.
    useEffect(() => {
        const unsubscribe = subscribeAuthLost(() => {
            setUser(null);
            try {
                queryClient.clear();
            } catch {
                /* ignore */
            }
            clearTodayWidget();
            void clearPendingFaceScanSubmit().catch(() => undefined);
            void clearFaceScanDraft().catch(() => undefined);
            void clearOnboardingDraft().catch(() => undefined);
            void clearRestoredTab().catch(() => undefined);
            void clearPersistedQueryCache().catch(() => undefined);
        });
        return unsubscribe;
    }, [queryClient]);

    // Auto-refresh iOS APNs push token on launch for users who've opted into push.
    // Tokens can rotate (reinstall, restore, iOS refresh), so re-registering keeps
    // the server's token fresh — otherwise push reminders silently stop arriving.
    useEffect(() => {
        if (Platform.OS !== 'ios') return;
        if (!user?.id) return;
        const appOptIn = user.onboarding?.app_notifications_opt_in;
        // Default-true: if unset, treat as opted-in (matches NotificationChannelsScreen).
        if (appOptIn === false) return;
        void (async () => {
            try {
                const token = await getIosApnsDeviceTokenForBackend();
                if (token) {
                    await api.registerPushToken(token);
                }
            } catch {
                /* non-fatal — user can re-save prefs in Profile */
            }
        })();
    }, [user?.id]);

    const login = useCallback(async (identifier: string, password: string) => {
        await api.login(identifier, password);
        const userData = await api.getMe();
        setUser(userData);
    }, []);

    const signup = useCallback(
        async (email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) => {
            await api.signup(email, password, first_name, last_name, username, phone_number);
            const userData = await api.getMe();
            setUser(userData);
        },
        [],
    );

    const fauxSignup = useCallback(async () => {
        await api.fauxSignup();
        const userData = await api.getMe();
        setUser(userData);
    }, []);

    const fauxSkipSignup = useCallback(async () => {
        await api.fauxSkipSignup();
        const userData = await api.getMe();
        setUser(userData);
    }, []);

    const fauxFreshSignup = useCallback(async () => {
        await api.fauxFreshSignup();
        const userData = await api.getMe();
        setUser(userData);
    }, []);

    const devToggleAdmin = useCallback(async () => {
        const { is_admin } = await api.devToggleAdmin();
        const userData = await api.getMe();
        setUser(userData);
        return is_admin;
    }, []);

    // Account-after-scan: mint a credential-less FREE account at "Get started" so
    // the funnel runs before sign-up; the user claims it before the paywall.
    const startAnon = useCallback(async () => {
        // A durable token here means a previous session was interrupted (the
        // boot restore failed transiently and dropped the user on Landing).
        // Resume THAT account instead of minting a fresh one — minting would
        // permanently orphan its onboarding answers / scan. Logout and a
        // definitive auth failure both clear tokens, so this never resurrects
        // a session the user chose to leave.
        try {
            const existing = await getItemAsync('access_token');
            if (existing) {
                const userData = await api.getMe({ timeout: 20_000 });
                setUser(userData);
                return;
            }
        } catch {
            /* unreadable/dead session — fall through to a fresh start */
        }
        await api.anonSignup();
        // The account + tokens are set now; don't let a transient getMe blip fail
        // "Get started" — retry once with a generous timeout before surfacing it.
        let userData: User;
        try {
            userData = await api.getMe({ timeout: 45_000 });
        } catch {
            await new Promise((r) => setTimeout(r, 1000));
            userData = await api.getMe({ timeout: 45_000 });
        }
        setUser(userData);
    }, []);

    const claimAccount = useCallback(
        async (email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) => {
            await api.claimAccount(email, password, first_name, last_name, username, phone_number);
            // The claim itself SUCCEEDED — don't let a transient getMe blip make the
            // screen report failure (a retry would then hit "already set up" and
            // strand the user). Retry once with a generous timeout, like startAnon.
            let userData: User;
            try {
                userData = await api.getMe({ timeout: 45_000 });
            } catch {
                await new Promise((r) => setTimeout(r, 1000));
                userData = await api.getMe({ timeout: 45_000 });
            }
            setUser(userData);
        },
        [],
    );

    const signInWithGoogle = useCallback(async (idToken: string) => {
        await api.googleSignIn(idToken);
        const userData = await api.getMe();
        setUser(userData);
        return userData;
    }, []);

    const signInWithGoogleDev = useCallback(async (email: string, name?: string) => {
        await api.googleSignInDev(email, name);
        const userData = await api.getMe();
        setUser(userData);
        return userData;
    }, []);

    const signInWithApple = useCallback(async (
        identityToken: string,
        opts?: { givenName?: string; familyName?: string; email?: string },
    ) => {
        await api.appleSignIn(identityToken, opts);
        const userData = await api.getMe();
        setUser(userData);
        return userData;
    }, []);

    const logout = useCallback(async () => {
        await api.clearTokens();
        setUser(null);
        setFreeTierChosen(false);
        // Reset the native Google SDK session so a later "Sign in with Google"
        // re-prompts cleanly instead of reusing a stale session (null idToken).
        await resetGoogleNativeSession();
        // Drop cached server state on logout so user B can't see user A's data.
        queryClient.clear();
        // Blank the Home Screen widget so a signed-out device (or user B) never
        // sees user A's tasks/streak.
        clearTodayWidget();
        await clearFreeTierChoice().catch(() => undefined);
        await clearPendingFaceScanSubmit().catch(() => undefined);
        await clearFaceScanDraft().catch(() => undefined);
        await clearOnboardingDraft().catch(() => undefined);
        await clearRestoredTab().catch(() => undefined);
        await clearPersistedQueryCache().catch(() => undefined);
    }, [queryClient]);

    const refreshUser = useCallback(async (): Promise<User> => {
        const userData = await api.getMe();
        setUser(userData);
        return userData;
    }, []);

    const deleteAccount = useCallback(async (password?: string) => {
        await api.deleteAccount(password);
        await api.clearTokens();
        setUser(null);
        setFreeTierChosen(false);
        clearTodayWidget();
        await resetGoogleNativeSession();
        await clearFreeTierChoice().catch(() => undefined);
        await clearPendingFaceScanSubmit().catch(() => undefined);
        await clearFaceScanDraft().catch(() => undefined);
        await clearOnboardingDraft().catch(() => undefined);
        await clearRestoredTab().catch(() => undefined);
        await clearPersistedQueryCache().catch(() => undefined);
    }, []);

    const chooseFreeTier = useCallback(async () => {
        // Flip state first so the navigator remounts onto Main immediately; the
        // persist is best-effort (worst case: re-tap on next cold start).
        setFreeTierChosen(true);
        if (user?.id) await saveFreeTierChoice(user.id);
    }, [user?.id]);

    const subscriptionTier: SubscriptionTier = (user?.subscription_tier as SubscriptionTier) ?? null;

    const value = useMemo<AuthContextType>(
        () => ({
            user,
            isLoading,
            isAuthenticated: !!user,
            isPaid: user?.is_paid ?? false,
            isPremium: user?.is_admin || (user?.is_paid && subscriptionTier === 'premium') || false,
            // Scan-only is a LIMITED tier; a full paid subscription supersedes it
            // (same principle as isFreeTier below). Without this, a scan-tier user
            // who later subscribes stays locked in the ScanOnly navigator with no
            // main app — RootNavigator checks isScanUser before Main/Admin/paid.
            isScanUser: (user?.is_scan_user ?? false) && !(user?.is_paid ?? false),
            isCreator: user?.is_creator ?? false,
            isAnonymous: !!user?.email && String(user.email).endsWith('@anon.trymax.app'),
            // Never "free tier" once actually paid — paying supersedes the choice.
            isFreeTier: freeTierChosen && !(user?.is_paid ?? false),
            chooseFreeTier,
            subscriptionTier,
            login,
            signup,
            fauxSignup,
            fauxSkipSignup,
            fauxFreshSignup,
            devToggleAdmin,
            startAnon,
            claimAccount,
            signInWithGoogle,
            signInWithGoogleDev,
            signInWithApple,
            logout,
            refreshUser,
            deleteAccount,
        }),
        [user, isLoading, freeTierChosen, chooseFreeTier, subscriptionTier, login, signup, fauxSignup, fauxSkipSignup, fauxFreshSignup, devToggleAdmin, startAnon, claimAccount, signInWithGoogle, signInWithGoogleDev, signInWithApple, logout, refreshUser, deleteAccount],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
}
