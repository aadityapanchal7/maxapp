/**
 * Auth Context - Global authentication state
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { getItemAsync } from '../services/storage';
import api from '../services/api';

interface User {
    id: string;
    email: string;
    first_name?: string;
    last_name?: string;
    username?: string;
    /** ISO timestamp — used for 2-week username change cooldown */
    last_username_change?: string | null;
    is_paid: boolean;
    onboarding: {
        completed: boolean;
        goals: string[];
        experience_level: string;
        age?: number;
        gender?: string;
        height?: number;
        weight?: number;
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
    };
    first_scan_completed: boolean;
    is_admin: boolean;
}

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    isPaid: boolean;
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

    useEffect(() => {
        checkAuth();
    }, []);

    const checkAuth = async () => {
        try {
            const token = await getItemAsync('access_token');
            if (token) {
                const userData = await api.getMe();
                setUser(userData);
            }
        } catch (error) {
            await api.clearTokens();
        } finally {
            setIsLoading(false);
        }
    };

    const login = async (identifier: string, password: string) => {
        await api.login(identifier, password);
        const userData = await api.getMe();
        setUser(userData);
    };

    const signup = async (email: string, password: string, first_name: string, last_name: string, username: string, phone_number?: string) => {
        await api.signup(email, password, first_name, last_name, username, phone_number);
        const userData = await api.getMe();
        setUser(userData);
    };

    const logout = async () => {
        await api.clearTokens();
        setUser(null);
    };

    const refreshUser = async (): Promise<User> => {
        const userData = await api.getMe();
        setUser(userData);
        return userData;
    };

    const deleteAccount = async (password: string) => {
        await api.deleteAccount(password);
        await api.clearTokens();
        setUser(null);
    };

    return (
        <AuthContext.Provider
            value={{
                user,
                isLoading,
                isAuthenticated: !!user,
                isPaid: user?.is_paid ?? false,
                login,
                signup,
                logout,
                refreshUser,
                deleteAccount,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
}
