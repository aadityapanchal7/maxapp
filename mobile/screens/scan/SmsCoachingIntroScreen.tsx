/**
 * Shown for paid users without a phone on file before the "Text Max" Sendblue screen.
 * Explains SMS won't work without a number; they can add one or continue and set up later in Profile.
 */

import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, fonts } from '../../theme/dark';

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

    return (
        <View style={styles.root}>
            <View style={[styles.content, { paddingTop: Math.max(insets.top, 12) + 48, paddingBottom: Math.max(insets.bottom, 20) + 16 }]}>
                {/* Top spacer + icon */}
                <View style={styles.heroSection}>
                    <View style={styles.iconCircle}>
                        <Ionicons name="chatbubbles-outline" size={32} color={colors.foreground} />
                    </View>
                    <Text style={styles.title}>Connect your phone</Text>
                    <Text style={styles.subtitle}>
                        Add your number to text Max directly and get SMS reminders for your schedule.
                    </Text>
                </View>

                {/* Feature bullets */}
                <View style={styles.features}>
                    {[
                        { icon: 'chatbubble-ellipses-outline' as const, text: 'Text Max from Messages' },
                        { icon: 'notifications-outline' as const, text: 'SMS schedule reminders' },
                        { icon: 'time-outline' as const, text: 'Set up anytime in Profile' },
                    ].map((item, i) => (
                        <View key={i} style={styles.featureRow}>
                            <View style={styles.featureIconWrap}>
                                <Ionicons name={item.icon} size={18} color={colors.foreground} />
                            </View>
                            <Text style={styles.featureText}>{item.text}</Text>
                        </View>
                    ))}
                </View>

                {/* Bottom buttons */}
                <View style={styles.actions}>
                    <TouchableOpacity style={styles.primaryBtn} onPress={onAddPhone} activeOpacity={0.88} disabled={busy}>
                        <Text style={styles.primaryBtnText}>Add phone number</Text>
                        <Ionicons name="arrow-forward" size={18} color={colors.background} />
                    </TouchableOpacity>

                    <TouchableOpacity
                        style={[styles.secondaryBtn, busy && styles.secondaryDisabled]}
                        onPress={() => void onContinueWithoutSms()}
                        disabled={busy}
                        activeOpacity={0.85}
                    >
                        {busy ? (
                            <ActivityIndicator color={colors.textMuted} />
                        ) : (
                            <Text style={styles.secondaryBtnText}>Skip for now</Text>
                        )}
                    </TouchableOpacity>
                </View>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    content: {
        flex: 1,
        paddingHorizontal: spacing.xl,
        justifyContent: 'space-between',
    },

    heroSection: {
        alignItems: 'center',
        paddingTop: 32,
    },
    iconCircle: {
        width: 72,
        height: 72,
        borderRadius: 36,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.borderLight,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: spacing.lg,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 28,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.5,
        textAlign: 'center',
        marginBottom: spacing.sm,
    },
    subtitle: {
        fontSize: 15,
        fontWeight: '400',
        color: colors.textSecondary,
        lineHeight: 22,
        textAlign: 'center',
        maxWidth: 280,
    },

    features: {
        gap: 16,
        paddingHorizontal: spacing.sm,
    },
    featureRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 14,
    },
    featureIconWrap: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.borderLight,
        alignItems: 'center',
        justifyContent: 'center',
    },
    featureText: {
        fontSize: 15,
        fontWeight: '500',
        color: colors.foreground,
        letterSpacing: -0.1,
    },

    actions: {
        gap: spacing.sm,
    },
    primaryBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        backgroundColor: colors.foreground,
        paddingVertical: 16,
        borderRadius: borderRadius.full,
    },
    primaryBtnText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.background,
        letterSpacing: 0.1,
    },
    secondaryBtn: {
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: 14,
    },
    secondaryDisabled: { opacity: 0.55 },
    secondaryBtnText: {
        fontSize: 14,
        fontWeight: '500',
        color: colors.textMuted,
    },
});
