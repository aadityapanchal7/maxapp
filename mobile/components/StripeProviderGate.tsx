import React from 'react';
import { StripeProvider } from '@stripe/stripe-react-native';

const STRIPE_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY?.trim() || '';

/** Omit merchantIdentifier until App ID + provisioning profile include Apple Pay (merchant.com.cannon.mobile). */
export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    return <StripeProvider publishableKey={STRIPE_PUBLISHABLE_KEY}>{children}</StripeProvider>;
}
