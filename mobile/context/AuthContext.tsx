/**
 * Auth Context - Global authentication state
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as SecureStore from 'expo-secure-store';
import api from '../services/api';

interface User {
    id: string;
    email: string;
    is_paid: boolean;
    onboarding: {
        completed: boolean;
        goals: string[];
        experience_level: string;
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
    login: (email: string, password: string) => Promise<void>;
    signup: (email: string, password: string, bio?: string) => Promise<void>;
    logout: () => Promise<void>;
    refreshUser: () => Promise<void>;
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
            const token = await SecureStore.getItemAsync('access_token');
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

    const login = async (email: string, password: string) => {
        await api.login(email, password);
        const userData = await api.getMe();
        setUser(userData);
    };

    const signup = async (email: string, password: string, bio?: string) => {
        await api.signup(email, password, bio);
        const userData = await api.getMe();
        setUser(userData);
    };

    const logout = async () => {
        await api.clearTokens();
        setUser(null);
    };

    const refreshUser = async () => {
        const userData = await api.getMe();
        setUser(userData);
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
