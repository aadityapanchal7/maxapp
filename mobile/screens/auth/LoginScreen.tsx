import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, Animated } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function LoginScreen() {
    const navigation = useNavigation<any>();
    const { login } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
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
        if (!email.trim() || !password) {
            setApiError('Please fill in all fields');
            return;
        }
        setLoading(true);
        setApiError(null);
        try { await login(email, password); }
        catch (error: any) {
            const msg = error.response?.data?.detail || 'Invalid credentials';
            setApiError(typeof msg === 'string' ? msg : 'Invalid credentials');
        }
        finally { setLoading(false); }
    };

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
                <Animated.View style={[styles.card, { opacity: fadeCard, transform: [{ translateY: slideCard }] }]}>
                    <Text style={styles.wordmark}>max</Text>
                    <Text style={styles.tagline}>Your lookmaxxing journey</Text>

                    <View style={styles.form}>
                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>EMAIL</Text>
                            <TextInput style={styles.input} placeholder="you@example.com" placeholderTextColor={colors.textMuted} value={email} onChangeText={(t) => { setEmail(t); setApiError(null); }} keyboardType="email-address" autoCapitalize="none" />
                        </View>
                        <View style={styles.inputGroup}>
                            <Text style={styles.label}>PASSWORD</Text>
                            <TextInput style={styles.input} placeholder="Enter your password" placeholderTextColor={colors.textMuted} value={password} onChangeText={(t) => { setPassword(t); setApiError(null); }} secureTextEntry />
                        </View>

                        {apiError && (
                            <View style={styles.apiErrorBox}>
                                <Ionicons name="alert-circle-outline" size={18} color="#ef4444" />
                                <Text style={styles.apiErrorText}>{apiError}</Text>
                            </View>
                        )}

                        <TouchableOpacity style={[styles.button, loading && styles.buttonDisabled]} onPress={handleLogin} disabled={loading} activeOpacity={0.7}>
                            <Text style={styles.buttonText}>{loading ? 'Signing in...' : 'Sign In'}</Text>
                        </TouchableOpacity>
                    </View>

                    <TouchableOpacity onPress={() => navigation.navigate('Signup')} activeOpacity={0.6} style={styles.linkContainer}>
                        <Text style={styles.linkText}>Don't have an account? <Text style={styles.linkBold}>Create one</Text></Text>
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
    linkContainer: { marginTop: spacing.xl, alignItems: 'center' },
    linkText: { fontSize: 13, color: colors.textSecondary },
    linkBold: { color: colors.foreground, fontWeight: '600' },
});
