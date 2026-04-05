import React from 'react';
import { Platform } from 'react-native';
import { StripeProvider } from '@stripe/stripe-react-native';

const STRIPE_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY?.trim() || '';
/** Must be passed on iOS or `initStripe` fails — even for card-only Payment Sheet. Apple Pay in the Sheet only works if the app entitlement + provisioning profile include this merchant (see app.json Stripe plugin). */
const MERCHANT_IDENTIFIER = 'merchant.com.cannon.mobile';

export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    return (
        <StripeProvider
            publishableKey={STRIPE_PUBLISHABLE_KEY}
            {...(Platform.OS === 'ios' ? { merchantIdentifier: MERCHANT_IDENTIFIER } : {})}
        >
            {/* StripeProvider typings require ReactElement, not full ReactNode */}
            <React.Fragment>{children}</React.Fragment>
        </StripeProvider>
    );
}
