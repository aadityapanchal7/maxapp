/**
 * Auth Context - Global authentication state
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { Platform } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { getItemAsync } from '../services/storage';
import api from '../services/api';
import { clearFaceScanDraft, clearPendingFaceScanSubmit } from '../lib/faceScanDraft';
import { getIosApnsDeviceTokenForBackend } from '../services/registerIosPushToken';

type SubscriptionTier = 'basic' | 'premium' | null;

interface User {
    id: string;
    email: string;
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
        /** False after payment until user completes in-app Sendblue SMS step */
        sendblue_connect_completed?: boolean;
        /** True after user texts the Sendblue line; enables automated SMS from the server */
        sendblue_sms_engaged?: boolean;
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
    /** Server has an APNs token on file (iOS push). */
    has_apns_token?: boolean;
}

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    isPaid: boolean;
    isPremium: boolean;
    subscriptionTier: SubscriptionTier;
    login: (identifier: string, password: string) => Promise<void>;
    signup: (email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) => Promise<void>;
    logout: () => Promise<void>;
    /** Returns latest user from API (e.g. after payment) so callers can branch before next render. */
    refreshUser: () => Promise<User>;
    /** Permanently delete the signed-in account (App Store account-deletion requirement). */
    deleteAccount: (password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const queryClient = useQueryClient();

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
            const token = await getItemAsync('access_token');
            if (token) {
                const userData = await api.getMe();
                setUser(userData);
            }
        } catch {
            await api.clearTokens();
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        void checkAuth();
    }, [checkAuth]);

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

    const logout = useCallback(async () => {
        await api.clearTokens();
        setUser(null);
        // Drop cached server state on logout so user B can't see user A's data.
        queryClient.clear();
        await clearPendingFaceScanSubmit().catch(() => undefined);
        await clearFaceScanDraft().catch(() => undefined);
    }, [queryClient]);

    const refreshUser = useCallback(async (): Promise<User> => {
        const userData = await api.getMe();
        setUser(userData);
        return userData;
    }, []);

    const deleteAccount = useCallback(async (password: string) => {
        await api.deleteAccount(password);
        await api.clearTokens();
        setUser(null);
        await clearPendingFaceScanSubmit().catch(() => undefined);
        await clearFaceScanDraft().catch(() => undefined);
    }, []);

    const subscriptionTier: SubscriptionTier = (user?.subscription_tier as SubscriptionTier) ?? null;

    const value = useMemo<AuthContextType>(
        () => ({
            user,
            isLoading,
            isAuthenticated: !!user,
            isPaid: user?.is_paid ?? false,
            isPremium: user?.is_admin || (user?.is_paid && subscriptionTier === 'premium') || false,
            subscriptionTier,
            login,
            signup,
            logout,
            refreshUser,
            deleteAccount,
        }),
        [user, isLoading, subscriptionTier, login, signup, logout, refreshUser, deleteAccount],
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
