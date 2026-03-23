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
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function LoginScreen() {
    const navigation = useNavigation<any>();
    const { login } = useAuth();
    const [identifier, setIdentifier] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [apiError, setApiError] = useState<string | null>(null);

    const fadeCard = useRef(new Animated.Value(0)).current;
    const slideCard = useRef(new Animated.Value(30)).current;
    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeCard, { toValue: 1, duration: 600, delay: 200, useNativeDriver: true }),
            Animated.timing(slideCard, { toValue: 0, duration: 600, delay: 200, useNativeDriver: true }),
        ]).start();
    }, []);

    const handleLogin = async () => {
        if (!identifier.trim() || !password) {
            setApiError('Please fill in all fields');
            return;
        }
        setLoading(true);
        setApiError(null);
        try {
            await login(identifier.trim(), password);
        } catch (error: any) {
            const msg = error.response?.data?.detail || 'Invalid credentials';
            setApiError(typeof msg === 'string' ? msg : 'Invalid credentials');
        } finally {
            setLoading(false);
        }
    };

    return (
        <View style={styles.safe}>
            <KeyboardAvoidingView
                style={styles.keyboardView}
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            >
                <Animated.View style={[styles.card, { opacity: fadeCard, transform: [{ translateY: slideCard }] }]}>
                    <Text style={styles.wordmark}>max</Text>
                    <Text style={styles.tagline}>Your lookmaxxing journey</Text>

                    <View style={styles.form}>
                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>EMAIL, USERNAME, OR PHONE</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="you@example.com"
                                placeholderTextColor={colors.textMuted}
                                value={identifier}
                                onChangeText={(t) => {
                                    setIdentifier(t);
                                    setApiError(null);
                                }}
                                keyboardType="default"
                                autoCapitalize="none"
                                autoCorrect={false}
                            />
                        </View>
                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>PASSWORD</Text>
                            <View style={styles.passwordRow}>
                                <TextInput
                                    style={styles.passwordInput}
                                    placeholder="Enter your password"
                                    placeholderTextColor={colors.textMuted}
                                    value={password}
                                    onChangeText={(t) => {
                                        setPassword(t);
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
                                    accessibilityRole="button"
                                    accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
                                >
                                    <Ionicons
                                        name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                                        size={22}
                                        color={colors.textMuted}
                                    />
                                </TouchableOpacity>
                            </View>
                        </View>

                        {apiError && (
                            <View style={styles.apiErrorBox}>
                                <Ionicons name="alert-circle-outline" size={18} color="#ef4444" />
                                <Text style={styles.apiErrorText}>{apiError}</Text>
                            </View>
                        )}

                        <TouchableOpacity
                            style={[styles.button, loading && styles.buttonDisabled]}
                            onPress={handleLogin}
                            disabled={loading}
                            activeOpacity={0.7}
                        >
                            <Text style={styles.buttonText}>{loading ? 'Signing in...' : 'Sign In'}</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                            onPress={() => navigation.navigate('ForgotPassword')}
                            activeOpacity={0.6}
                            style={styles.forgotLink}
                        >
                            <Text style={styles.forgotText}>Forgot password?</Text>
                        </TouchableOpacity>
                    </View>

                    <TouchableOpacity onPress={() => navigation.navigate('Signup')} activeOpacity={0.6} style={styles.linkContainer}>
                        <Text style={styles.linkText}>
                            Don&apos;t have an account? <Text style={styles.linkBold}>Create one</Text>
                        </Text>
                    </TouchableOpacity>

                    <TouchableOpacity onPress={() => navigation.navigate('LegalAndSafety')} activeOpacity={0.6} style={styles.legalLink}>
                        <Text style={styles.legalLinkText}>Privacy, support & safety</Text>
                    </TouchableOpacity>
                </Animated.View>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    safe: {
        flex: 1,
        backgroundColor: colors.background,
    },
    keyboardView: {
        flex: 1,
        justifyContent: 'center',
        paddingHorizontal: spacing.lg,
        backgroundColor: colors.background,
    },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        ...shadows.xl,
    },
    wordmark: {
        fontSize: 44,
        fontWeight: '300',
        color: colors.foreground,
        letterSpacing: -2,
        textAlign: 'center',
        marginBottom: spacing.xs,
    },
    tagline: {
        fontSize: 14,
        color: colors.textSecondary,
        textAlign: 'center',
        marginBottom: spacing.xxl,
        letterSpacing: 0.2,
    },
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
    forgotLink: { marginTop: spacing.md, alignItems: 'center' },
    forgotText: { fontSize: 14, color: colors.textSecondary, fontWeight: '500' },
    linkContainer: { marginTop: spacing.xl, alignItems: 'center' },
    linkText: { fontSize: 13, color: colors.textSecondary },
    linkBold: { color: colors.foreground, fontWeight: '600' },
    legalLink: { marginTop: spacing.md, alignItems: 'center', paddingVertical: spacing.sm },
    legalLinkText: { fontSize: 12, color: colors.textMuted, fontWeight: '500' },
});
