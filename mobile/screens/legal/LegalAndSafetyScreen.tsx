import React, { useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    TouchableOpacity,
    TextInput,
    Alert,
    Platform,
    Linking,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Constants from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

function getExtra(): Record<string, string | undefined> {
    return (Constants.expoConfig?.extra ?? {}) as Record<string, string | undefined>;
}

export default function LegalAndSafetyScreen() {
    const navigation = useNavigation();
    const { isAuthenticated, deleteAccount } = useAuth();
    const extra = getExtra();
    const supportEmail = extra.supportEmail || 'support@example.com';
    const privacyUrl = extra.privacyPolicyUrl;
    const termsUrl = extra.termsOfServiceUrl;
    const [password, setPassword] = useState('');
    const [busy, setBusy] = useState(false);

    const openUrl = (url: string, label: string) => {
        Linking.openURL(url).catch(() => Alert.alert('Error', `Could not open ${label}.`));
    };

    const mailSupport = () => {
        const subject = encodeURIComponent('Max app — support');
        Linking.openURL(`mailto:${supportEmail}?subject=${subject}`).catch(() =>
            Alert.alert('Contact', `Email us at ${supportEmail}`)
        );
    };

    const confirmDelete = () => {
        if (!password.trim()) {
            Alert.alert('Password required', 'Enter your password to delete your account.');
            return;
        }
        Alert.alert(
            'Delete account?',
            'This permanently removes your account and associated data. Channel posts will show as deleted. This cannot be undone.',
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Delete',
                    style: 'destructive',
                    onPress: async () => {
                        setBusy(true);
                        try {
                            await deleteAccount(password.trim());
                            setPassword('');
                        } catch (e: any) {
                            const d = e?.response?.data?.detail;
                            const msg = typeof d === 'string' ? d : e?.message || 'Could not delete account';
                            Alert.alert('Error', msg);
                        } finally {
                            setBusy(false);
                        }
                    },
                },
            ]
        );
    };

    return (
        <View style={styles.container}>
            <View style={styles.topBar}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.title}>Legal & safety</Text>
                <View style={{ width: 40 }} />
            </View>

            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                <Text style={styles.lead}>
                    Community channels: you can report posts and block users from the menu on each message. Reports are reviewed by our team.
                </Text>

                <TouchableOpacity style={styles.row} onPress={mailSupport} activeOpacity={0.7}>
                    <Ionicons name="mail-outline" size={22} color={colors.foreground} />
                    <View style={styles.rowTextWrap}>
                        <Text style={styles.rowTitle}>Contact & support</Text>
                        <Text style={styles.rowSub}>{supportEmail}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                </TouchableOpacity>

                {privacyUrl ? (
                    <TouchableOpacity style={styles.row} onPress={() => openUrl(privacyUrl, 'Privacy')} activeOpacity={0.7}>
                        <Ionicons name="document-text-outline" size={22} color={colors.foreground} />
                        <View style={styles.rowTextWrap}>
                            <Text style={styles.rowTitle}>Privacy policy</Text>
                            <Text style={styles.rowSub} numberOfLines={1}>
                                {privacyUrl}
                            </Text>
                        </View>
                        <Ionicons name="open-outline" size={18} color={colors.textMuted} />
                    </TouchableOpacity>
                ) : (
                    <View style={styles.hintBox}>
                        <Text style={styles.hintText}>
                            Set <Text style={styles.mono}>extra.privacyPolicyUrl</Text> in app.json and add the same link in App Store Connect.
                        </Text>
                    </View>
                )}

                {termsUrl ? (
                    <TouchableOpacity style={styles.row} onPress={() => openUrl(termsUrl, 'Terms')} activeOpacity={0.7}>
                        <Ionicons name="reader-outline" size={22} color={colors.foreground} />
                        <View style={styles.rowTextWrap}>
                            <Text style={styles.rowTitle}>Terms of service</Text>
                        </View>
                        <Ionicons name="open-outline" size={18} color={colors.textMuted} />
                    </TouchableOpacity>
                ) : null}

                {isAuthenticated ? (
                    <View style={styles.dangerZone}>
                        <Text style={styles.dangerTitle}>Delete account</Text>
                        <Text style={styles.dangerSub}>Removes your profile, chat history, and personal data from our systems.</Text>
                        <TextInput
                            style={styles.input}
                            placeholder="Confirm with your password"
                            placeholderTextColor={colors.textMuted}
                            secureTextEntry
                            value={password}
                            onChangeText={setPassword}
                            autoCapitalize="none"
                            editable={!busy}
                        />
                        <TouchableOpacity
                            style={[styles.deleteBtn, busy && styles.deleteBtnDisabled]}
                            onPress={confirmDelete}
                            disabled={busy}
                            activeOpacity={0.8}
                        >
                            <Text style={styles.deleteBtnText}>{busy ? 'Working…' : 'Delete my account'}</Text>
                        </TouchableOpacity>
                    </View>
                ) : null}

                <View style={{ height: Platform.OS === 'ios' ? 48 : 32 }} />
            </ScrollView>
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
        paddingTop: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        ...shadows.sm,
    },
    backBtn: { padding: spacing.xs },
    title: { ...typography.h3, color: colors.foreground, fontWeight: '700' },
    scroll: { padding: spacing.lg },
    lead: { ...typography.body, color: colors.textSecondary, lineHeight: 22, marginBottom: spacing.lg },
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.card,
        borderRadius: borderRadius.md,
        padding: spacing.md,
        marginBottom: spacing.sm,
        borderWidth: 1,
        borderColor: colors.border,
        gap: spacing.md,
    },
    rowTextWrap: { flex: 1, minWidth: 0 },
    rowTitle: { fontSize: 16, fontWeight: '600', color: colors.foreground },
    rowSub: { fontSize: 13, color: colors.textMuted, marginTop: 4 },
    hintBox: {
        padding: spacing.md,
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    hintText: { fontSize: 13, color: colors.textSecondary, lineHeight: 20 },
    mono: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 12 },
    dangerZone: {
        marginTop: spacing.xl,
        padding: spacing.lg,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.error,
        backgroundColor: colors.card,
    },
    dangerTitle: { fontSize: 17, fontWeight: '700', color: colors.error },
    dangerSub: { fontSize: 13, color: colors.textSecondary, marginTop: spacing.sm, lineHeight: 20 },
    input: {
        marginTop: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.sm,
        paddingHorizontal: spacing.md,
        paddingVertical: Platform.OS === 'ios' ? 12 : 8,
        color: colors.foreground,
        backgroundColor: colors.background,
    },
    deleteBtn: {
        marginTop: spacing.md,
        backgroundColor: colors.error,
        paddingVertical: 14,
        borderRadius: borderRadius.md,
        alignItems: 'center',
    },
    deleteBtnDisabled: { opacity: 0.6 },
    deleteBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
