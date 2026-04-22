import { useCallback, useState } from 'react';
import { Alert, Platform } from 'react-native';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

type Tier = 'basic' | 'premium';

const SIMULATED_SKUS: Record<Tier, string> = {
    basic: 'com.cannon.mobile.subscribe.basic.weekly',
    premium: 'com.cannon.mobile.subscribe.premium.weekly',
};

/**
 * Non-iOS stub. On web/Android in __DEV__, simulates the Apple IAP verify
 * flow against the real backend so you can test from localhost via console logs.
 */
export function useAppleSubscription() {
    const { user, refreshUser } = useAuth();
    const [loading, setLoading] = useState<Tier | null>(null);

    const subscribeTier = useCallback(
        async (tier: Tier): Promise<boolean> => {
            if (!__DEV__) return false;
            if (!user?.id) {
                Alert.alert('Sign in', 'Log in to subscribe.');
                return false;
            }

            setLoading(tier);
            const sku = SIMULATED_SKUS[tier];
            const fakeTid = `sim_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

            console.log('──────────────────────────────────────────');
            console.log('[AppleIAP-Sim] Simulating Apple IAP purchase');
            console.log('[AppleIAP-Sim] Tier:', tier);
            console.log('[AppleIAP-Sim] SKU:', sku);
            console.log('[AppleIAP-Sim] Simulated transaction ID:', fakeTid);
            console.log('[AppleIAP-Sim] User ID:', user.id);
            console.log('[AppleIAP-Sim] Calling POST /payments/apple/verify ...');

            try {
                const result = await api.verifyAppleIapTransaction(fakeTid, sku);
                console.log('[AppleIAP-Sim] ✅ Backend responded:', JSON.stringify(result));
                console.log('[AppleIAP-Sim] Refreshing user profile ...');

                await refreshUser();
                console.log('[AppleIAP-Sim] ✅ User refreshed — is_paid should now be true');
                console.log('[AppleIAP-Sim] ✅ RootNavigator will swap to paid stack');
                console.log('──────────────────────────────────────────');

                if (Platform.OS === 'web') {
                    window.alert(`Subscribed! Tier: ${result.tier || tier}`);
                } else {
                    Alert.alert('Subscribed!', `Your ${tier} plan is now active.`);
                }
                return true;
            } catch (e: unknown) {
                const detail = (e as any)?.response?.data?.detail;
                const status = (e as any)?.response?.status;
                const msg = typeof detail === 'string' ? detail : (e as Error)?.message || 'Verification failed';

                console.error('[AppleIAP-Sim] ❌ Verify failed');
                console.error('[AppleIAP-Sim] HTTP status:', status);
                console.error('[AppleIAP-Sim] Detail:', msg);
                console.error('[AppleIAP-Sim] Full error:', JSON.stringify((e as any)?.response?.data));
                console.log('──────────────────────────────────────────');

                if (Platform.OS === 'web') {
                    window.alert(`Apple IAP verify error: ${msg}`);
                } else {
                    Alert.alert('Purchase error', msg);
                }
                return false;
            } finally {
                setLoading(null);
            }
        },
        [user?.id, refreshUser],
    );

    const restorePurchases = useCallback(async (): Promise<boolean> => {
        if (Platform.OS === 'web') {
            window.alert('Restore purchases is only available on iOS.');
        } else {
            Alert.alert('Not available', 'Restore purchases is only available on iOS.');
        }
        return false;
    }, []);

    return {
        loading,
        restoring: false,
        subscribeBasic: useCallback(() => subscribeTier('basic'), [subscribeTier]),
        subscribePremium: useCallback(() => subscribeTier('premium'), [subscribeTier]),
        subscribeTier,
        restorePurchases,
        storeConnected: __DEV__,
    };
}
