import React, { useState, useEffect, useRef } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    Alert,
    KeyboardAvoidingView,
    Platform,
    ScrollView,
    Animated,
    Modal,
    FlatList,
    Pressable,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { CachedImage } from '../../components/CachedImage';
import { PHONE_COUNTRIES, type PhoneCountry } from '../../constants/phoneCountryCodes';

function signupErrorMessage(error: any): string {
    const res = error?.response;
    const base = api.getBaseUrl?.() || '';

    if (!res) {
        const msg = String(error?.message || '');
        const isTimeout = error?.code === 'ECONNABORTED' || /timeout/i.test(msg);
        const isNetwork = /Network Error|Failed to fetch|ECONNREFUSED|ENOTFOUND/i.test(msg) || isTimeout;
        if (isNetwork) {
            const local = /127\.0\.0\.1|localhost/i.test(base);
            if (local && Platform.OS === 'web') {
                return "Can't reach the API from the browser. Start the backend (uvicorn on port 8000 from maxapp/backend), keep EXPO_PUBLIC_API_BASE_URL as http://127.0.0.1:8000/api/, and restart Metro. If the server is up, check the browser Network tab for blocked requests (CORS).";
            }
            if (local) {
                return "Can't reach the API. On a real phone, localhost doesn't point to your Mac — set EXPO_PUBLIC_API_BASE_URL to your Mac's LAN IP (e.g. http://192.168.x.x:8000/api/) and use `npx expo start --lan`, or use the production API URL. Then restart Metro.";
            }
            return "Can't reach the server. Check your connection, that the API is running, and EXPO_PUBLIC_API_BASE_URL in mobile/.env, then restart Metro with --clear.";
        }
        return msg || 'Could not create account';
    }

    const d = res?.data?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
        const parts = d.map((x: { msg?: string }) => x?.msg).filter(Boolean);
        if (parts.length) return parts.join(' ');
    }
    if (d && typeof d === 'object' && 'message' in d) {
        return String((d as { message?: string }).message);
    }
    return res?.status ? `Could not create account (error ${res.status}).` : 'Could not create account';
}

export default function SignupScreen() {
    const navigation = useNavigation<any>();
    const { signup, refreshUser } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [username, setUsername] = useState('');
    const [phoneNational, setPhoneNational] = useState('');
    const [phoneCountry, setPhoneCountry] = useState<PhoneCountry>(PHONE_COUNTRIES[0]);
    const [countryModalVisible, setCountryModalVisible] = useState(false);
    const [avatarUri, setAvatarUri] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [fieldErrors, setFieldErrors] = useState<Record<string, boolean>>({});
    const [fieldErrorMessages, setFieldErrorMessages] = useState<Record<string, string>>({});
    const [apiError, setApiError] = useState<string | null>(null);
    const [passwordMismatch, setPasswordMismatch] = useState(false);
    const [acceptedPolicies, setAcceptedPolicies] = useState(false);

    const fadeCard = useRef(new Animated.Value(0)).current;
    const slideCard = useRef(new Animated.Value(30)).current;

    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeCard, { toValue: 1, duration: 600, delay: 200, useNativeDriver: true }),
            Animated.timing(slideCard, { toValue: 0, duration: 600, delay: 200, useNativeDriver: true }),
        ]).start();
    }, []);

    const pickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.8 });
        if (!result.canceled) setAvatarUri(result.assets[0].uri);
    };

    const handleSignup = async () => {
        const err: Record<string, boolean> = {};
        if (!firstName.trim()) err.firstName = true;
        if (!lastName.trim()) err.lastName = true;
        if (!username.trim()) err.username = true;
        if (username.trim() && username.length < 3) err.username = true;
        if (username.trim() && !/^[a-zA-Z0-9_]+$/.test(username)) err.username = true;
        if (!email.trim()) err.email = true;
        if (!password) err.password = true;
        if (password && password.length < 8) err.password = true;
        if (!confirmPassword) err.confirmPassword = true;
        const pwdMismatch = !!(password && confirmPassword && password !== confirmPassword);
        if (pwdMismatch) { err.password = true; err.confirmPassword = true; }
        const nationalDigits = phoneNational.replace(/\D/g, '');
        if (!nationalDigits || nationalDigits.length < 7) err.phone = true;

        setFieldErrors(err);
        setApiError(null);
        setFieldErrorMessages({});
        setPasswordMismatch(pwdMismatch);
        if (Object.keys(err).length > 0) return;

        if (!acceptedPolicies) {
            setApiError('Please agree to the Terms of Service and Privacy Policy to create an account.');
            return;
        }

        setLoading(true);
        setApiError(null);
        setFieldErrorMessages({});
        try {
            const fullPhone =
                phoneCountry.dialCode + phoneNational.replace(/\D/g, '');
            await signup(email, password, firstName, lastName, username, fullPhone);
            if (avatarUri) {
                try {
                    await api.uploadAvatar(avatarUri);
                    await refreshUser();
                } catch {
                    Alert.alert('Note', 'Account created but profile picture could not be uploaded.');
                }
            }
        } catch (error: any) {
            const msg = signupErrorMessage(error);
            const lower = msg.toLowerCase();
            setFieldErrorMessages({});
            if (lower.includes('username') && lower.includes('taken')) {
                setFieldErrors((p) => ({ ...p, username: true }));
                setFieldErrorMessages((p) => ({ ...p, username: 'Username already taken' }));
            } else if (lower.includes('email') && lower.includes('registered')) {
                setFieldErrors((p) => ({ ...p, email: true }));
                setFieldErrorMessages((p) => ({ ...p, email: 'Email already registered' }));
            } else if (lower.includes('phone') && lower.includes('registered')) {
                setFieldErrors((p) => ({ ...p, phone: true }));
                setFieldErrorMessages((p) => ({ ...p, phone: 'Phone number already registered' }));
            } else {
                setApiError(msg);
            }
        }
        finally { setLoading(false); }
    };

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
                <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                    <Animated.View style={[styles.card, { opacity: fadeCard, transform: [{ translateY: slideCard }] }]}>
                        <Text style={styles.wordmark}>max</Text>
                        <Text style={styles.tagline}>Create your account</Text>

                        <View style={styles.form}>
                            <TouchableOpacity style={styles.avatarContainer} onPress={pickImage} activeOpacity={0.8}>
                                {avatarUri ? (
                                    <CachedImage uri={avatarUri} style={styles.avatar} />
                                ) : (
                                    <View style={styles.avatarPlaceholder}>
                                        <Ionicons name="camera-outline" size={24} color={colors.textMuted} />
                                    </View>
                                )}
                            </TouchableOpacity>

                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.firstName && styles.labelError]}>FIRST NAME</Text>
                                <TextInput style={[styles.input, fieldErrors.firstName && styles.inputError]} placeholder="John" placeholderTextColor={colors.textMuted} value={firstName} onChangeText={(t) => { setFirstName(t); setFieldErrors((p) => ({ ...p, firstName: false })); setApiError(null); }} autoCapitalize="words" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.lastName && styles.labelError]}>LAST NAME</Text>
                                <TextInput style={[styles.input, fieldErrors.lastName && styles.inputError]} placeholder="Doe" placeholderTextColor={colors.textMuted} value={lastName} onChangeText={(t) => { setLastName(t); setFieldErrors((p) => ({ ...p, lastName: false })); setApiError(null); }} autoCapitalize="words" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.username && styles.labelError]}>USERNAME</Text>
                                <TextInput style={[styles.input, fieldErrors.username && styles.inputError]} placeholder="johndoe" placeholderTextColor={colors.textMuted} value={username} onChangeText={(t) => { setUsername(t); setFieldErrors((p) => ({ ...p, username: false })); setFieldErrorMessages((p) => ({ ...p, username: '' })); setApiError(null); }} autoCapitalize="none" />
                                {fieldErrorMessages.username ? <Text style={styles.helperError}>{fieldErrorMessages.username}</Text> : null}
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.email && styles.labelError]}>EMAIL</Text>
                                <TextInput style={[styles.input, fieldErrors.email && styles.inputError]} placeholder="you@example.com" placeholderTextColor={colors.textMuted} value={email} onChangeText={(t) => { setEmail(t); setFieldErrors((p) => ({ ...p, email: false })); setFieldErrorMessages((p) => ({ ...p, email: '' })); setApiError(null); }} keyboardType="email-address" autoCapitalize="none" />
                                {fieldErrorMessages.email ? <Text style={styles.helperError}>{fieldErrorMessages.email}</Text> : null}
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.password && styles.labelError]}>PASSWORD</Text>
                                <View style={[styles.passwordRow, fieldErrors.password && styles.inputError]}>
                                    <TextInput style={[styles.input, styles.passwordInput]} placeholder="Min. 8 characters" placeholderTextColor={colors.textMuted} value={password} onChangeText={(t) => { setPassword(t); setFieldErrors((p) => ({ ...p, password: false, confirmPassword: false })); setPasswordMismatch(false); setApiError(null); }} secureTextEntry={!showPassword} />
                                    <TouchableOpacity style={styles.eyeButton} onPress={() => setShowPassword((p) => !p)} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                                        <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={22} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.confirmPassword && styles.labelError]}>CONFIRM PASSWORD</Text>
                                <View style={[styles.passwordRow, fieldErrors.confirmPassword && styles.inputError]}>
                                    <TextInput style={[styles.input, styles.passwordInput]} placeholder="Re-enter password" placeholderTextColor={colors.textMuted} value={confirmPassword} onChangeText={(t) => { setConfirmPassword(t); setFieldErrors((p) => ({ ...p, confirmPassword: false, password: false })); setPasswordMismatch(false); setApiError(null); }} secureTextEntry={!showConfirmPassword} />
                                    <TouchableOpacity style={styles.eyeButton} onPress={() => setShowConfirmPassword((p) => !p)} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                                        <Ionicons name={showConfirmPassword ? 'eye-off-outline' : 'eye-outline'} size={22} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                                {passwordMismatch && <Text style={styles.helperError}>Passwords don&apos;t match</Text>}
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.phone && styles.labelError]}>PHONE NUMBER</Text>
                                <View style={[styles.phoneRow, fieldErrors.phone && styles.inputError]}>
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
                                        placeholder="555 123 4567"
                                        placeholderTextColor={colors.textMuted}
                                        value={phoneNational}
                                        onChangeText={(t) => {
                                            setPhoneNational(t);
                                            setFieldErrors((p) => ({ ...p, phone: false }));
                                            setApiError(null);
                                        }}
                                        keyboardType="phone-pad"
                                    />
                                </View>
                                {fieldErrorMessages.phone ? (
                                    <Text style={styles.helperError}>{fieldErrorMessages.phone}</Text>
                                ) : (
                                    <Text style={styles.phoneHint}>Used for SMS coaching and account access.</Text>
                                )}
                            </View>

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
                                            <TouchableOpacity onPress={() => setCountryModalVisible(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
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
                                                        item.dialCode === phoneCountry.dialCode && item.name === phoneCountry.name && styles.countryRowSelected,
                                                    ]}
                                                    onPress={() => {
                                                        setPhoneCountry(item);
                                                        setCountryModalVisible(false);
                                                        setFieldErrors((p) => ({ ...p, phone: false }));
                                                        setFieldErrorMessages((p) => ({ ...p, phone: '' }));
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

                            <View style={styles.policyRow}>
                                <TouchableOpacity
                                    onPress={() => {
                                        setAcceptedPolicies((v) => !v);
                                        setApiError(null);
                                    }}
                                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                                    accessibilityRole="checkbox"
                                    accessibilityState={{ checked: acceptedPolicies }}
                                    accessibilityLabel="Agree to Terms of Service and Privacy Policy"
                                >
                                    <Ionicons
                                        name={acceptedPolicies ? 'checkbox' : 'square-outline'}
                                        size={22}
                                        color={acceptedPolicies ? colors.foreground : colors.textMuted}
                                        style={styles.policyCheckIcon}
                                    />
                                </TouchableOpacity>
                                <Text style={styles.policyText}>
                                    I agree to the{' '}
                                    <Text
                                        style={styles.policyLink}
                                        onPress={() => navigation.navigate('LegalDocument', { document: 'terms' })}
                                    >
                                        Terms of Service
                                    </Text>
                                    {' '}and{' '}
                                    <Text
                                        style={styles.policyLink}
                                        onPress={() => navigation.navigate('LegalDocument', { document: 'privacy' })}
                                    >
                                        Privacy Policy
                                    </Text>
                                    .
                                </Text>
                            </View>

                            {apiError && (
                                <View style={styles.apiErrorBox}>
                                    <Ionicons name="alert-circle-outline" size={18} color="#ef4444" />
                                    <Text style={styles.apiErrorText}>{apiError}</Text>
                                </View>
                            )}

                            <TouchableOpacity style={[styles.button, loading && styles.buttonDisabled]} onPress={handleSignup} disabled={loading} activeOpacity={0.7}>
                                <Text style={styles.buttonText}>{loading ? 'Creating Account...' : 'Create Account'}</Text>
                            </TouchableOpacity>
                        </View>

                        <TouchableOpacity onPress={() => navigation.navigate('Login')} activeOpacity={0.6} style={styles.linkContainer}>
                            <Text style={styles.linkText}>Already have an account? <Text style={styles.linkBold}>Sign In</Text></Text>
                        </TouchableOpacity>
                    </Animated.View>
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    keyboardView: { flex: 1 },
    scroll: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: spacing.xl, paddingVertical: spacing.xxl },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius.xl,
        padding: spacing.xl,
        borderWidth: 1,
        borderColor: colors.border,
    },
    wordmark: {
        fontFamily: fonts.serif,
        fontSize: 48,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -1.5,
        textAlign: 'center',
        marginBottom: spacing.xs,
    },
    tagline: { fontSize: 13, color: colors.textMuted, textAlign: 'center', marginBottom: spacing.xl, letterSpacing: 0.5 },
    form: { gap: spacing.md + 4 },
    avatarContainer: { alignSelf: 'center', marginBottom: spacing.md },
    avatar: { width: 76, height: 76, borderRadius: 38, borderWidth: 1, borderColor: colors.border },
    avatarPlaceholder: {
        width: 76, height: 76, borderRadius: 38,
        backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center',
        borderWidth: 1, borderColor: colors.border, borderStyle: 'dashed',
    },
    inputGroup: { gap: spacing.xs + 2 },
    label: { ...typography.label, marginLeft: 2 },
    input: {
        backgroundColor: colors.surface, borderRadius: borderRadius.sm,
        paddingVertical: 14, paddingHorizontal: spacing.md,
        color: colors.textPrimary, fontSize: 15,
        borderWidth: 1, borderColor: colors.borderLight,
    },
    passwordRow: {
        flexDirection: 'row', alignItems: 'center',
        backgroundColor: colors.surface, borderRadius: borderRadius.sm,
        borderWidth: 1, borderColor: colors.borderLight,
    },
    passwordInput: { flex: 1, backgroundColor: 'transparent', paddingRight: 44, borderWidth: 0 },
    eyeButton: { position: 'absolute', right: 12, padding: 4 },
    inputError: { borderWidth: 1, borderColor: colors.error },
    labelError: { color: colors.error },
    helperError: { fontSize: 12, color: colors.error, marginTop: 4, marginLeft: 2 },
    apiErrorBox: {
        backgroundColor: 'rgba(139, 58, 58, 0.06)',
        padding: spacing.md,
        borderRadius: borderRadius.sm,
        borderWidth: 1,
        borderColor: 'rgba(139, 58, 58, 0.15)',
    },
    apiErrorText: { fontSize: 13, color: colors.error, fontWeight: '400' },
    textArea: { minHeight: 64, textAlignVertical: 'top' },
    button: {
        backgroundColor: colors.foreground, borderRadius: borderRadius.sm,
        paddingVertical: 14, alignItems: 'center', marginTop: spacing.sm,
    },
    buttonDisabled: { opacity: 0.4 },
    buttonText: { ...typography.button },
    linkContainer: { marginTop: spacing.xl, alignItems: 'center' },
    linkText: { fontSize: 13, color: colors.textMuted },
    linkBold: { color: colors.foreground, fontWeight: '500' },
    policyRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        gap: spacing.sm,
        marginTop: spacing.sm,
        paddingVertical: spacing.xs,
    },
    policyCheckIcon: { marginTop: 2 },
    policyText: {
        flex: 1,
        fontSize: 12,
        color: colors.textSecondary,
        lineHeight: 18,
    },
    policyLink: {
        color: colors.foreground,
        fontWeight: '500',
        textDecorationLine: 'underline',
        textDecorationColor: colors.foreground,
    },
    phoneRow: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: colors.surface,
        borderRadius: borderRadius.sm,
        overflow: 'hidden',
        borderWidth: 1,
        borderColor: colors.borderLight,
    },
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
    countryCodeText: {
        fontSize: 15,
        fontWeight: '500',
        color: colors.textPrimary,
        flexShrink: 1,
    },
    phoneNationalInput: {
        flex: 1,
        paddingVertical: 14,
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
        borderBottomWidth: 1,
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
