/**
 * Shown for paid users without a phone on file before the "Text Max" Sendblue screen.
 * Explains SMS won't work without a number; they can add one or continue and set up later in Profile.
 */

import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator, Alert } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

type NextRoute = 'ModuleSelect' | 'Main';

type RouteParams = {
    next?: NextRoute;
};

export default function SmsCoachingIntroScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { refreshUser } = useAuth();
    const [busy, setBusy] = useState(false);

    const next: NextRoute = route.params?.next === 'Main' ? 'Main' : 'ModuleSelect';

    const onAddPhone = () => {
        navigation.navigate('SmsSetup', {
            nextAfterSendblue: next,
            continueTo: 'SendblueConnect',
        });
    };

    const onContinueWithoutSms = async () => {
        setBusy(true);
        try {
            await api.completeSendblueConnect({ sms_opt_in: false, app_notifications_opt_in: true });
            await refreshUser();
            navigation.replace('NotificationChannels', { next, editMode: false });
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not save. Check your connection and try again.');
        } finally {
            setBusy(false);
        }
    };

    const padBottom = insets.bottom + spacing.xxl;

    return (
        <View style={styles.root}>
            <ScrollView
                contentContainerStyle={[
                    styles.scroll,
                    { paddingTop: Math.max(insets.top, 12) + 24, paddingBottom: padBottom },
                ]}
                keyboardShouldPersistTaps="handled"
            >
                <Text style={styles.kicker}>SMS coaching</Text>
                <Text style={styles.title}>Add a phone when you&apos;re ready</Text>
                <Text style={styles.body}>
                    You didn&apos;t add a phone number when you created your account. Without a number on file, we can&apos;t
                    turn on SMS reminders or link you to Max through Messages.
                </Text>
                <Text style={styles.body}>
                    You can add a number anytime from your profile — then you can text Max to finish SMS setup. Nothing is
                    permanent; skipping here only means SMS stays off until you add a phone.
                </Text>

                <TouchableOpacity style={styles.primaryBtn} onPress={onAddPhone} activeOpacity={0.88} disabled={busy}>
                    <Ionicons name="call-outline" size={22} color={colors.background} />
                    <Text style={styles.primaryBtnText}>Add phone number</Text>
                </TouchableOpacity>

                <TouchableOpacity
                    style={[styles.secondaryBtn, busy && styles.secondaryDisabled]}
                    onPress={() => void onContinueWithoutSms()}
                    disabled={busy}
                    activeOpacity={0.85}
                >
                    {busy ? (
                        <ActivityIndicator color={colors.foreground} />
                    ) : (
                        <Text style={styles.secondaryBtnText}>Continue without SMS for now</Text>
                    )}
                </TouchableOpacity>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    scroll: { paddingHorizontal: spacing.xl },
    kicker: { ...typography.label, color: colors.textMuted, letterSpacing: 1.2, marginBottom: spacing.sm },
    title: { ...typography.h2, fontSize: 26, marginBottom: spacing.md },
    body: { ...typography.body, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.md },
    primaryBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        borderRadius: borderRadius.md,
        marginTop: spacing.lg,
    },
    primaryBtnText: { ...typography.button, color: colors.background, fontSize: 16 },
    secondaryBtn: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 14,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        marginTop: spacing.md,
    },
    secondaryDisabled: { opacity: 0.55 },
    secondaryBtnText: { fontSize: 16, fontWeight: '600', color: colors.foreground },
});
