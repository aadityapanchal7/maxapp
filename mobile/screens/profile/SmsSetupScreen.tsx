/**
 * Add phone to account (first time only). Used from Profile or pre-Sendblue intro.
 */

import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    TextInput,
    Modal,
    FlatList,
    Pressable,
    Platform,
    Alert,
    ActivityIndicator,
    KeyboardAvoidingView,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';
import {
    PHONE_COUNTRIES,
    parseE164WithKnownCountries,
    type PhoneCountry,
} from '../../constants/phoneCountryCodes';

type NextRoute = 'ModuleSelect' | 'Main';

type RouteParams = {
    nextAfterSendblue?: NextRoute;
    continueTo?: 'SendblueConnect' | 'back';
    /** Pre-fill from `user.phone_number` (e.g. edit from Text Agartha screen). */
    prefillFromAccount?: boolean;
};

export default function SmsSetupScreen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { refreshUser, user } = useAuth();
    const params = (route.params || {}) as RouteParams;
    const prefillFromAccount = params.prefillFromAccount === true;

    const [phoneNational, setPhoneNational] = useState('');
    const [phoneCountry, setPhoneCountry] = useState<PhoneCountry>(PHONE_COUNTRIES[0]);
    const [countryModalVisible, setCountryModalVisible] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!prefillFromAccount || !user?.phone_number?.trim()) return;
        const parsed = parseE164WithKnownCountries(user.phone_number);
        if (parsed) {
            setPhoneCountry(parsed.country);
            setPhoneNational(parsed.nationalDigits);
        }
    }, [prefillFromAccount, user?.phone_number]);

    const onSave = async () => {
        const nationalDigits = phoneNational.replace(/\D/g, '');
        if (nationalDigits.length < 7) {
            setError('Enter a valid national number (at least 7 digits).');
            return;
        }
        const fullPhone = phoneCountry.dialCode + nationalDigits;
        setSaving(true);
        setError(null);
        try {
            await api.updateAccount({ phone_number: fullPhone });
            await refreshUser();
            const next = params.nextAfterSendblue === 'Main' ? 'Main' : 'ModuleSelect';
            if (params.continueTo === 'SendblueConnect') {
                navigation.replace('SendblueConnect', { next });
            } else {
                Alert.alert('Saved', prefillFromAccount ? 'Your phone number was updated.' : 'Your phone number was added.');
                navigation.goBack();
            }
        } catch (e: any) {
            const msg = e?.response?.data?.detail;
            setError(typeof msg === 'string' ? msg : 'Could not save. Try again.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <View style={styles.root}>
            <KeyboardAvoidingView
                style={styles.flex}
                behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            >
                <View style={[styles.header, { paddingTop: Math.max(insets.top, 12) }]}>
                    <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backHit} hitSlop={12}>
                        <Ionicons name="arrow-back" size={24} color={colors.foreground} />
                    </TouchableOpacity>
                    <Text style={styles.headerTitle}>{prefillFromAccount ? 'Update phone number' : 'Add phone number'}</Text>
                    <View style={{ width: 40 }} />
                </View>

                <View style={styles.centerWrap}>
                    <View style={styles.formCard}>
                        <Text style={styles.lead}>
                            {prefillFromAccount
                                ? 'Use the number you will text Agartha from on the next screen. Open Messages from that device or line.'
                                : "We'll use this for SMS coaching and to verify it's you when you text Agartha."}
                        </Text>

                        <Text style={styles.label}>PHONE NUMBER</Text>
                        <View style={[styles.phoneRow, error && styles.phoneRowErr]}>
                            <TouchableOpacity
                                style={styles.countryCodeButton}
                                onPress={() => setCountryModalVisible(true)}
                                activeOpacity={0.7}
                            >
                                <Text style={styles.countryCodeFlag}>{phoneCountry.flag}</Text>
                                <Text style={styles.countryCodeText} numberOfLines={1}>
                                    {phoneCountry.dialCode}
                                </Text>
                                <Ionicons name="chevron-down" size={16} color={colors.textMuted} />
                            </TouchableOpacity>
                            <TextInput
                                style={styles.phoneNationalInput}
                                placeholder="National number"
                                placeholderTextColor={colors.textMuted}
                                value={phoneNational}
                                onChangeText={(t) => {
                                    setPhoneNational(t);
                                    setError(null);
                                }}
                                keyboardType="phone-pad"
                            />
                        </View>
                        {error ? <Text style={styles.errText}>{error}</Text> : null}

                        <TouchableOpacity
                            style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
                            onPress={() => void onSave()}
                            disabled={saving}
                            activeOpacity={0.88}
                        >
                            {saving ? (
                                <ActivityIndicator color={colors.background} />
                            ) : (
                                <Text style={styles.saveBtnText}>Save</Text>
                            )}
                        </TouchableOpacity>
                    </View>
                </View>
            </KeyboardAvoidingView>

            <Modal visible={countryModalVisible} animationType="slide" transparent onRequestClose={() => setCountryModalVisible(false)}>
                <Pressable style={styles.modalBackdrop} onPress={() => setCountryModalVisible(false)}>
                    <Pressable style={styles.modalSheet} onPress={(e) => e.stopPropagation()}>
                        <View style={styles.modalHeader}>
                            <Text style={styles.modalTitle}>Country code</Text>
                            <TouchableOpacity onPress={() => setCountryModalVisible(false)} hitSlop={10}>
                                <Ionicons name="close" size={24} color={colors.foreground} />
                            </TouchableOpacity>
                        </View>
                        <FlatList
                            data={PHONE_COUNTRIES}
                            keyExtractor={(item) => `${item.dialCode}-${item.name}`}
                            keyboardShouldPersistTaps="handled"
                            renderItem={({ item }) => (
                                <TouchableOpacity
                                    style={[
                                        styles.countryRow,
                                        item.dialCode === phoneCountry.dialCode &&
                                            item.name === phoneCountry.name &&
                                            styles.countryRowSelected,
                                    ]}
                                    onPress={() => {
                                        setPhoneCountry(item);
                                        setCountryModalVisible(false);
                                    }}
                                    activeOpacity={0.65}
                                >
                                    <Text style={styles.countryRowFlag}>{item.flag}</Text>
                                    <Text style={styles.countryRowName} numberOfLines={2}>
                                        {item.name}
                                    </Text>
                                    <Text style={styles.countryRowDial}>{item.dialCode}</Text>
                                </TouchableOpacity>
                            )}
                        />
                    </Pressable>
                </Pressable>
            </Modal>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },
    flex: { flex: 1 },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.md,
        paddingBottom: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
    },
    backHit: { padding: 8 },
    headerTitle: { ...typography.h3, color: colors.foreground },
    centerWrap: {
        flex: 1,
        justifyContent: 'center',
        paddingHorizontal: spacing.xl,
    },
    formCard: {},
    lead: { fontSize: 15, color: colors.textSecondary, lineHeight: 22, marginBottom: spacing.xl },
    label: { ...typography.label, marginBottom: spacing.sm },
    phoneRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.borderLight,
        overflow: 'hidden',
    },
    phoneRowErr: { borderColor: colors.error },
    countryCodeButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 14,
        paddingLeft: spacing.md,
        paddingRight: spacing.sm,
        borderRightWidth: 1,
        borderRightColor: colors.border,
        maxWidth: '42%',
    },
    countryCodeFlag: { fontSize: 18 },
    countryCodeText: { fontSize: 15, fontWeight: '500', color: colors.textPrimary, flexShrink: 1 },
    phoneNationalInput: {
        flex: 1,
        paddingVertical: 14,
        paddingHorizontal: spacing.md,
        fontSize: 15,
        color: colors.textPrimary,
        minWidth: 0,
    },
    errText: { fontSize: 13, color: colors.error, marginTop: spacing.sm },
    saveBtn: {
        marginTop: spacing.xl,
        backgroundColor: colors.foreground,
        paddingVertical: 14,
        borderRadius: borderRadius.md,
        alignItems: 'center',
    },
    saveBtnDisabled: { opacity: 0.5 },
    saveBtnText: { ...typography.button, color: colors.background, fontSize: 16 },
    modalBackdrop: {
        flex: 1,
        backgroundColor: colors.overlay,
        justifyContent: 'flex-end',
    },
    modalSheet: {
        backgroundColor: colors.card,
        borderTopLeftRadius: borderRadius.xl,
        borderTopRightRadius: borderRadius.xl,
        maxHeight: '72%',
        paddingBottom: Platform.OS === 'ios' ? 34 : spacing.lg,
        borderWidth: 1,
        borderColor: colors.border,
    },
    modalHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.divider,
    },
    modalTitle: { ...typography.h3 },
    countryRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 14,
        paddingHorizontal: spacing.lg,
        gap: 12,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.divider,
    },
    countryRowSelected: { backgroundColor: colors.surface },
    countryRowFlag: { fontSize: 22, width: 32 },
    countryRowName: { flex: 1, fontSize: 15, color: colors.textPrimary },
    countryRowDial: { fontSize: 15, fontWeight: '500', color: colors.textSecondary, minWidth: 56, textAlign: 'right' },
});
