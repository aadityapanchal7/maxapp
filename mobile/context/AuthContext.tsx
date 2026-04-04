/**
 * Auth Context - Global authentication state
 */

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { getItemAsync } from '../services/storage';
import api from '../services/api';
import { clearFaceScanDraft, clearPendingFaceScanSubmit } from '../lib/faceScanDraft';

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

    const checkAuth = useCallback(async () => {
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
        await clearPendingFaceScanSubmit().catch(() => undefined);
        await clearFaceScanDraft().catch(() => undefined);
    }, []);

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
