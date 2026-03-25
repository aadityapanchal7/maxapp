/**
 * After paid scan results: user must text the Sendblue line so their number is in the thread ($100/mo plan).
 */

import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Linking, Platform, ActivityIndicator, Alert } from 'react-native';
import { useNavigation, useRoute, useFocusEffect } from '@react-navigation/native';
import Constants from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

type RouteParams = { next?: 'ModuleSelect' | 'Main' };

export default function SendblueConnectScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const { refreshUser, user } = useAuth();
    const [busy, setBusy] = useState(false);

    const smsConfirmed = user?.onboarding?.sendblue_sms_engaged === true;

    useFocusEffect(
        useCallback(() => {
            refreshUser().catch(() => {});
        }, [refreshUser])
    );

    useEffect(() => {
        if (smsConfirmed) return;
        const id = setInterval(() => {
            refreshUser().catch(() => {});
        }, 2500);
        return () => clearInterval(id);
    }, [smsConfirmed, refreshUser]);

    const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, string | undefined>;
    const smsE164 = (extra.sendblueSmsNumber || '+16468304204').replace(/\s/g, '');
    const display = extra.sendblueDisplayNumber || '+1 (646) 830-4204';
    const next: 'ModuleSelect' | 'Main' = route.params?.next === 'Main' ? 'Main' : 'ModuleSelect';

    const openSms = () => {
        const body = encodeURIComponent('Hey Max');
        const url = Platform.OS === 'ios' ? `sms:${smsE164}&body=${body}` : `sms:${smsE164}?body=${body}`;
        Linking.openURL(url).catch(() => {
            Alert.alert('Messages', `Text ${display} from your phone to connect.`);
        });
    };

    const onContinue = async () => {
        setBusy(true);
        try {
            await api.completeSendblueConnect();
            await refreshUser();
            if (next === 'ModuleSelect') {
                navigation.navigate('ModuleSelect');
            } else {
                navigation.navigate('Main');
            }
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not continue. Check your connection and try again.');
        } finally {
            setBusy(false);
        }
    };

    return (
        <View style={styles.root}>
            <TouchableOpacity style={styles.backHit} onPress={() => navigation.goBack()} hitSlop={12}>
                <Ionicons name="arrow-back" size={24} color={colors.foreground} />
            </TouchableOpacity>

            <Text style={styles.kicker}>One more step</Text>
            <Text style={styles.title}>Text Max to unlock coaching</Text>
            <Text style={styles.lead}>
                Send any message to our number so we can message you back on iMessage or SMS. This links your phone to
                your account.
            </Text>

            <View style={styles.card}>
                <Text style={styles.cardLabel}>OUR NUMBER</Text>
                <Text style={styles.phone}>{display}</Text>
                <TouchableOpacity style={styles.primaryBtn} onPress={openSms} activeOpacity={0.88}>
                    <Ionicons name="chatbubble-ellipses-outline" size={22} color={colors.background} />
                    <Text style={styles.primaryBtnText}>Open Messages</Text>
                </TouchableOpacity>
            </View>

            {!smsConfirmed ? (
                <View style={styles.waitingRow}>
                    <ActivityIndicator color={colors.foreground} size="small" />
                    <Text style={styles.waitingText}>
                        Waiting for your message… we&apos;ll enable continue as soon as we see it.
                    </Text>
                </View>
            ) : (
                <Text style={styles.confirmedLine}>We got your text — you&apos;re linked. Tap continue below.</Text>
            )}

            <Text style={styles.hint}>
                {smsConfirmed
                    ? 'You can always text this number later for help from Max.'
                    : 'Use Open Messages, send any text from the phone on your account, then stay on this screen until continue turns on.'}
            </Text>

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
        </View>
    );
}

const styles = StyleSheet.create({
    root: {
        flex: 1,
        backgroundColor: colors.background,
        paddingHorizontal: spacing.xl,
        paddingTop: 56,
        paddingBottom: spacing.xxl,
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
    phone: { fontSize: 28, fontWeight: '800', color: colors.foreground, marginBottom: spacing.lg },
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
});
