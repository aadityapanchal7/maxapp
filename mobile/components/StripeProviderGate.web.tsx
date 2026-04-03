import React from 'react';

/** Web: Stripe React Native is native-only; skip provider so Metro can bundle for web. */
export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
