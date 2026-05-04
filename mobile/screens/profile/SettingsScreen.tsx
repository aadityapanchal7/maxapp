import React, { useState, type ComponentProps } from 'react';
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    TouchableOpacity,
    Pressable,
    Platform,
    Alert,
    TextInput,
    ActivityIndicator,
    Keyboard,
} from 'react-native';
import { useNavigation, CommonActions } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Linking from 'expo-linking';
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

type ResponseLength = 'concise' | 'medium' | 'detailed';

const RESPONSE_LENGTH_OPTIONS: { value: ResponseLength; label: string; hint: string }[] = [
    { value: 'concise', label: 'Concise', hint: '1 short sentence when possible' },
    { value: 'medium', label: 'Medium', hint: '1–3 sentences (default)' },
    { value: 'detailed', label: 'Detailed', hint: 'Longer answers with specifics' },
];

export default function SettingsScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { isPaid, logout, deleteAccount, user, refreshUser } = useAuth();
    const supportEmail =
        String((Constants.expoConfig?.extra as { supportEmail?: string } | undefined)?.supportEmail || '').trim() ||
        LEGAL_SUPPORT_EMAIL;

    const [deleteModalVisible, setDeleteModalVisible] = useState(false);
    const [deletePassword, setDeletePassword] = useState('');
    const [deleteBusy, setDeleteBusy] = useState(false);

    const storedLength: ResponseLength = (user?.onboarding?.response_length ?? 'medium') as ResponseLength;
    const [responseLength, setResponseLength] = useState<ResponseLength>(storedLength);
    const [lengthPickerVisible, setLengthPickerVisible] = useState(false);
    const [lengthBusy, setLengthBusy] = useState(false);

    const currentLengthLabel =
        RESPONSE_LENGTH_OPTIONS.find((o) => o.value === responseLength)?.label ?? 'Medium';

    const applyResponseLength = async (next: ResponseLength) => {
        if (next === responseLength) {
            setLengthPickerVisible(false);
            return;
        }
        setLengthBusy(true);
        const previous = responseLength;
        setResponseLength(next);
        try {
            await api.patchResponseLength(next);
            await refreshUser().catch(() => undefined);
            setLengthPickerVisible(false);
        } catch (e: any) {
            setResponseLength(previous);
            const detail = e?.response?.data?.detail || e?.message || 'Could not update';
            Alert.alert('Error', detail);
        } finally {
            setLengthBusy(false);
        }
    };

    const openDoc = (document: LegalDocId) => navigation.navigate('LegalDocument', { document });

    const openSupport = () => {
        const q = `subject=${encodeURIComponent('Agartha support')}`;
        void Linking.openURL(`mailto:${encodeURIComponent(supportEmail)}?${q}`);
    };

    const confirmDeleteAccount = async () => {
        if (!deletePassword.trim()) {
            Alert.alert('Password required', 'Enter your password to delete your account.');
            return;
        }
        setDeleteBusy(true);
        try {
            await deleteAccount(deletePassword.trim());
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
                            hint="Plan, billing & renewal"
                            onPress={() => navigation.dispatch(CommonActions.navigate({ name: 'ManageSubscription' }))}
                        />
                    </View>
                ) : null}

                {/* ── Coaching ────────────────────────────────────────── */}
                <View style={st.section}>
                    <Text style={st.sectionLabel}>Coaching</Text>
                    {isPaid ? (
                        <Row
                            label="Notification preferences"
                            hint="Reminders, timing & intensity"
                            onPress={() => navigation.navigate('NotificationChannels', { editMode: true })}
                        />
                    ) : null}
                    <Row
                        label="Edit lifestyle"
                        hint="Goals & habits for better recommendations"
                        onPress={() => navigation.navigate('EditPersonal')}
                    />
                    <Row
                        label="Response length"
                        hint={`${currentLengthLabel} — Agartha chat verbosity`}
                        onPress={() => setLengthPickerVisible(true)}
                        disabled={lengthBusy}
                        trailing={
                            lengthBusy
                                ? <ActivityIndicator size="small" color={colors.textMuted} />
                                : undefined
                        }
                    />
                </View>

                {/* ── Profile ────────────────────────────────────────── */}
                <View style={st.section}>
                    <Text style={st.sectionLabel}>Profile</Text>
                    <Row
                        label="Edit personal info"
                        hint="Name, email & account details"
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
                    {LEGAL_ROWS.map((row) => (
                        <Row key={row.id} label={row.label} onPress={() => openDoc(row.id)} />
                    ))}
                </View>

                {/* ── Account ────────────────────────────────────────── */}
                <View style={st.section}>
                    <Text style={st.sectionLabel}>Account</Text>
                    <Row
                        label="Sign out"
                        labelColor={colors.textSecondary}
                        onPress={logout}
                        trailing={null}
                    />
                </View>

                <Text style={st.version}>
                    v{Constants.expoConfig?.version ?? '–'}
                    {Constants.expoConfig?.ios?.buildNumber ? ` (${Constants.expoConfig.ios.buildNumber})` : ''}
                </Text>

                <TouchableOpacity
                    onPress={() => setDeleteModalVisible(true)}
                    activeOpacity={0.4}
                    style={st.dangerTap}
                >
                    <Text style={st.dangerText}>Delete account</Text>
                </TouchableOpacity>

                <View style={{ height: Platform.OS === 'ios' ? 56 : 40 }} />
            </ScrollView>

            {/* ── Response length picker ──────────────────────────────── */}
            {lengthPickerVisible && (
                <View style={st.overlay} pointerEvents="box-none">
                    <Pressable
                        style={StyleSheet.absoluteFill}
                        onPress={() => setLengthPickerVisible(false)}
                        accessibilityLabel="Close"
                        accessibilityRole="button"
                    />
                    <View style={st.modal}>
                        <Text style={st.modalTitle}>Response length</Text>
                        <Text style={st.modalBody}>
                            Controls how verbose Agartha's chat replies are.
                        </Text>
                        {RESPONSE_LENGTH_OPTIONS.map((opt) => {
                            const selected = opt.value === responseLength;
                            return (
                                <TouchableOpacity
                                    key={opt.value}
                                    style={[st.row, selected ? { opacity: 1 } : undefined]}
                                    activeOpacity={0.6}
                                    onPress={() => applyResponseLength(opt.value)}
                                    disabled={lengthBusy}
                                >
                                    <View style={st.rowBody}>
                                        <Text style={st.rowLabel}>{opt.label}</Text>
                                        <Text style={st.rowHint}>{opt.hint}</Text>
                                    </View>
                                    {selected ? (
                                        <Ionicons name="checkmark" size={18} color={colors.foreground} />
                                    ) : null}
                                </TouchableOpacity>
                            );
                        })}
                    </View>
                </View>
            )}

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
