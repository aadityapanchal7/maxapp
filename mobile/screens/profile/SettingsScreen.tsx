import React, { useState, type ComponentProps } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Pressable, Platform, Alert, TextInput, ActivityIndicator, Keyboard } from 'react-native';
import { useNavigation, CommonActions } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';
import { elevatedCardSurface } from '../../theme/screenAesthetic';
import type { LegalDocId } from '../legal/legalDocuments';
import { LEGAL_SUPPORT_EMAIL } from '../legal/legalConstants';

const POLICY_ROWS: { id: LegalDocId; title: string; icon: ComponentProps<typeof Ionicons>['name'] }[] = [
    { id: 'privacy', title: 'Privacy policy', icon: 'document-text-outline' },
    { id: 'terms', title: 'Terms of service', icon: 'reader-outline' },
    { id: 'community', title: 'Community guidelines', icon: 'people-outline' },
    { id: 'cookies', title: 'Cookie notice', icon: 'information-circle-outline' },
];

export default function SettingsScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const { isPaid, logout, deleteAccount } = useAuth();
    const supportEmail =
        String((Constants.expoConfig?.extra as { supportEmail?: string } | undefined)?.supportEmail || '').trim() ||
        LEGAL_SUPPORT_EMAIL;

    const [deleteModalVisible, setDeleteModalVisible] = useState(false);
    const [deletePassword, setDeletePassword] = useState('');
    const [deleteBusy, setDeleteBusy] = useState(false);
    const [pushBusy, setPushBusy] = useState(false);

    const sendTestPush = async () => {
        setPushBusy(true);
        try {
            await api.sendTestPush();
            Alert.alert('Sent', 'Check your notifications — a test push is on its way.');
        } catch (e: any) {
            const detail = e?.response?.data?.detail || e?.message || 'Could not send test push';
            Alert.alert('Error', detail);
        } finally {
            setPushBusy(false);
        }
    };

    const openDoc = (document: LegalDocId) => {
        navigation.navigate('LegalDocument', { document });
    };

    const openSupport = () => {
        const q = `subject=${encodeURIComponent('Max app support')}`;
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
        <View style={styles.container}>
            <View style={[styles.topBar, { paddingTop: Math.max(insets.top, 12) }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>
                <View style={styles.topBarTitleBlock}>
                    <Text style={styles.titleEyebrow}>App</Text>
                    <Text style={styles.title}>Settings</Text>
                </View>
                <View style={{ width: 40 }} />
            </View>
            <View style={styles.topBarDivider} />

            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                {/* Account section */}
                <Text style={styles.sectionLabel}>ACCOUNT</Text>
                <View style={styles.cardGroup}>
                {isPaid ? (
                    <TouchableOpacity
                        style={styles.menuRow}
                        onPress={() => navigation.dispatch(CommonActions.navigate({ name: 'ManageSubscription' }))}
                        activeOpacity={0.7}
                    >
                        <Ionicons name="card-outline" size={22} color={colors.foreground} />
                        <Text style={styles.menuRowText}>Manage subscription</Text>
                        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                    </TouchableOpacity>
                ) : null}
                {isPaid ? (
                    <TouchableOpacity
                        style={styles.menuRow}
                        onPress={() => navigation.navigate('NotificationChannels', { editMode: true })}
                        activeOpacity={0.7}
                    >
                        <Ionicons name="notifications-outline" size={22} color={colors.foreground} />
                        <Text style={styles.menuRowText}>Notification preferences</Text>
                        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                    </TouchableOpacity>
                ) : null}
                <TouchableOpacity style={styles.menuRow} onPress={() => navigation.navigate('PersonalInfo')} activeOpacity={0.7}>
                    <Ionicons name="id-card-outline" size={22} color={colors.foreground} />
                    <Text style={styles.menuRowText}>Edit personal info</Text>
                    <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                </TouchableOpacity>
                <TouchableOpacity style={styles.menuRow} onPress={() => navigation.navigate('EditPersonal')} activeOpacity={0.7}>
                    <Ionicons name="leaf-outline" size={22} color={colors.foreground} />
                    <Text style={styles.menuRowText}>Edit lifestyle</Text>
                    <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                </TouchableOpacity>
                {Platform.OS === 'ios' ? (
                    <TouchableOpacity
                        style={[styles.menuRow, styles.menuRowLast]}
                        onPress={sendTestPush}
                        activeOpacity={0.7}
                        disabled={pushBusy}
                    >
                        <Ionicons name="notifications-outline" size={22} color={colors.foreground} />
                        <Text style={[styles.menuRowText, { flex: 1 }]}>Test push notification</Text>
                        {pushBusy ? (
                            <ActivityIndicator size="small" color={colors.textMuted} />
                        ) : (
                            <Ionicons name="send-outline" size={18} color={colors.textMuted} />
                        )}
                    </TouchableOpacity>
                ) : null}
                </View>

                {/* Support & legal */}
                <Text style={[styles.sectionLabel, styles.sectionLabelSpaced]}>SUPPORT & LEGAL</Text>
                <View style={styles.cardGroup}>
                <Pressable
                    onPress={openSupport}
                    style={({ pressed }) => [styles.menuRow, pressed && { opacity: 0.6 }]}
                    accessibilityRole="button"
                    accessibilityLabel="Contact support"
                >
                    <Ionicons name="mail-outline" size={22} color={colors.foreground} />
                    <View style={{ flex: 1 }}>
                        <Text style={styles.menuRowText}>Contact support</Text>
                        <Text style={styles.supportHint} numberOfLines={1}>{supportEmail}</Text>
                    </View>
                    <Ionicons name="open-outline" size={18} color={colors.textMuted} />
                </Pressable>
                {POLICY_ROWS.map((row, idx) => (
                    <Pressable
                        key={row.id}
                        onPress={() => openDoc(row.id)}
                        style={({ pressed }) => [
                            styles.menuRow,
                            idx === POLICY_ROWS.length - 1 && styles.menuRowLast,
                            pressed && { opacity: 0.6 },
                        ]}
                        accessibilityRole="link"
                    >
                        <Ionicons name={row.icon as any} size={22} color={colors.foreground} />
                        <Text style={styles.menuRowText}>{row.title}</Text>
                        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                    </Pressable>
                ))}
                </View>

                {/* Danger zone */}
                <Text style={[styles.sectionLabel, styles.sectionLabelSpaced]}>DANGER ZONE</Text>
                <View style={styles.cardGroup}>
                <TouchableOpacity style={[styles.menuRow, styles.menuRowLast, styles.deleteRow]} onPress={() => setDeleteModalVisible(true)} activeOpacity={0.7}>
                    <Ionicons name="trash-outline" size={22} color={colors.error} />
                    <Text style={[styles.menuRowText, { color: colors.error }]}>Delete account</Text>
                    <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                </TouchableOpacity>
                </View>

                <TouchableOpacity style={styles.logoutButton} onPress={logout} activeOpacity={0.7}>
                    <Text style={styles.logoutText}>Sign out</Text>
                </TouchableOpacity>

                <View style={{ height: Platform.OS === 'ios' ? 48 : 32 }} />
            </ScrollView>

            {deleteModalVisible && (
                <View style={styles.modalOverlay} pointerEvents="box-none">
                    <Pressable
                        style={StyleSheet.absoluteFill}
                        onPress={() => {
                            Keyboard.dismiss();
                            setDeleteModalVisible(false);
                        }}
                        accessibilityLabel="Close delete account dialog"
                        accessibilityRole="button"
                    />
                    <View style={styles.modalContent}>
                        <View style={styles.modalHeader}>
                            <Text style={styles.modalTitle}>Delete account</Text>
                            <TouchableOpacity onPress={() => setDeleteModalVisible(false)} style={styles.modalClose} activeOpacity={0.7}>
                                <Ionicons name="close" size={18} color={colors.textSecondary} />
                            </TouchableOpacity>
                        </View>
                        <Text style={styles.deleteHelpText}>
                            This permanently removes your account and personal data. This action cannot be undone.
                        </Text>
                        <TextInput
                            style={styles.input}
                            placeholder="Confirm with your password"
                            placeholderTextColor={colors.textMuted}
                            secureTextEntry
                            value={deletePassword}
                            onChangeText={setDeletePassword}
                            autoCapitalize="none"
                            editable={!deleteBusy}
                            returnKeyType="done"
                            onSubmitEditing={confirmDeleteAccount}
                        />
                        <View style={styles.modalButtons}>
                            <TouchableOpacity style={styles.cancelButton} onPress={() => setDeleteModalVisible(false)}>
                                <Text style={styles.cancelButtonText}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.deleteActionButton} onPress={confirmDeleteAccount} disabled={deleteBusy} activeOpacity={0.8}>
                                {deleteBusy ? <ActivityIndicator color="#fff" /> : <Text style={styles.deleteActionButtonText}>Delete</Text>}
                            </TouchableOpacity>
                        </View>
                    </View>
                </View>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.sm,
        backgroundColor: 'transparent',
    },
    topBarDivider: {
        height: StyleSheet.hairlineWidth,
        backgroundColor: colors.divider,
        marginHorizontal: spacing.lg,
        opacity: 0.9,
    },
    backBtn: { padding: spacing.xs },
    topBarTitleBlock: { flex: 1, alignItems: 'center', paddingHorizontal: spacing.sm },
    titleEyebrow: {
        ...typography.caption,
        letterSpacing: 1.2,
        textTransform: 'uppercase',
        marginBottom: 2,
    },
    title: { ...typography.h3, fontSize: 17, textAlign: 'center' },
    scroll: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.xl,
        paddingBottom: spacing.xxxl,
        maxWidth: 720,
        width: '100%',
        alignSelf: 'center',
    },
    sectionLabel: {
        ...typography.label,
        color: colors.textMuted,
        marginBottom: spacing.sm,
        marginTop: 0,
        letterSpacing: 1.2,
    },
    sectionLabelSpaced: {
        marginTop: spacing.xl + spacing.sm,
    },
    cardGroup: {
        ...elevatedCardSurface,
        overflow: 'hidden',
        paddingVertical: 0,
        paddingHorizontal: 0,
        marginBottom: spacing.sm,
        borderRadius: borderRadius.lg,
    },
    menuRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        paddingVertical: spacing.md + 2,
        paddingHorizontal: spacing.lg,
        gap: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.divider,
    },
    menuRowLast: {
        borderBottomWidth: 0,
    },
    menuRowText: {
        flex: 1,
        fontSize: 15,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: 0.1,
    },
    supportHint: {
        fontSize: 12,
        color: colors.textMuted,
        marginTop: 4,
        fontWeight: '400',
    },
    deleteRow: {
        backgroundColor: colors.card,
    },
    logoutButton: {
        alignSelf: 'center',
        marginTop: spacing.xl + spacing.sm,
        paddingVertical: spacing.sm + 2,
        paddingHorizontal: spacing.xl,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.background,
    },
    logoutText: {
        fontSize: 13,
        fontWeight: '500',
        color: colors.textSecondary,
        letterSpacing: 0.2,
    },
    modalOverlay: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: colors.overlay,
        justifyContent: 'center',
        alignItems: 'center',
        padding: spacing.lg,
    },
    modalContent: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        maxWidth: 440,
        width: '100%',
        zIndex: 1,
        borderWidth: 1,
        borderColor: colors.border,
    },
    modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.xl },
    modalTitle: { ...typography.h3 },
    modalClose: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
    deleteHelpText: {
        fontSize: 14,
        color: colors.textSecondary,
        lineHeight: 20,
        marginBottom: spacing.md,
    },
    input: {
        backgroundColor: colors.background,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.borderLight,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        color: colors.textPrimary,
        fontSize: 16,
        marginBottom: spacing.sm,
    },
    modalButtons: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: spacing.xl, gap: spacing.md },
    cancelButton: { padding: spacing.md },
    cancelButtonText: { fontSize: 14, fontWeight: '500', color: colors.textMuted },
    deleteActionButton: {
        backgroundColor: colors.error,
        borderRadius: borderRadius.md,
        paddingHorizontal: spacing.lg,
        paddingVertical: 10,
        borderWidth: 1,
        borderColor: colors.error,
    },
    deleteActionButtonText: { color: '#fff', fontSize: 14, fontWeight: '700' },
});
