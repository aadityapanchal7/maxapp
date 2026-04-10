import React from 'react';
import { StripeProvider } from '@stripe/stripe-react-native';

const STRIPE_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY?.trim() || '';

export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    return (
        <StripeProvider
            publishableKey={STRIPE_PUBLISHABLE_KEY}
            merchantIdentifier="merchant.com.cannon.mobile"
            urlScheme="cannon"
        >
            <React.Fragment>{children}</React.Fragment>
        </StripeProvider>
    );
}
