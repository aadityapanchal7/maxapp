import React, { useState, type ComponentProps } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    TouchableOpacity,
    Pressable,
    Platform,
    TextInput,
    ActivityIndicator,
    Keyboard,
} from 'react-native'
import { Alert } from '../../components/InAppAlert';
import { useNavigation, CommonActions } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Linking from 'expo-linking';
import { manualReview } from '../../services/reviewService';
import Constants from 'expo-constants';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { colors, spacing, borderRadius, fonts } from '../../theme/dark';
import type { LegalDocId } from '../legal/legalDocuments';
import { LEGAL_SUPPORT_EMAIL } from '../legal/legalConstants';

const LEGAL_ROWS: { id: LegalDocId; label: string }[] = [
    { id: 'privacy', label: 'Privacy policy' },
    { id: 'terms', label: 'Terms of service' },
    { id: 'community', label: 'Community guidelines' },
    { id: 'cookies', label: 'Cookie notice' },
];

/* ── Primitives ──────────────────────────────────────────────────── */

function Row({
    label,
    hint,
    onPress,
    trailing,
    labelColor,
    disabled,
}: {
    label: string;
    hint?: string;
    onPress: () => void;
    trailing?: React.ReactNode;
    labelColor?: string;
    disabled?: boolean;
}) {
    return (
        <TouchableOpacity
            style={st.row}
            onPress={onPress}
            activeOpacity={0.5}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityLabel={label}
        >
            <View style={st.rowBody}>
                <Text style={[st.rowLabel, labelColor ? { color: labelColor } : undefined]}>{label}</Text>
                {hint ? <Text style={st.rowHint}>{hint}</Text> : null}
            </View>
            {trailing ?? <Ionicons name="chevron-forward" size={16} color={colors.textMuted} style={{ opacity: 0.4 }} />}
        </TouchableOpacity>
    );
}

/* ── Screen ──────────────────────────────────────────────────────── */

export default function SettingsScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { isPaid, logout, deleteAccount, user } = useAuth();
    const isOAuthAccount = String((user as any)?.auth_provider || 'password').toLowerCase() !== 'password';
    const supportEmail =
        String((Constants.expoConfig?.extra as { supportEmail?: string } | undefined)?.supportEmail || '').trim() ||
        LEGAL_SUPPORT_EMAIL;

    const [deleteModalVisible, setDeleteModalVisible] = useState(false);
    const [deletePassword, setDeletePassword] = useState('');
    const [deleteBusy, setDeleteBusy] = useState(false);

    const openDoc = (document: LegalDocId) => navigation.navigate('LegalDocument', { document });

    const googleStatusQ = useQuery({
        queryKey: ['googleStatus'],
        queryFn: () => api.getGoogleStatus(),
        staleTime: 60_000,
    });
    // `!== false` (not `=== true`) so the row stays put while the status query
    // is in flight — matching DayPlannerScreen. `=== true` made it pop in late.
    const showCalendarRow = googleStatusQ.data?.calendar_link_enabled !== false;

    const openSupport = () => {
        const q = `subject=${encodeURIComponent('Max support')}`;
        void Linking.openURL(`mailto:${encodeURIComponent(supportEmail)}?${q}`);
    };

    const confirmSignOut = () => {
        // react-native-web does not render Alert button dialogs, so the native
        // Alert path below never fires its onPress on web. Use a real browser
        // confirm there so sign-out actually works on the web build.
        if (Platform.OS === 'web') {
            if (typeof window !== 'undefined' && window.confirm('Sign out?')) {
                void logout();
            }
            return;
        }
        Alert.alert('Sign out?', '', [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Sign out', style: 'destructive', onPress: logout },
        ]);
    };

    const confirmDeleteAccount = async () => {
        // Google/OAuth accounts have no password — authorize via session instead.
        if (!isOAuthAccount && !deletePassword.trim()) {
            Alert.alert('Password required', 'Enter your password to delete your account.');
            return;
        }
        setDeleteBusy(true);
        try {
            await deleteAccount(isOAuthAccount ? undefined : deletePassword.trim());
            setDeletePassword('');
            setDeleteModalVisible(false);
        } catch (e: any) {
            const d = e?.response?.data?.detail;
            const msg = typeof d === 'string' ? d : e?.message || 'Could not delete account';
            Alert.alert('Error', msg);
        } finally {
            setDeleteBusy(false);
        }
    };

    return (
        <View style={st.container}>
            {/* Header */}
            <View style={[st.header, { paddingTop: Math.max(insets.top, 12) + 4 }]}>
                <TouchableOpacity
                    onPress={() => navigation.goBack()}
                    style={st.backBtn}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                >
                    <Ionicons name="arrow-back" size={20} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={st.headerTitle}>Settings</Text>
                <View style={{ width: 36 }} />
            </View>

            <ScrollView
                contentContainerStyle={st.scroll}
                showsVerticalScrollIndicator={false}
                keyboardShouldPersistTaps="handled"
            >
                {/* ── Membership ──────────────────────────────────────── */}
                {isPaid ? (
                    <View style={st.section}>
                        <Text style={st.sectionLabel}>Membership</Text>
                        <Row
                            label="Manage subscription"
                            hint="Manage your plan"
                            onPress={() => navigation.dispatch(CommonActions.navigate({ name: 'ManageSubscription' }))}
                        />
                    </View>
                ) : null}

                {/* ── Coaching ────────────────────────────────────────── */}
                <View style={st.section}>
                    <Text style={st.sectionLabel}>Coaching</Text>
                    {/* Notification preferences row removed — push is on
                        by default; users toggle device-level via OS. */}
                    <Row
                        label="Edit lifestyle"
                        hint="Your goals & habits"
                        onPress={() => navigation.navigate('EditPersonal')}
                    />
                    <Row
                        label="My products"
                        onPress={() => navigation.navigate('MyProducts')}
                    />
                    {showCalendarRow ? (
                        <Row
                            label="Google Calendar"
                            hint={
                                googleStatusQ.data?.connected
                                    ? (googleStatusQ.data?.routine_sync_enabled
                                        ? 'Connected · syncing routine'
                                        : 'Connected')
                                    : 'Link your calendar'
                            }
                            onPress={() => navigation.navigate('GoogleCalendarConnect')}
                        />
                    ) : null}
                    {/* Response length lives in the chat sidebar — keep
                        Settings focused on profile + account / legal. */}
                </View>

                {/* ── Profile ────────────────────────────────────────── */}
                <View style={st.section}>
                    <Text style={st.sectionLabel}>Profile</Text>
                    <Row
                        label="Edit personal info"
                        onPress={() => navigation.navigate('PersonalInfo')}
                    />
                </View>

                {/* ── Support ────────────────────────────────────────── */}
                <View style={st.section}>
                    <Text style={st.sectionLabel}>Support</Text>
                    <Row
                        label="Contact support"
                        hint={supportEmail}
                        onPress={openSupport}
                        trailing={<Ionicons name="open-outline" size={14} color={colors.textMuted} style={{ opacity: 0.4 }} />}
                    />
                    {Platform.OS === 'ios' ? (
                        <Row
                            label="Rate us on the App Store"
                            onPress={() => { void manualReview(); }}
                            trailing={<Ionicons name="star-outline" size={14} color={colors.textMuted} style={{ opacity: 0.5 }} />}
                        />
                    ) : null}
                    {LEGAL_ROWS.map((row) => (
                        <Row key={row.id} label={row.label} onPress={() => openDoc(row.id)} />
                    ))}
                </View>

                {/* ── Account & Data ──────────────────────────────────── */}
                {/* Account deletion must be visible/accessible in-app (Apple
                    Guideline 5.1.1(v) + GDPR). Keep it in this section, not
                    buried below the version string. */}
                <View style={st.section}>
                    <Text style={st.sectionLabel}>Account & Data</Text>
                    <Row
                        label="Sign out"
                        labelColor={colors.textSecondary}
                        onPress={confirmSignOut}
                        trailing={null}
                    />
                    <Row
                        label="Delete account"
                        hint="Permanently erase your account and data"
                        labelColor="#D7263D"
                        onPress={() => setDeleteModalVisible(true)}
                        trailing={<Ionicons name="trash-outline" size={16} color="#D7263D" style={{ opacity: 0.7 }} />}
                    />
                </View>

                <Text style={st.version}>
                    v{Constants.expoConfig?.version ?? '-'}
                    {Constants.expoConfig?.ios?.buildNumber ? ` (${Constants.expoConfig.ios.buildNumber})` : ''}
                </Text>

                <View style={{ height: Platform.OS === 'ios' ? 56 : 40 }} />
            </ScrollView>

            {/* ── Delete modal ────────────────────────────────────────── */}
            {deleteModalVisible && (
                <View style={st.overlay} pointerEvents="box-none">
                    <Pressable
                        style={StyleSheet.absoluteFill}
                        onPress={() => { Keyboard.dismiss(); setDeleteModalVisible(false); }}
                        accessibilityLabel="Close"
                        accessibilityRole="button"
                    />
                    <View style={st.modal}>
                        <Text style={st.modalTitle}>Delete account</Text>
                        <Text style={st.modalBody}>
                            This permanently removes your account and all personal data. This cannot be undone.
                        </Text>
                        {!isOAuthAccount && (
                            <TextInput
                                style={st.modalInput}
                                placeholder="Enter your password"
                                placeholderTextColor={colors.textMuted}
                                secureTextEntry
                                value={deletePassword}
                                onChangeText={setDeletePassword}
                                autoCapitalize="none"
                                editable={!deleteBusy}
                                returnKeyType="done"
                                onSubmitEditing={confirmDeleteAccount}
                            />
                        )}
                        <View style={st.modalBtns}>
                            <TouchableOpacity style={st.modalCancelBtn} onPress={() => setDeleteModalVisible(false)}>
                                <Text style={st.modalCancelLabel}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={st.modalDeleteBtn}
                                onPress={confirmDeleteAccount}
                                disabled={deleteBusy}
                                activeOpacity={0.8}
                            >
                                {deleteBusy
                                    ? <ActivityIndicator color="#fff" />
                                    : <Text style={st.modalDeleteLabel}>Delete</Text>}
                            </TouchableOpacity>
                        </View>
                    </View>
                </View>
            )}
        </View>
    );
}

/* ── Styles ──────────────────────────────────────────────────────── */

const st = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },

    header: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
    },
    backBtn: { padding: spacing.xs, marginRight: spacing.sm },
    headerTitle: {
        flex: 1,
        fontFamily: fonts.serif,
        fontSize: 24,
        fontWeight: '400',
        letterSpacing: -0.4,
        color: colors.foreground,
    },

    scroll: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.sm,
        paddingBottom: spacing.xxxl,
        maxWidth: 520,
        width: '100%',
        alignSelf: 'center',
    },

    /* Sections — no cards, just label + rows + divider */
    section: {
        marginTop: spacing.lg + spacing.sm,
    },
    sectionLabel: {
        fontSize: 11,
        fontWeight: '500',
        color: colors.textMuted,
        letterSpacing: 1.4,
        textTransform: 'uppercase',
        marginBottom: spacing.xs,
        opacity: 0.7,
    },

    /* Rows — borderless, airy */
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 15,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.borderLight,
    },
    rowBody: { flex: 1, minWidth: 0 },
    rowLabel: {
        fontSize: 15,
        fontWeight: '400',
        color: colors.foreground,
    },
    rowHint: {
        fontSize: 12,
        fontWeight: '400',
        color: colors.textMuted,
        marginTop: 2,
    },

    dangerTap: {
        alignSelf: 'center',
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.lg,
        marginTop: spacing.lg,
    },
    dangerText: {
        fontSize: 12,
        fontWeight: '400',
        color: colors.textMuted,
        opacity: 0.5,
    },

    version: {
        fontSize: 11,
        color: colors.textMuted,
        textAlign: 'center',
        marginTop: spacing.xxl,
        opacity: 0.45,
        letterSpacing: 0.3,
    },

    /* Modal */
    overlay: {
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: colors.overlay,
        justifyContent: 'center',
        alignItems: 'center',
        padding: spacing.lg,
    },
    modal: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        maxWidth: 380,
        width: '100%',
        zIndex: 1,
    },
    modalTitle: {
        fontFamily: fonts.serif,
        fontSize: 20,
        color: colors.foreground,
        marginBottom: spacing.sm,
    },
    modalBody: {
        fontSize: 14,
        color: colors.textSecondary,
        lineHeight: 20,
        marginBottom: spacing.lg,
    },
    modalInput: {
        backgroundColor: colors.background,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.borderLight,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        color: colors.foreground,
        fontSize: 15,
    },
    modalBtns: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        marginTop: spacing.xl,
        gap: spacing.md,
    },
    modalCancelBtn: { paddingVertical: 10, paddingHorizontal: spacing.md },
    modalCancelLabel: { fontSize: 14, fontWeight: '500', color: colors.textMuted },
    modalDeleteBtn: {
        backgroundColor: colors.error,
        borderRadius: borderRadius.md,
        paddingHorizontal: spacing.lg,
        paddingVertical: 10,
    },
    modalDeleteLabel: { color: '#fff', fontSize: 14, fontWeight: '600' },
});
