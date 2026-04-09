type Tier = 'basic' | 'premium';

/** Android / web: subscriptions use Stripe (or are unavailable on web). */
export function useAppleSubscription() {
    return {
        loading: null as Tier | null,
        subscribeBasic: async () => {},
        subscribePremium: async () => {},
        subscribeTier: async () => false,
        storeConnected: false,
    };
}
