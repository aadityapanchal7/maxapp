import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Platform } from 'react-native';
import type { StripeEmbeddedCheckoutProps } from './StripeEmbeddedCheckout.native';

declare global {
    interface Window {
        Stripe?: (pk: string) => {
            initEmbeddedCheckout: (opts: { clientSecret: string }) => Promise<{ mount: (sel: string) => void }>;
        };
    }
}

export default function StripeEmbeddedCheckout({
    publishableKey,
    clientSecret,
    onClose,
}: StripeEmbeddedCheckoutProps) {
    const mounted = useRef(false);

    useEffect(() => {
        if (Platform.OS !== 'web' || typeof document === 'undefined') return;

        const mountId = 'stripe-embedded-root';
        const el = document.getElementById(mountId);
        if (!el || mounted.current) return;
        mounted.current = true;

        const loadStripe = () =>
            new Promise<void>((resolve, reject) => {
                if (window.Stripe) {
                    resolve();
                    return;
                }
                const existing = document.querySelector('script[src="https://js.stripe.com/v3/"]');
                if (existing) {
                    existing.addEventListener('load', () => resolve());
                    existing.addEventListener('error', () => reject(new Error('Stripe.js load failed')));
                    return;
                }
                const script = document.createElement('script');
                script.src = 'https://js.stripe.com/v3/';
                script.async = true;
                script.onload = () => resolve();
                script.onerror = () => reject(new Error('Stripe.js load failed'));
                document.body.appendChild(script);
            });

        let cancelled = false;
        (async () => {
            try {
                await loadStripe();
                if (cancelled || !window.Stripe) return;
                const stripe = window.Stripe(publishableKey);
                const checkout = await stripe.initEmbeddedCheckout({ clientSecret });
                checkout.mount(`#${mountId}`);
            } catch {
                if (!cancelled && el) {
                    el.innerHTML =
                        '<p style="color:#fafafa;padding:16px;font-family:system-ui;">Could not load checkout. Try again or use the mobile app.</p>';
                }
            }
        })();

        return () => {
            cancelled = true;
            if (el) el.innerHTML = '';
            mounted.current = false;
        };
    }, [publishableKey, clientSecret]);

    return (
        <View style={styles.wrap}>
            <View style={styles.toolbar}>
                <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                    <Text style={styles.closeText}>Cancel</Text>
                </TouchableOpacity>
            </View>
            {/* @ts-expect-error RN Web maps nativeID to DOM id */}
            <View nativeID="stripe-embedded-root" style={styles.mount} />
        </View>
    );
}

const styles = StyleSheet.create({
    wrap: { flex: 1, backgroundColor: '#0a0a0a' },
    toolbar: {
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: '#333',
    },
    closeBtn: { alignSelf: 'flex-start' },
    closeText: { color: '#fafafa', fontWeight: '600', fontSize: 16 },
    mount: { flex: 1, minHeight: 420, width: '100%' },
});
