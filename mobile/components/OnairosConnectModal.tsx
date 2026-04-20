/**
 * OnairosConnectModal — popup that lets the user enable cross-platform data
 * connections via the Onairos SDK (@onairos/react-native) so Max can pull in
 * richer personalization signals from apps they already use.
 *
 * The Onairos SDK handles the in-app consent UI itself. We just trigger it
 * and pass the resolved {apiUrl, accessToken, approvedRequests, userData}
 * bundle to our backend via apiService.connectOnairos(...).
 *
 * Renders a graceful "unavailable" state when EXPO_PUBLIC_ONAIROS_API_KEY
 * is not set, so the feature can ship behind a build-time flag.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    ActivityIndicator,
    Modal,
    Pressable,
    StyleSheet,
    Text,
    View,
} from 'react-native';

import apiService from '../services/api';

type OnairosResolvedPayload = {
    success: boolean;
    apiUrl?: string;
    accessToken?: string;
    approvedRequests?: Record<string, boolean>;
    userData?: { basic?: { name?: string; email?: string } } | null;
};

type OnairosSdkModule = {
    OnairosButton: React.ComponentType<any>;
    initializeApiKey?: (args: { apiKey: string }) => Promise<void> | void;
};

/**
 * Dynamic require so the app still boots when the native module isn't
 * installed yet (e.g. web builds, or before `npm install` picks up the
 * new dep). Web falls back to a disabled notice instead of crashing.
 */
function loadOnairosSdk(): OnairosSdkModule | null {
    try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        return require('@onairos/react-native') as OnairosSdkModule;
    } catch {
        return null;
    }
}

const REQUEST_DATA = {
    personality_traits: {
        name: 'Personality & Traits',
        description: 'Lets Max tailor coaching tone + priorities to who you are.',
        reward: 'Personalized routine out of the gate.',
    },
    sentiment_analysis: {
        name: 'Sentiment',
        description: 'Helps Max read the room — less nag when you\u2019re burnt out.',
        reward: 'Smarter check-ins.',
    },
} as const;

export type OnairosConnectModalProps = {
    visible: boolean;
    onClose: () => void;
    onConnected?: (result: { initialTraits?: any }) => void;
};

export default function OnairosConnectModal({
    visible,
    onClose,
    onConnected,
}: OnairosConnectModalProps) {
    const sdk = useMemo(() => loadOnairosSdk(), []);
    const apiKey = (process.env.EXPO_PUBLIC_ONAIROS_API_KEY || '').trim();

    const [initializing, setInitializing] = useState<boolean>(false);
    const [initError, setInitError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState<boolean>(false);
    const [submitError, setSubmitError] = useState<string | null>(null);
    const [success, setSuccess] = useState<boolean>(false);

    // Initialize the SDK once when the modal opens (the SDK caches internally).
    useEffect(() => {
        if (!visible || !sdk || !apiKey || !sdk.initializeApiKey) {
            return;
        }
        let cancelled = false;
        setInitializing(true);
        setInitError(null);
        Promise.resolve(sdk.initializeApiKey({ apiKey }))
            .catch((e: unknown) => {
                if (!cancelled) {
                    setInitError(
                        e instanceof Error ? e.message : 'Could not reach Onairos.'
                    );
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setInitializing(false);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [visible, sdk, apiKey]);

    const handleResolved = useCallback(
        async (payload: OnairosResolvedPayload) => {
            if (!payload?.success || !payload.apiUrl || !payload.accessToken) {
                setSubmitError('Connection did not complete. Please try again.');
                return;
            }
            setSubmitError(null);
            setSubmitting(true);
            try {
                const resp = await apiService.connectOnairos({
                    apiUrl: payload.apiUrl,
                    accessToken: payload.accessToken,
                    approvedRequests: payload.approvedRequests || {},
                    userData: payload.userData ?? null,
                });
                setSuccess(true);
                onConnected?.({ initialTraits: resp?.initial_traits });
            } catch (e: unknown) {
                setSubmitError(
                    e instanceof Error
                        ? e.message
                        : 'Could not save your connection. Try again in a moment.'
                );
            } finally {
                setSubmitting(false);
            }
        },
        [onConnected]
    );

    const canRender = !!sdk && !!apiKey;
    const OnairosButton = sdk?.OnairosButton;

    return (
        <Modal
            transparent
            visible={visible}
            animationType="fade"
            onRequestClose={onClose}
        >
            <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="Dismiss">
                <Pressable style={styles.card} onPress={() => { /* stop propagation */ }}>
                    <Text style={styles.title}>Connect your other apps</Text>
                    <Text style={styles.subtitle}>
                        Pull in personality, preferences, and habits from apps you already use so
                        Max can tailor coaching without another 20 onboarding questions. You
                        approve each category; revoke any time.
                    </Text>

                    {!canRender && (
                        <View style={styles.notice}>
                            <Text style={styles.noticeText}>
                                Onairos is unavailable in this build. Set
                                EXPO_PUBLIC_ONAIROS_API_KEY and install
                                @onairos/react-native to enable it.
                            </Text>
                        </View>
                    )}

                    {canRender && initializing && (
                        <View style={styles.row}>
                            <ActivityIndicator />
                            <Text style={styles.helper}>Getting Onairos ready\u2026</Text>
                        </View>
                    )}

                    {canRender && initError && (
                        <Text style={styles.error}>{initError}</Text>
                    )}

                    {canRender && !initializing && !initError && OnairosButton && (
                        <View style={styles.buttonWrap}>
                            <OnairosButton
                                AppName="Max"
                                webpageName="maxapp"
                                requestData={REQUEST_DATA}
                                onResolved={handleResolved}
                                autoFetch={false}
                                textColor="white"
                                textLayout="right"
                            />
                        </View>
                    )}

                    {submitting && (
                        <View style={styles.row}>
                            <ActivityIndicator />
                            <Text style={styles.helper}>Saving your connection\u2026</Text>
                        </View>
                    )}

                    {submitError && <Text style={styles.error}>{submitError}</Text>}

                    {success && (
                        <Text style={styles.success}>
                            Connected. Max will start using this on your next chat.
                        </Text>
                    )}

                    <Pressable onPress={onClose} style={styles.closeBtn} accessibilityRole="button">
                        <Text style={styles.closeText}>{success ? 'Done' : 'Maybe later'}</Text>
                    </Pressable>
                </Pressable>
            </Pressable>
        </Modal>
    );
}

const styles = StyleSheet.create({
    backdrop: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.55)',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
    },
    card: {
        width: '100%',
        maxWidth: 420,
        backgroundColor: '#111',
        borderRadius: 16,
        padding: 20,
        gap: 14,
    },
    title: {
        color: 'white',
        fontSize: 20,
        fontWeight: '700',
    },
    subtitle: {
        color: '#C8C8C8',
        fontSize: 14,
        lineHeight: 20,
    },
    notice: {
        backgroundColor: '#1F1F1F',
        borderRadius: 10,
        padding: 12,
    },
    noticeText: {
        color: '#B0B0B0',
        fontSize: 13,
    },
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
    },
    helper: {
        color: '#C8C8C8',
        fontSize: 13,
    },
    error: {
        color: '#FF6B6B',
        fontSize: 13,
    },
    success: {
        color: '#4DDE84',
        fontSize: 14,
        fontWeight: '600',
    },
    buttonWrap: {
        paddingVertical: 6,
    },
    closeBtn: {
        alignSelf: 'flex-end',
        paddingVertical: 8,
        paddingHorizontal: 10,
    },
    closeText: {
        color: '#BDBDBD',
        fontSize: 14,
        fontWeight: '600',
    },
});
