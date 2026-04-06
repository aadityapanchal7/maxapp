/**
 * After paid scan results: user must text the Sendblue line so their number is in the thread ($100/mo plan).
 * Next: NotificationChannelsScreen picks SMS vs iPhone push vs both.
 */

import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    Linking,
    Platform,
    ActivityIndicator,
    Alert,
    ScrollView,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Constants from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { SHOW_DEV_SKIP_CONTROLS } from '../../constants/devSkips';

type RouteParams = { next?: 'ModuleSelect' | 'Main' };

/** Readable display for the phone the user signed up with (E.164 or digits). */
function formatSignupPhoneDisplay(raw?: string | null): string {
    if (!raw?.trim()) return '';
    const d = raw.replace(/\D/g, '');
    if (d.length === 11 && d.startsWith('1')) {
        const n = d.slice(1);
        return `+1 (${n.slice(0, 3)}) ${n.slice(3, 6)}-${n.slice(6)}`;
    }
    if (d.length === 10) {
        return `+1 (${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
    }
    return raw.trim();
}

export default function SendblueConnectScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { refreshUser, user } = useAuth();
    const [busy, setBusy] = useState(false);

    const smsConfirmed = user?.onboarding?.sendblue_sms_engaged === true;

    // Poll every 4s while waiting for SMS — single source of refresh so we don't
    // double-fire with focus. Stops the moment smsConfirmed flips true.
    useEffect(() => {
        if (smsConfirmed) return;
        refreshUser().catch(() => {});
        const id = setInterval(() => {
            refreshUser().catch(() => {});
        }, 4000);
        return () => clearInterval(id);
    }, [smsConfirmed, refreshUser]);

    const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string | undefined>;
    const smsE164 = (extra.sendblueSmsNumber || '+16468304204').replace(/\s/g, '');
    const signupDisplay = formatSignupPhoneDisplay(user?.phone_number);
    const next: 'ModuleSelect' | 'Main' = route.params?.next === 'Main' ? 'Main' : 'ModuleSelect';

    const openSms = () => {
        const body = encodeURIComponent('Hey Max');
        const url = Platform.OS === 'ios' ? `sms:${smsE164}&body=${body}` : `sms:${smsE164}?body=${body}`;
        Linking.openURL(url).catch(() => {
            Alert.alert('Messages', 'Open Messages and text our Max line from the phone number on your account.');
        });
    };

    const onContinue = () => {
        navigation.navigate('NotificationChannels', { next, editMode: false });
    };

    const onSkipSms = () => {
        Alert.alert(
            'Skip SMS permanently?',
            'SMS coaching from Max (schedule reminders, check-ins, motivation texts) will never be available on this account.\n\nTo get SMS later, you would need to delete your account and create a new one.\n\nAre you sure you want to skip?',
            [
                { text: 'Go back', style: 'cancel' },
                {
                    text: 'Skip SMS forever',
                    style: 'destructive',
                    onPress: async () => {
                        setBusy(true);
                        try {
                            await api.completeSendblueConnect({ sms_opt_in: false, app_notifications_opt_in: true });
                            await refreshUser();
                            if (next === 'Main') {
                                navigation.navigate('Main');
                            } else {
                                navigation.navigate('ModuleSelect');
                            }
                        } catch (e) {
                            console.error(e);
                            Alert.alert('Error', 'Could not save. Check your connection and try again.');
                        } finally {
                            setBusy(false);
                        }
                    },
                },
            ],
        );
    };

    const onDevSkip = async () => {
        setBusy(true);
        try {
            await api.devSkipSendblueEngageOnly();
            await refreshUser();
            navigation.navigate('NotificationChannels', { next, editMode: false });
        } catch (e) {
            console.error(e);
            Alert.alert('Dev skip failed', 'Could not skip. Check backend is in debug mode.');
        } finally {
            setBusy(false);
        }
    };

    const scrollBottomPad = insets.bottom + spacing.xxl + 8;

    return (
        <View style={styles.root}>
            <ScrollView
                style={styles.scroll}
                contentContainerStyle={[
                    styles.scrollContent,
                    { paddingTop: Math.max(insets.top, 12) + 44, paddingBottom: scrollBottomPad },
                ]}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator
            >
                <TouchableOpacity style={styles.backHit} onPress={() => navigation.goBack()} hitSlop={12}>
                    <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                </TouchableOpacity>

                <Text style={styles.kicker}>One more step</Text>
                <Text style={styles.title}>Text Max to connect</Text>
                <Text style={styles.lead}>
                    Send any message to link your phone to your account.
                </Text>

                <View style={styles.card}>
                    <Text style={styles.cardLabel}>TEXT FROM THIS NUMBER</Text>
                    {signupDisplay ? (
                        <Text style={styles.phoneUser} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.65}>
                            {signupDisplay}
                        </Text>
                    ) : (
                        <Text style={styles.phoneMissing}>
                            We don&apos;t have a phone on your account. Add one in Profile, or use the number you signed up with in
                            Messages.
                        </Text>
                    )}
                    <Text style={styles.cardHint}>
                        Open Messages below and send from the phone number above so we can verify it&apos;s you.
                    </Text>
                    <TouchableOpacity style={styles.primaryBtn} onPress={openSms} activeOpacity={0.88}>
                        <Ionicons name="chatbubble-ellipses-outline" size={22} color={colors.background} />
                        <Text style={styles.primaryBtnText}>Open Messages</Text>
                    </TouchableOpacity>
                </View>

                {!smsConfirmed ? (
                    <View style={styles.waitingRow}>
                        <ActivityIndicator color={colors.foreground} size="small" />
                        <Text style={styles.waitingText}>
                            Waiting for your message…
                        </Text>
                    </View>
                ) : (
                    <Text style={styles.confirmedLine}>
                        You&apos;re linked — tap Continue.
                    </Text>
                )}

                <TouchableOpacity
                    style={[styles.secondaryBtn, (!smsConfirmed || busy) && styles.secondaryBtnDisabled]}
                    onPress={onContinue}
                    disabled={!smsConfirmed || busy}
                    activeOpacity={0.85}
                >
                    {busy ? (
                        <ActivityIndicator color={colors.foreground} />
                    ) : (
                        <Text style={styles.secondaryBtnText}>Continue</Text>
                    )}
                </TouchableOpacity>

                <View style={styles.skipSmsWrap}>
                    <Ionicons name="warning-outline" size={15} color={colors.error} style={{ marginTop: 1 }} />
                    <Text style={styles.skipSmsWarning}>
                        SMS coaching is only available if you complete this step. Skipping is permanent — you cannot add SMS later without deleting your account.
                    </Text>
                </View>
                <TouchableOpacity
                    style={[styles.skipSmsBtn, busy && styles.secondaryBtnDisabled]}
                    onPress={onSkipSms}
                    disabled={busy}
                    activeOpacity={0.7}
                >
                    <Text style={styles.skipSmsBtnText}>Skip SMS (permanent)</Text>
                </TouchableOpacity>

                {SHOW_DEV_SKIP_CONTROLS ? (
                    <TouchableOpacity
                        style={[styles.devSkipBtn, busy && styles.secondaryBtnDisabled]}
                        onPress={onDevSkip}
                        disabled={busy}
                        activeOpacity={0.85}
                    >
                        <Text style={styles.devSkipText}>Dev: skip confirmation</Text>
                    </TouchableOpacity>
                ) : null}
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    root: {
        flex: 1,
        backgroundColor: colors.background,
    },
    scroll: { flex: 1 },
    scrollContent: {
        paddingHorizontal: spacing.xl,
    },
    backHit: { alignSelf: 'flex-start', padding: 8, marginBottom: spacing.md },
    kicker: { ...typography.label, color: colors.textMuted, letterSpacing: 1.2, marginBottom: spacing.sm },
    title: { ...typography.h2, fontSize: 26, marginBottom: spacing.md },
    lead: { ...typography.body, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        borderWidth: 1,
        borderColor: colors.border,
        ...shadows.md,
        marginBottom: spacing.lg,
    },
    cardLabel: { fontSize: 11, fontWeight: '700', color: colors.textMuted, letterSpacing: 0.8, marginBottom: spacing.sm },
    phoneUser: {
        fontSize: 20,
        fontWeight: '700',
        color: colors.foreground,
        marginBottom: spacing.sm,
        letterSpacing: 0.2,
    },
    phoneMissing: { fontSize: 14, color: colors.textSecondary, lineHeight: 20, marginBottom: spacing.sm },
    cardHint: { fontSize: 13, color: colors.textSecondary, lineHeight: 19, marginBottom: spacing.lg },
    primaryBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: 16,
        borderRadius: borderRadius.full,
    },
    primaryBtnText: { ...typography.button, color: colors.background, fontSize: 16 },
    waitingRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        marginBottom: spacing.md,
        paddingVertical: spacing.sm,
    },
    waitingText: { flex: 1, fontSize: 14, color: colors.textSecondary, lineHeight: 21 },
    confirmedLine: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
        marginBottom: spacing.md,
        lineHeight: 22,
    },
    hint: { fontSize: 14, color: colors.textSecondary, lineHeight: 21, marginBottom: spacing.xl },
    secondaryBtn: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 16,
        borderRadius: borderRadius.full,
        borderWidth: 2,
        borderColor: colors.foreground,
    },
    secondaryBtnDisabled: { opacity: 0.5 },
    secondaryBtnText: { fontSize: 16, fontWeight: '700', color: colors.foreground },
    skipSmsWrap: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.sm,
        marginTop: spacing.xl,
        marginBottom: spacing.sm,
        backgroundColor: colors.card,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        borderColor: colors.error,
        padding: spacing.md,
    },
    skipSmsWarning: {
        flex: 1,
        fontSize: 13,
        color: colors.error,
        lineHeight: 19,
        fontWeight: '500',
    },
    skipSmsBtn: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 13,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.error,
        marginBottom: spacing.lg,
    },
    skipSmsBtnText: { fontSize: 14, fontWeight: '600', color: colors.error },
    devSkipBtn: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 12,
        marginTop: spacing.lg,
        borderRadius: borderRadius.full,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
    },
    devSkipText: { fontSize: 13, fontWeight: '600', color: colors.textMuted },
});
