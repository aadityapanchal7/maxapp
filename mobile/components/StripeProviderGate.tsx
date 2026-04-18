import React from 'react';
import { Platform } from 'react-native';
import { StripeProvider } from '@stripe/stripe-react-native';

const STRIPE_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY?.trim() || '';

// iOS uses Apple IAP exclusively — Stripe / Apple Pay is not used there.
// Mounting StripeProvider on iOS still pulls in PassKit; we bypass it entirely.
export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    if (Platform.OS === 'ios') {
        return <React.Fragment>{children}</React.Fragment>;
    }
    return (
        <StripeProvider
            publishableKey={STRIPE_PUBLISHABLE_KEY}
            urlScheme="cannon"
        >
            <React.Fragment>{children}</React.Fragment>
        </StripeProvider>
    );
}
