import React from 'react';

// iOS uses Apple IAP only. Do not import Stripe on iOS so the binary does not
// pull in unused Apple Pay / PassKit-related native code.
export function StripeProviderGate({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
