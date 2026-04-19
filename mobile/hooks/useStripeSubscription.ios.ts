type Tier = 'basic' | 'premium';

// iOS subscriptions are handled exclusively via Apple IAP. Export a shape
// compatible with the Android/web Stripe hook without importing Stripe at all.
export function useStripeSubscription() {
    const subscribeTier = async (_tier: Tier): Promise<boolean> => false;

    return {
        loading: null as Tier | null,
        error: null as string | null,
        subscribeBasic: () => subscribeTier('basic'),
        subscribePremium: () => subscribeTier('premium'),
        subscribeTier,
    };
}
