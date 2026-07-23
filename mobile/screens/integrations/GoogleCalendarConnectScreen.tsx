/**
 * Google Calendar connect screen — opens the system browser for OAuth
 * (backend-mediated, zero token on client), then polls /google/status until
 * connected. Also shows connected + disconnect states.
 *
 * Hidden when calendar_link_enabled is false (flag default OFF).
 */
import React, { useEffect, useRef, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ActivityIndicator,
    ScrollView,
    Linking,
} from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import { Alert } from '../../components/InAppAlert';
import { useNavigation } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { openGoogleCalendarAuth } from '../../lib/googleConnect';
import { colors, spacing, fonts } from '../../theme/dark';

const STATUS_QK = ['googleStatus'];

export default function GoogleCalendarConnectScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const qc = useQueryClient();
    const [connecting, setConnecting] = useState(false);
    const [disconnecting, setDisconnecting] = useState(false);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const statusQ = useQuery({
        queryKey: STATUS_QK,
        queryFn: () => api.getGoogleStatus(),
        staleTime: 10_000,
    });

    const status = statusQ.data;
    const connected = !!status?.connected;

    // Stop polling once connected
    useEffect(() => {
        if (connected && pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setConnecting(false);
            try { WebBrowser.dismissAuthSession(); } catch { /* auto-closes on redirect */ }
            qc.invalidateQueries({ queryKey: ['plannerToday'] });
        }
    }, [connected, qc]);

    // Clean up on unmount
    useEffect(() => () => {
        if (pollRef.current) clearInterval(pollRef.current);
    }, []);

    const handleConnect = async () => {
        if (!status?.oauth_available) {
            Alert.alert('Not configured', 'Google OAuth is not set up yet.');
            return;
        }
        try {
            setConnecting(true);
            // Belt-and-suspenders poll while the auth sheet is open.
            pollRef.current = setInterval(() => {
                qc.invalidateQueries({ queryKey: STATUS_QK });
            }, 3000);
            // Native auth sheet (ASWebAuthenticationSession) — auto-closes when the
            // backend callback redirects back to cannon://google-connected.
            await openGoogleCalendarAuth();
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            qc.invalidateQueries({ queryKey: STATUS_QK });
            qc.invalidateQueries({ queryKey: ['plannerToday'] });
        } catch (e: any) {
            const s = e?.response?.status;
            const detail = s ? `HTTP ${s}` : e?.message ? String(e.message) : 'no response (network)';
            Alert.alert('Could not connect Google Calendar', `Please try again.\n\n(${detail})`);
        } finally {
            // Always stop the status poll — on the error path the interval would
            // otherwise keep refetching every 3s until the screen unmounts.
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            setConnecting(false);
        }
    };

    const handleDisconnect = async () => {
        try {
            setDisconnecting(true);
            await api.disconnectGoogle();
            qc.invalidateQueries({ queryKey: STATUS_QK });
            qc.invalidateQueries({ queryKey: ['plannerToday'] });
        } catch {
            Alert.alert('Error', 'Could not disconnect. Please try again.');
        } finally {
            setDisconnecting(false);
        }
    };

    if (statusQ.isLoading) {
        // The status fetch retries with backoff on a bad connection — keep the
        // back chevron visible so this spinner is never a screen with no exit.
        return (
            <View style={{ flex: 1, paddingTop: insets.top + 16, paddingHorizontal: spacing.md ?? 16 }}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                    <Ionicons name="chevron-back" size={22} color={colors.foreground} />
                </TouchableOpacity>
                <View style={styles.center}>
                    <ActivityIndicator color={colors.textMuted} />
                </View>
            </View>
        );
    }

    return (
        <ScrollView
            contentContainerStyle={[styles.container, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 40 }]}
        >
            <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
                <Ionicons name="chevron-back" size={22} color={colors.foreground} />
            </TouchableOpacity>

            <View style={styles.header}>
                <Ionicons name="calendar" size={40} color={colors.foreground} style={{ marginBottom: 12 }} />
                <Text style={styles.title}>Google Calendar</Text>
                <Text style={styles.subtitle}>
                    See your real calendar events alongside your Max tasks — read-only, always up to date.
                </Text>
            </View>

            {connected ? (
                <View style={styles.card}>
                    <View style={styles.connectedRow}>
                        <Ionicons name="checkmark-circle" size={20} color="#4CAF50" />
                        <Text style={styles.connectedText}>Connected</Text>
                    </View>
                    {status?.last_synced_at ? (
                        <Text style={styles.hint}>
                            Last synced {new Date(status.last_synced_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </Text>
                    ) : null}
                    <TouchableOpacity
                        style={[styles.btn, styles.btnSecondary, { marginTop: 20 }]}
                        onPress={handleDisconnect}
                        disabled={disconnecting}
                    >
                        {disconnecting ? (
                            <ActivityIndicator color={colors.foreground} size="small" />
                        ) : (
                            <Text style={[styles.btnText, { color: colors.foreground }]}>Disconnect</Text>
                        )}
                    </TouchableOpacity>
                </View>
            ) : (
                <View style={styles.card}>
                    <Text style={styles.hint}>
                        Max will read your primary calendar (next 60 days) to show events on your planner. Syncs every 30 minutes. Calendar data stays on Max servers — not shared.
                    </Text>
                    <TouchableOpacity
                        style={[styles.btn, connecting && styles.btnDisabled]}
                        onPress={handleConnect}
                        disabled={connecting}
                    >
                        {connecting ? (
                            <ActivityIndicator color="#fff" size="small" />
                        ) : (
                            <>
                                <Ionicons name="logo-google" size={16} color="#fff" style={{ marginRight: 8 }} />
                                <Text style={styles.btnText}>Connect Google Calendar</Text>
                            </>
                        )}
                    </TouchableOpacity>
                    {connecting ? (
                        <Text style={[styles.hint, { marginTop: 12, textAlign: 'center' }]}>
                            Complete sign-in in your browser, then return here.
                        </Text>
                    ) : null}
                    <TouchableOpacity onPress={() => navigation.goBack()} style={{ marginTop: 16, alignItems: 'center' }}>
                        <Text style={[styles.hint, { textDecorationLine: 'underline' }]}>Skip for now</Text>
                    </TouchableOpacity>
                </View>
            )}
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    container: { paddingHorizontal: spacing.md ?? 16 },
    backBtn: { marginBottom: 8, padding: 4 },
    header: { alignItems: 'center', marginVertical: 24 },
    title: { fontSize: 24, fontFamily: fonts.serifSemiBold, color: colors.foreground, marginBottom: 8 },
    subtitle: { fontSize: 15, color: colors.textMuted, textAlign: 'center', lineHeight: 22 },
    card: { backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 16, padding: 20, marginTop: 8 },
    connectedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
    connectedText: { fontSize: 16, fontFamily: fonts.sansMedium, color: colors.foreground },
    hint: { fontSize: 13, color: colors.textMuted, lineHeight: 20 },
    btn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#1a73e8',
        borderRadius: 12,
        paddingVertical: 14,
        paddingHorizontal: 20,
        marginTop: 16,
    },
    btnSecondary: { backgroundColor: 'transparent', borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)' },
    btnDisabled: { opacity: 0.5 },
    btnText: { fontSize: 15, fontFamily: fonts.sansMedium, color: '#fff' },
});
