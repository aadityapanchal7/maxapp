import React from 'react';
import { View } from 'react-native';

export type StripeEmbeddedCheckoutProps = {
    publishableKey: string;
    clientSecret: string;
    onClose: () => void;
};

/** Native uses in-app / deep-link flows; embedded checkout is web-only. */
export default function StripeEmbeddedCheckout(_props: StripeEmbeddedCheckoutProps) {
    return <View />;
}
