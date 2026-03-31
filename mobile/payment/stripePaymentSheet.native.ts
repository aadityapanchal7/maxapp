import { initPaymentSheet, presentPaymentSheet } from '@stripe/stripe-react-native';
import * as Linking from 'expo-linking';
import api from '../services/api';

export type SubscriptionTier = 'chadlite' | 'chad';

export type PresentSubscriptionResult =
    | { kind: 'paid' }
    | { kind: 'canceled' }
    | { kind: 'error'; message: string };

export async function presentSubscriptionPaymentSheet(params: {
    tier: SubscriptionTier;
    finishAfterPayment: () => Promise<void>;
}): Promise<PresentSubscriptionResult> {
    try {
        const sheet = await api.createPaymentSheet(params.tier);
        const returnURL = Linking.createURL('stripe-redirect');
        const { error: initError } = await initPaymentSheet({
            merchantDisplayName: 'Max',
            customerId: sheet.customer_id,
            customerEphemeralKeySecret: sheet.ephemeral_key_secret,
            paymentIntentClientSecret: sheet.payment_intent_client_secret,
            allowsDelayedPaymentMethods: true,
            returnURL,
        });
        if (initError) {
            return { kind: 'error', message: initError.message };
        }
        const { error: presentError } = await presentPaymentSheet();
        if (presentError) {
            if (presentError.code === 'Canceled') {
                return { kind: 'canceled' };
            }
            return { kind: 'error', message: presentError.message };
        }
        await params.finishAfterPayment();
        return { kind: 'paid' };
    } catch (e: unknown) {
        const ax = e as { response?: { data?: { detail?: string } }; message?: string };
        const msg = ax?.response?.data?.detail || ax?.message || 'Could not start checkout';
        return { kind: 'error', message: String(msg) };
    }
}
