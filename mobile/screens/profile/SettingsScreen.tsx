import React, { useState, type ComponentProps } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Pressable, Platform, Alert, TextInput, ActivityIndicator } from 'react-native';
import { useNavigation, CommonActions } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
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
                <Text style={styles.title}>Settings</Text>
                <View style={{ width: 40 }} />
            </View>

            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                {/* Account section */}
                <Text style={styles.sectionLabel}>ACCOUNT</Text>
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

                {/* Support & legal */}
                <Text style={[styles.sectionLabel, { marginTop: spacing.xl }]}>SUPPORT & LEGAL</Text>
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
                {POLICY_ROWS.map((row) => (
                    <Pressable
                        key={row.id}
                        onPress={() => openDoc(row.id)}
                        style={({ pressed }) => [styles.menuRow, pressed && { opacity: 0.6 }]}
                        accessibilityRole="link"
                    >
                        <Ionicons name={row.icon as any} size={22} color={colors.foreground} />
                        <Text style={styles.menuRowText}>{row.title}</Text>
                        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                    </Pressable>
                ))}

                {/* Danger zone */}
                <Text style={[styles.sectionLabel, { marginTop: spacing.xl }]}>DANGER ZONE</Text>
                <TouchableOpacity style={[styles.menuRow, styles.deleteRow]} onPress={() => setDeleteModalVisible(true)} activeOpacity={0.7}>
                    <Ionicons name="trash-outline" size={22} color={colors.error} />
                    <Text style={[styles.menuRowText, { color: colors.error }]}>Delete account</Text>
                    <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                </TouchableOpacity>

                <TouchableOpacity style={styles.logoutButton} onPress={logout} activeOpacity={0.7}>
                    <Text style={styles.logoutText}>Sign out</Text>
                </TouchableOpacity>

                <View style={{ height: Platform.OS === 'ios' ? 48 : 32 }} />
            </ScrollView>

            {deleteModalVisible && (
                <Pressable style={styles.modalOverlay} onPress={() => setDeleteModalVisible(false)}>
                    <Pressable style={styles.modalContent} onPress={() => {}}>
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
                        />
                        <View style={styles.modalButtons}>
                            <TouchableOpacity style={styles.cancelButton} onPress={() => setDeleteModalVisible(false)}>
                                <Text style={styles.cancelButtonText}>Cancel</Text>
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.deleteActionButton} onPress={confirmDeleteAccount} disabled={deleteBusy} activeOpacity={0.8}>
                                {deleteBusy ? <ActivityIndicator color="#fff" /> : <Text style={styles.deleteActionButtonText}>Delete</Text>}
                            </TouchableOpacity>
                        </View>
                    </Pressable>
                </Pressable>
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
        paddingHorizontal: spacing.md,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        ...shadows.sm,
    },
    backBtn: { padding: spacing.xs },
    title: { ...typography.h3, color: colors.foreground, fontWeight: '700' },
    scroll: { padding: spacing.lg, paddingBottom: spacing.xxl, maxWidth: 720, width: '100%', alignSelf: 'center' },
    sectionLabel: {
        ...typography.label,
        color: colors.textMuted,
        marginBottom: spacing.sm,
        marginTop: spacing.md,
        letterSpacing: 1,
    },
    menuRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.lg,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: colors.border,
        gap: spacing.md,
        marginBottom: spacing.sm,
    },
    menuRowText: {
        flex: 1,
        fontSize: 16,
        fontWeight: '500',
        color: colors.foreground,
    },
    supportHint: {
        fontSize: 11,
        color: colors.textMuted,
        opacity: 0.85,
        marginTop: 2,
    },
    deleteRow: {
        borderColor: 'rgba(220, 38, 38, 0.35)',
        backgroundColor: colors.card,
    },
    logoutButton: {
        alignItems: 'center',
        marginTop: spacing.xl,
        paddingVertical: spacing.md,
    },
    logoutText: {
        fontSize: 15,
        fontWeight: '500',
        color: colors.textMuted,
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
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        maxWidth: 440,
        width: '100%',
        ...shadows.xl,
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
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        padding: spacing.lg,
        color: colors.textPrimary,
        fontSize: 16,
        marginBottom: spacing.sm,
    },
    modalButtons: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: spacing.xl, gap: spacing.md },
    cancelButton: { padding: spacing.md },
    cancelButtonText: { fontSize: 14, fontWeight: '500', color: colors.textMuted },
    deleteActionButton: {
        backgroundColor: colors.error,
        borderRadius: borderRadius.full,
        paddingHorizontal: spacing.xl,
        paddingVertical: spacing.md,
        ...shadows.sm,
    },
    deleteActionButtonText: { color: '#fff', fontSize: 14, fontWeight: '700' },
});
