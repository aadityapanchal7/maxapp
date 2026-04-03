import { useState, useCallback } from 'react';
import { Alert } from 'react-native';

type Tier = 'basic' | 'premium';

/** Web: Payment Sheet is iOS/Android only. */
export function useStripeSubscription() {
    const [loading] = useState<Tier | null>(null);
    const [error] = useState<string | null>(null);

    const subscribeTier = useCallback(async (_tier: Tier): Promise<boolean> => {
        Alert.alert('Not available', 'In-app subscription is only available on iOS and Android.');
        return false;
    }, []);

    const subscribeBasic = useCallback(() => subscribeTier('basic'), [subscribeTier]);
    const subscribePremium = useCallback(() => subscribeTier('premium'), [subscribeTier]);

    return { loading, error, subscribeBasic, subscribePremium, subscribeTier };
}
