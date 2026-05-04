import React, { useState, useEffect, useRef } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    KeyboardAvoidingView,
    Platform,
    Animated,
    Modal,
    FlatList,
    Pressable,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { PHONE_COUNTRIES, type PhoneCountry } from '../../constants/phoneCountryCodes';
import { buildFullPhoneNational } from '../../utils/buildLoginIdentifier';

export default function ForgotPasswordScreen() {
    const navigation = useNavigation<any>();
    const [step, setStep] = useState<1 | 2>(1);
    const [phoneNational, setPhoneNational] = useState('');
    const [phoneCountry, setPhoneCountry] = useState<PhoneCountry>(PHONE_COUNTRIES[0]);
    const [countryModalVisible, setCountryModalVisible] = useState(false);
    /** E.164 used for API after step 1 — must match confirm */
    const [phoneE164, setPhoneE164] = useState('');
    const [code, setCode] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [info, setInfo] = useState<string | null>(null);
    const [apiError, setApiError] = useState<string | null>(null);

    const fadeCard = useRef(new Animated.Value(0)).current;
    const slideCard = useRef(new Animated.Value(30)).current;
    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeCard, { toValue: 1, duration: 600, delay: 200, useNativeDriver: true }),
            Animated.timing(slideCard, { toValue: 0, duration: 600, delay: 200, useNativeDriver: true }),
        ]).start();
    }, []);

    const sendCode = async () => {
        const full = buildFullPhoneNational(phoneNational, phoneCountry);
        if (!full) {
            setApiError('Enter a valid phone number (national digits only)');
            return;
        }
        setLoading(true);
        setApiError(null);
        setInfo(null);
        try {
            const res = await api.requestPasswordResetSms(full);
            setPhoneE164(full);
            setInfo(res.message);
            setStep(2);
        } catch (error: any) {
            const msg = error.response?.data?.detail;
            setApiError(typeof msg === 'string' ? msg : 'Could not send code');
        } finally {
            setLoading(false);
        }
    };

    const resetPassword = async () => {
        if (!/^\d{6}$/.test(code.trim())) {
            setApiError('Enter the 6-digit code from your text');
            return;
        }
        if (newPassword.length < 8) {
            setApiError('Password must be at least 8 characters');
            return;
        }
        if (!phoneE164) {
            setApiError('Session expired. Go back and request a code again.');
            return;
        }
        setLoading(true);
        setApiError(null);
        setInfo(null);
        try {
            const res = await api.confirmPasswordResetSms(phoneE164, code.trim(), newPassword);
            setInfo(res.message);
            setTimeout(() => navigation.navigate('Login'), 1500);
        } catch (error: any) {
            const msg = error.response?.data?.detail;
            setApiError(typeof msg === 'string' ? msg : 'Reset failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
                <Animated.View style={[styles.card, { opacity: fadeCard, transform: [{ translateY: slideCard }] }]}>
                    <TouchableOpacity style={styles.backRow} onPress={() => navigation.goBack()} hitSlop={12}>
                        <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
                        <Text style={styles.backText}>Back</Text>
                    </TouchableOpacity>

                    <Text style={styles.title}>reset password</Text>
                    <Text style={styles.sub}>
                        {step === 1
                            ? 'We’ll text a code to the phone number on your Max account.'
                            : 'Enter the code and choose a new password.'}
                    </Text>

                    {step === 1 ? (
                        <View style={styles.form}>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>PHONE NUMBER</Text>
                                <View style={styles.phoneRow}>
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
                                            setApiError(null);
                                        }}
                                        keyboardType="phone-pad"
                                        autoCapitalize="none"
                                    />
                                </View>
                                <Text style={styles.phoneHint}>Same format as when you signed up — country + number without the code prefix.</Text>
                            </View>
                        </View>
                    ) : (
                        <View style={styles.form}>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>6-DIGIT CODE</Text>
                                <TextInput
                                    style={styles.input}
                                    placeholder="000000"
                                    placeholderTextColor={colors.textMuted}
                                    value={code}
                                    onChangeText={(t) => {
                                        setCode(t.replace(/\D/g, '').slice(0, 6));
                                        setApiError(null);
                                    }}
                                    keyboardType="number-pad"
                                    maxLength={6}
                                />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>NEW PASSWORD</Text>
                                <View style={styles.passwordRow}>
                                    <TextInput
                                        style={styles.passwordInput}
                                        placeholder="At least 8 characters"
                                        placeholderTextColor={colors.textMuted}
                                        value={newPassword}
                                        onChangeText={(t) => {
                                            setNewPassword(t);
                                            setApiError(null);
                                        }}
                                        secureTextEntry={!showPassword}
                                        autoCapitalize="none"
                                        autoCorrect={false}
                                    />
                                    <TouchableOpacity
                                        style={styles.viewPasswordBtn}
                                        onPress={() => setShowPassword((v) => !v)}
                                        hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                                    >
                                        <Ionicons
                                            name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                                            size={22}
                                            color={colors.textMuted}
                                        />
                                    </TouchableOpacity>
                                </View>
                            </View>
                        </View>
                    )}

                    <Modal
                        visible={countryModalVisible}
                        animationType="slide"
                        transparent
                        onRequestClose={() => setCountryModalVisible(false)}
                    >
                        <Pressable style={styles.modalBackdrop} onPress={() => setCountryModalVisible(false)}>
                            <Pressable style={styles.modalSheet} onPress={(e) => e.stopPropagation()}>
                                <View style={styles.modalHeader}>
                                    <Text style={styles.modalTitle}>Country code</Text>
                                    <TouchableOpacity
                                        onPress={() => setCountryModalVisible(false)}
                                        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                                    >
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
                                                setApiError(null);
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

                    {apiError && (
                        <View style={styles.apiErrorBox}>
                            <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
                            <Text style={styles.apiErrorText}>{apiError}</Text>
                        </View>
                    )}
                    {info && !apiError && (
                        <View style={styles.infoBox}>
                            <Ionicons name="checkmark-circle-outline" size={18} color={colors.success} />
                            <Text style={styles.infoText}>{info}</Text>
                        </View>
                    )}

                    <TouchableOpacity
                        style={[styles.button, loading && styles.buttonDisabled]}
                        onPress={step === 1 ? sendCode : resetPassword}
                        disabled={loading}
                        activeOpacity={0.7}
                    >
                        <Text style={styles.buttonText}>
                            {loading ? 'Please wait…' : step === 1 ? 'Send code' : 'Update password'}
                        </Text>
                    </TouchableOpacity>
                </Animated.View>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    keyboardView: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl + spacing.sm,
        borderWidth: 1,
        borderColor: colors.border,
    },
    backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: spacing.md },
    backText: { fontSize: 15, color: colors.textSecondary },
    title: {
        fontFamily: fonts.serif,
        fontSize: 26,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.4,
        marginBottom: spacing.md,
    },
    sub: { fontSize: 14, color: colors.textSecondary, marginBottom: spacing.xl + spacing.sm, lineHeight: 22 },
    form: { gap: spacing.md },
    inputGroup: { gap: spacing.xs },
    label: { ...typography.label, marginLeft: 2 },
    input: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.borderLight,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        color: colors.textPrimary,
        fontSize: 15,
    },
    phoneRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.borderLight,
        overflow: 'hidden',
    },
    countryCodeButton: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 12,
        paddingLeft: spacing.md,
        paddingRight: spacing.sm,
        borderRightWidth: 1,
        borderRightColor: colors.border,
        maxWidth: '42%',
    },
    countryCodeFlag: { fontSize: 18 },
    countryCodeText: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.textPrimary,
        flexShrink: 1,
    },
    phoneNationalInput: {
        flex: 1,
        paddingVertical: 12,
        paddingHorizontal: spacing.md,
        color: colors.textPrimary,
        fontSize: 15,
        minWidth: 0,
    },
    phoneHint: {
        fontSize: 11,
        color: colors.textMuted,
        marginTop: 4,
        marginLeft: 2,
    },
    passwordRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        borderWidth: 1,
        borderColor: colors.borderLight,
    },
    passwordInput: {
        flex: 1,
        paddingVertical: 12,
        paddingLeft: spacing.md,
        paddingRight: 8,
        color: colors.textPrimary,
        fontSize: 15,
    },
    viewPasswordBtn: {
        paddingVertical: 12,
        paddingHorizontal: spacing.sm,
        marginRight: spacing.xs,
    },
    modalBackdrop: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.5)',
        justifyContent: 'flex-end',
    },
    modalSheet: {
        backgroundColor: colors.card,
        borderTopLeftRadius: borderRadius.xl,
        borderTopRightRadius: borderRadius.xl,
        maxHeight: '72%',
        paddingBottom: Platform.OS === 'ios' ? 34 : spacing.lg,
    },
    modalHeader: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
    },
    modalTitle: { fontFamily: fonts.serif, fontSize: 18, fontWeight: '400', color: colors.foreground },
    countryRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 14,
        paddingHorizontal: spacing.lg,
        gap: 12,
        borderBottomWidth: 1,
        borderBottomColor: colors.borderLight,
    },
    countryRowSelected: { backgroundColor: colors.surface },
    countryRowFlag: { fontSize: 22, width: 32 },
    countryRowName: { flex: 1, fontSize: 15, color: colors.textPrimary },
    countryRowDial: { fontSize: 15, fontWeight: '600', color: colors.textSecondary, minWidth: 56, textAlign: 'right' },
    apiErrorBox: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        backgroundColor: colors.surface,
        padding: spacing.md,
        borderRadius: borderRadius.md,
        marginTop: spacing.md,
        borderWidth: 1,
        borderColor: colors.error + '44',
    },
    apiErrorText: { flex: 1, fontSize: 13, color: colors.error, fontWeight: '500' },
    infoBox: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        backgroundColor: colors.surface,
        padding: spacing.md,
        borderRadius: borderRadius.md,
        marginTop: spacing.md,
        borderWidth: 1,
        borderColor: colors.success + '44',
    },
    infoText: { flex: 1, fontSize: 13, color: colors.success, fontWeight: '500' },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.md,
        paddingVertical: 12,
        alignItems: 'center',
        marginTop: spacing.lg,
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    buttonDisabled: { opacity: 0.5 },
    buttonText: { ...typography.button },
});
