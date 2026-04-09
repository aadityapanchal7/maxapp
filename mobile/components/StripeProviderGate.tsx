import React from 'react';
import { Platform } from 'react-native';
import { StripeProvider } from '@stripe/stripe-react-native';

const STRIPE_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY?.trim() || '';

export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    /** iPhone subscriptions use App Store IAP; Stripe Payment Sheet is Android + web only. */
    if (Platform.OS === 'ios') {
        return <>{children}</>;
    }

    return (
        <StripeProvider
            publishableKey={STRIPE_PUBLISHABLE_KEY}
            {...(Platform.OS === 'android' ? { urlScheme: 'cannon' } : {})}
        >
            {/* StripeProvider typings require ReactElement, not full ReactNode */}
            <React.Fragment>{children}</React.Fragment>
        </StripeProvider>
    );
}
