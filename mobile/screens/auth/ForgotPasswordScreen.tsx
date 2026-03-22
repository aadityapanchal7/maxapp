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
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function ForgotPasswordScreen() {
    const navigation = useNavigation<any>();
    const [step, setStep] = useState<1 | 2>(1);
    const [phone, setPhone] = useState('');
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
        if (!phone.trim()) {
            setApiError('Enter the phone number on your account');
            return;
        }
        setLoading(true);
        setApiError(null);
        setInfo(null);
        try {
            const res = await api.requestPasswordResetSms(phone.trim());
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
        setLoading(true);
        setApiError(null);
        setInfo(null);
        try {
            const res = await api.confirmPasswordResetSms(phone.trim(), code.trim(), newPassword);
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
                                <TextInput
                                    style={styles.input}
                                    placeholder="+1… or your saved number"
                                    placeholderTextColor={colors.textMuted}
                                    value={phone}
                                    onChangeText={(t) => {
                                        setPhone(t);
                                        setApiError(null);
                                    }}
                                    keyboardType="phone-pad"
                                    autoCapitalize="none"
                                />
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

                    {apiError && (
                        <View style={styles.apiErrorBox}>
                            <Ionicons name="alert-circle-outline" size={18} color="#ef4444" />
                            <Text style={styles.apiErrorText}>{apiError}</Text>
                        </View>
                    )}
                    {info && !apiError && (
                        <View style={styles.infoBox}>
                            <Ionicons name="checkmark-circle-outline" size={18} color="#22c55e" />
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
    keyboardView: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.lg },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        ...shadows.xl,
    },
    backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: spacing.md },
    backText: { fontSize: 15, color: colors.textSecondary },
    title: {
        fontSize: 28,
        fontWeight: '600',
        color: colors.foreground,
        letterSpacing: -0.5,
        marginBottom: spacing.sm,
    },
    sub: { fontSize: 14, color: colors.textSecondary, marginBottom: spacing.xl, lineHeight: 20 },
    form: { gap: spacing.md },
    inputGroup: { gap: spacing.xs },
    label: { ...typography.label, marginLeft: 2 },
    input: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        paddingVertical: 15,
        paddingHorizontal: spacing.md,
        color: colors.textPrimary,
        fontSize: 15,
    },
    passwordRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
    },
    passwordInput: {
        flex: 1,
        paddingVertical: 15,
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
    apiErrorBox: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        padding: spacing.md,
        borderRadius: borderRadius.md,
        marginTop: spacing.sm,
        borderWidth: 1,
        borderColor: 'rgba(239, 68, 68, 0.3)',
    },
    apiErrorText: { flex: 1, fontSize: 13, color: '#ef4444', fontWeight: '500' },
    infoBox: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        padding: spacing.md,
        borderRadius: borderRadius.md,
        marginTop: spacing.sm,
        borderWidth: 1,
        borderColor: 'rgba(34, 197, 94, 0.25)',
    },
    infoText: { flex: 1, fontSize: 13, color: '#22c55e', fontWeight: '500' },
    button: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: 16,
        alignItems: 'center',
        marginTop: spacing.md,
        ...shadows.md,
    },
    buttonDisabled: { opacity: 0.5 },
    buttonText: { ...typography.button },
});
