/**
 * Post-Sendblue: choose Apple push only, SMS only, or both. Profile: same UI to edit prefs.
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    Alert,
    Platform,
} from 'react-native';
import { CommonActions, useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import { getIosApnsDeviceTokenForBackend } from '../../services/registerIosPushToken';

type NextRoute = 'ModuleSelect' | 'Main';

type RouteParams = {
    next?: NextRoute;
    /** When true (e.g. from Profile), only PATCH prefs + token — do not call sendblue-connect/complete. */
    editMode?: boolean;
};

type ChannelChoice = 'apple_only' | 'sms_only' | 'both';

function prefsFromChoice(choice: ChannelChoice): { sms: boolean; app: boolean } {
    switch (choice) {
        case 'apple_only':
            return { sms: false, app: true };
        case 'sms_only':
            return { sms: true, app: false };
        default:
            return { sms: true, app: true };
    }
}

function choiceFromPrefs(smsOptIn: boolean, appOptIn: boolean): ChannelChoice {
    if (!smsOptIn && appOptIn) return 'apple_only';
    if (smsOptIn && !appOptIn) return 'sms_only';
    return 'both';
}

export default function NotificationChannelsScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { refreshUser, user } = useAuth();
    const [busy, setBusy] = useState(false);

    const params = (route.params || {}) as RouteParams;
    const next: NextRoute = params.next === 'Main' ? 'Main' : 'ModuleSelect';
    /** Profile-only: PATCH prefs. Post-Sendblue first visit must use complete + navigate (never goBack). */
    const editMode = params.editMode === true;

    const isIos = Platform.OS === 'ios';
    /** Server push is iOS-only; Android shows SMS + local in-app copy for "both". */
    const allowAppleOnly = isIos;

    const initialChoice = useMemo((): ChannelChoice => {
        const sms = user?.onboarding?.sendblue_sms_opt_in !== false;
        const app = user?.onboarding?.app_notifications_opt_in !== false;
        const c = choiceFromPrefs(sms, app);
        if (!allowAppleOnly && c === 'apple_only') return 'both';
        return c;
    }, [user?.id, user?.onboarding, allowAppleOnly]);

    const [choice, setChoice] = useState<ChannelChoice>(initialChoice);

    React.useEffect(() => {
        setChoice(initialChoice);
    }, [initialChoice]);

    const onSave = useCallback(async () => {
        const { sms, app } = prefsFromChoice(choice);
        if (!sms && !app) {
            Alert.alert('Choose a channel', 'Pick at least one way to get reminders.');
            return;
        }

        setBusy(true);
        try {
            if (editMode) {
                await api.patchNotificationChannels({
                    sms_opt_in: sms,
                    app_notifications_opt_in: app,
                });
            } else {
                await api.completeSendblueConnect({
                    sms_opt_in: sms,
                    app_notifications_opt_in: app,
                });
            }

            if (Platform.OS === 'ios') {
                if (app) {
                    const token = await getIosApnsDeviceTokenForBackend();
                    if (token) {
                        try {
                            await api.registerPushToken(token);
                        } catch (e) {
                            console.warn('registerPushToken', e);
                            Alert.alert(
                                'Push setup',
                                'Preferences saved. If alerts do not arrive, enable notifications for Max in Settings.',
                            );
                        }
                    } else {
                        Alert.alert(
                            'Notifications',
                            'Turn on notifications for Max in Settings to get reminders on this iPhone.',
                        );
                    }
                } else {
                    try {
                        await api.clearPushToken();
                    } catch {
                        /* ignore */
                    }
                }
            }

            await refreshUser();

            if (editMode) {
                navigation.goBack();
            } else if (next === 'Main') {
                navigation.navigate('Main');
            } else {
                navigation.dispatch(
                    CommonActions.reset({
                        index: 1,
                        routes: [{ name: 'Main' }, { name: 'ModuleSelect' }],
                    }),
                );
            }
        } catch (e) {
            console.error(e);
            Alert.alert('Error', 'Could not save. Check your connection and try again.');
        } finally {
            setBusy(false);
        }
    }, [choice, editMode, isIos, navigation, next, refreshUser]);

    const scrollBottomPad = insets.bottom + spacing.xxl + 8;

    const OptionRow = ({
        id,
        title,
        subtitle,
    }: {
        id: ChannelChoice;
        title: string;
        subtitle: string;
    }) => {
        const selected = choice === id;
        return (
            <TouchableOpacity
                style={[styles.optionCard, selected && styles.optionCardSelected]}
                onPress={() => setChoice(id)}
                activeOpacity={0.88}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
            >
                <View style={[styles.radioOuter, selected && styles.radioOuterSelected]}>
                    {selected ? <View style={styles.radioInner} /> : null}
                </View>
                <View style={{ flex: 1 }}>
                    <Text style={styles.optionTitle}>{title}</Text>
                    <Text style={styles.optionSub}>{subtitle}</Text>
                </View>
            </TouchableOpacity>
        );
    };

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

                <Text style={styles.kicker}>Reminders</Text>
                <Text style={styles.title}>How should Max reach you?</Text>
                <Text style={styles.lead}>
                    Schedule nudges and coaching can go to your phone as iPhone alerts and/or texts, based on what you
                    pick. You can change this anytime in Profile.
                </Text>

                {allowAppleOnly ? (
                    <OptionRow
                        id="apple_only"
                        title="iPhone notifications only"
                        subtitle="Alerts on this device. No SMS from our number for reminders."
                    />
                ) : null}

                <OptionRow
                    id="sms_only"
                    title="SMS only"
                    subtitle="Texts to the number on your account. No push from our servers."
                />

                <OptionRow
                    id="both"
                    title="Both"
                    subtitle={
                        isIos
                            ? 'iPhone alerts and SMS when we send reminders.'
                            : 'SMS plus in-app reminders on this device.'
                    }
                />

                <TouchableOpacity
                    style={[styles.primaryBtn, busy && styles.primaryBtnDisabled]}
                    onPress={onSave}
                    disabled={busy}
                    activeOpacity={0.88}
                >
                    {busy ? (
                        <ActivityIndicator color={colors.background} />
                    ) : (
                        <Text style={styles.primaryBtnText}>{editMode ? 'Save' : 'Continue'}</Text>
                    )}
                </TouchableOpacity>
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    scroll: { flex: 1 },
    scrollContent: { paddingHorizontal: spacing.xl },
    backHit: { alignSelf: 'flex-start', padding: 8, marginBottom: spacing.md },
    kicker: { ...typography.label, color: colors.textMuted, letterSpacing: 1.2, marginBottom: spacing.sm },
    title: { ...typography.h2, fontSize: 26, marginBottom: spacing.md },
    lead: { ...typography.body, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
    optionCard: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.md,
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.lg,
        borderWidth: 1,
        borderColor: colors.border,
        marginBottom: spacing.md,
        ...shadows.sm,
    },
    optionCardSelected: {
        borderColor: colors.foreground,
        borderWidth: 2,
    },
    radioOuter: {
        width: 22,
        height: 22,
        borderRadius: 11,
        borderWidth: 2,
        borderColor: colors.border,
        marginTop: 2,
        alignItems: 'center',
        justifyContent: 'center',
    },
    radioOuterSelected: { borderColor: colors.foreground },
    radioInner: {
        width: 12,
        height: 12,
        borderRadius: 6,
        backgroundColor: colors.foreground,
    },
    optionTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground, marginBottom: 4 },
    optionSub: { fontSize: 14, color: colors.textSecondary, lineHeight: 20 },
    primaryBtn: {
        marginTop: spacing.lg,
        backgroundColor: colors.foreground,
        paddingVertical: 16,
        borderRadius: borderRadius.full,
        alignItems: 'center',
        justifyContent: 'center',
    },
    primaryBtnDisabled: { opacity: 0.55 },
    primaryBtnText: { ...typography.button, color: colors.background, fontSize: 16 },
});
