import React from 'react';
import { Platform } from 'react-native';
import { StripeProvider } from '@stripe/stripe-react-native';

const STRIPE_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY?.trim() || '';

/**
 * Must match app.json @stripe/stripe-react-native plugin and Apple Developer Merchant ID.
 * Stripe Dashboard → Apple Pay must register the same merchant. Expo plugin writes in-app-payments entitlement.
 */
const MERCHANT_IDENTIFIER = 'merchant.com.cannon.mobile';

export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    return (
        <StripeProvider
            publishableKey={STRIPE_PUBLISHABLE_KEY}
            {...(Platform.OS === 'ios'
                ? { merchantIdentifier: MERCHANT_IDENTIFIER, urlScheme: 'cannon' }
                : {})}
        >
            {/* StripeProvider typings require ReactElement, not full ReactNode */}
            <React.Fragment>{children}</React.Fragment>
        </StripeProvider>
    );
}
