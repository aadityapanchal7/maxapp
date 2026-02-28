import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert, KeyboardAvoidingView, Platform } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function LoginScreen() {
    const navigation = useNavigation<any>();
    const { login } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);

    const handleLogin = async () => {
        if (!email || !password) {
            Alert.alert('Error', 'Please fill in all fields');
            return;
        }
        setLoading(true);
        try {
            await login(email, password);
        } catch (error: any) {
            Alert.alert('Login Failed', error.response?.data?.detail || 'Invalid credentials');
        } finally {
            setLoading(false);
        }
    };

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
                <View style={styles.content}>
                    <View style={styles.header}>
                        <Text style={styles.logo}>CANNON</Text>
                        <View style={styles.accentLine} />
                        <Text style={styles.subtitle}>Your Lookmaxxing Journey Starts Here</Text>
                    </View>

                    <View style={styles.form}>
                        <View style={styles.inputContainer}>
                            <Text style={styles.label}>Email</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="you@example.com"
                                placeholderTextColor={colors.textMuted}
                                value={email}
                                onChangeText={setEmail}
                                keyboardType="email-address"
                                autoCapitalize="none"
                            />
                        </View>
                        <View style={styles.inputContainer}>
                            <Text style={styles.label}>Password</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="Enter your password"
                                placeholderTextColor={colors.textMuted}
                                value={password}
                                onChangeText={setPassword}
                                secureTextEntry
                            />
                        </View>

                        <TouchableOpacity
                            style={[styles.button, loading && styles.buttonDisabled]}
                            onPress={handleLogin}
                            disabled={loading}
                            activeOpacity={0.85}
                        >
                            <Text style={styles.buttonText}>{loading ? 'Signing in...' : 'Sign In'}</Text>
                        </TouchableOpacity>
                    </View>

                    <TouchableOpacity onPress={() => navigation.navigate('Signup')} activeOpacity={0.7}>
                        <Text style={styles.linkText}>
                            New here?  <Text style={styles.linkHighlight}>Create an account</Text>
                        </Text>
                    </TouchableOpacity>
                </View>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    keyboardView: { flex: 1 },
    content: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.xl },
    header: { alignItems: 'center', marginBottom: spacing.xxl },
    logo: {
        fontSize: 42,
        fontWeight: '700',
        color: colors.textPrimary,
        letterSpacing: 10,
    },
    accentLine: {
        width: 36,
        height: 3,
        backgroundColor: colors.accent,
        borderRadius: 2,
        marginTop: spacing.md,
        marginBottom: spacing.md,
    },
    subtitle: {
        ...typography.bodySmall,
        textAlign: 'center',
        letterSpacing: 0.5,
    },
    form: { gap: spacing.md },
    inputContainer: { gap: spacing.xs },
    label: {
        ...typography.caption,
        textTransform: 'uppercase',
        letterSpacing: 1.2,
        marginLeft: spacing.xs,
        color: colors.textSecondary,
    },
    input: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        paddingVertical: 14,
        paddingHorizontal: spacing.md,
        color: colors.textPrimary,
        fontSize: 15,
        borderWidth: 1,
        borderColor: colors.border,
    },
    button: {
        backgroundColor: colors.primary,
        borderRadius: borderRadius.md,
        paddingVertical: 16,
        alignItems: 'center',
        marginTop: spacing.sm,
        ...shadows.md,
    },
    buttonDisabled: { opacity: 0.6 },
    buttonText: { ...typography.button },
    linkText: {
        ...typography.bodySmall,
        textAlign: 'center',
        marginTop: spacing.xl,
    },
    linkHighlight: { color: colors.accent, fontWeight: '600' },
});
