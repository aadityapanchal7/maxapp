import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert, KeyboardAvoidingView, Platform, Image, ScrollView, Animated } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

export default function SignupScreen() {
    const navigation = useNavigation<any>();
    const { signup } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [username, setUsername] = useState('');
    const [phone, setPhone] = useState('');
    const [avatarUri, setAvatarUri] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [fieldErrors, setFieldErrors] = useState<Record<string, boolean>>({});

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
        if (password && confirmPassword && password !== confirmPassword) { err.password = true; err.confirmPassword = true; }
        if (!phone.trim()) err.phone = true;

        setFieldErrors(err);
        if (Object.keys(err).length > 0) return;

        setLoading(true);
        try {
            await signup(email, password, firstName, lastName, username, phone || undefined);
            if (avatarUri) { try { await api.uploadAvatar(avatarUri); } catch { Alert.alert('Note', 'Account created but profile picture could not be uploaded.'); } }
        } catch (error: any) { Alert.alert('Signup Failed', error.response?.data?.detail || 'Could not create account'); }
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
                                    <Image source={{ uri: avatarUri }} style={styles.avatar} />
                                ) : (
                                    <View style={styles.avatarPlaceholder}>
                                        <Ionicons name="camera-outline" size={24} color={colors.textMuted} />
                                    </View>
                                )}
                            </TouchableOpacity>

                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.firstName && styles.labelError]}>FIRST NAME</Text>
                                <TextInput style={[styles.input, fieldErrors.firstName && styles.inputError]} placeholder="John" placeholderTextColor={colors.textMuted} value={firstName} onChangeText={(t) => { setFirstName(t); setFieldErrors((p) => ({ ...p, firstName: false })); }} autoCapitalize="words" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.lastName && styles.labelError]}>LAST NAME</Text>
                                <TextInput style={[styles.input, fieldErrors.lastName && styles.inputError]} placeholder="Doe" placeholderTextColor={colors.textMuted} value={lastName} onChangeText={(t) => { setLastName(t); setFieldErrors((p) => ({ ...p, lastName: false })); }} autoCapitalize="words" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.username && styles.labelError]}>USERNAME</Text>
                                <TextInput style={[styles.input, fieldErrors.username && styles.inputError]} placeholder="johndoe" placeholderTextColor={colors.textMuted} value={username} onChangeText={(t) => { setUsername(t); setFieldErrors((p) => ({ ...p, username: false })); }} autoCapitalize="none" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.email && styles.labelError]}>EMAIL</Text>
                                <TextInput style={[styles.input, fieldErrors.email && styles.inputError]} placeholder="you@example.com" placeholderTextColor={colors.textMuted} value={email} onChangeText={(t) => { setEmail(t); setFieldErrors((p) => ({ ...p, email: false })); }} keyboardType="email-address" autoCapitalize="none" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.password && styles.labelError]}>PASSWORD</Text>
                                <View style={[styles.passwordRow, fieldErrors.password && styles.inputError]}>
                                    <TextInput style={[styles.input, styles.passwordInput]} placeholder="Min. 8 characters" placeholderTextColor={colors.textMuted} value={password} onChangeText={(t) => { setPassword(t); setFieldErrors((p) => ({ ...p, password: false, confirmPassword: false })); }} secureTextEntry={!showPassword} />
                                    <TouchableOpacity style={styles.eyeButton} onPress={() => setShowPassword((p) => !p)} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                                        <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={22} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.confirmPassword && styles.labelError]}>CONFIRM PASSWORD</Text>
                                <View style={[styles.passwordRow, fieldErrors.confirmPassword && styles.inputError]}>
                                    <TextInput style={[styles.input, styles.passwordInput]} placeholder="Re-enter password" placeholderTextColor={colors.textMuted} value={confirmPassword} onChangeText={(t) => { setConfirmPassword(t); setFieldErrors((p) => ({ ...p, confirmPassword: false, password: false })); }} secureTextEntry={!showConfirmPassword} />
                                    <TouchableOpacity style={styles.eyeButton} onPress={() => setShowConfirmPassword((p) => !p)} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                                        <Ionicons name={showConfirmPassword ? 'eye-off-outline' : 'eye-outline'} size={22} color={colors.textMuted} />
                                    </TouchableOpacity>
                                </View>
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={[styles.label, fieldErrors.phone && styles.labelError]}>WHATSAPP · Required</Text>
                                <TextInput style={[styles.input, fieldErrors.phone && styles.inputError]} placeholder="+91 98765 43210" placeholderTextColor={colors.textMuted} value={phone} onChangeText={(t) => { setPhone(t); setFieldErrors((p) => ({ ...p, phone: false })); }} keyboardType="phone-pad" />
                            </View>

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
    scroll: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.xxl },
    card: {
        backgroundColor: colors.card,
        borderRadius: borderRadius['2xl'],
        padding: spacing.xl,
        ...shadows.xl,
    },
    wordmark: { fontSize: 40, fontWeight: '300', color: colors.foreground, letterSpacing: -2, textAlign: 'center', marginBottom: spacing.xs },
    tagline: { fontSize: 14, color: colors.textSecondary, textAlign: 'center', marginBottom: spacing.xl, letterSpacing: 0.2 },
    form: { gap: spacing.md },
    avatarContainer: { alignSelf: 'center', marginBottom: spacing.sm },
    avatar: { width: 80, height: 80, borderRadius: 40, borderWidth: 1, borderColor: colors.border },
    avatarPlaceholder: {
        width: 80, height: 80, borderRadius: 40,
        backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center',
        borderWidth: 1, borderColor: colors.border, borderStyle: 'dashed',
    },
    inputGroup: { gap: spacing.xs },
    label: { ...typography.label, marginLeft: 2 },
    input: {
        backgroundColor: colors.surface, borderRadius: borderRadius.md,
        paddingVertical: 15, paddingHorizontal: spacing.md,
        color: colors.textPrimary, fontSize: 15,
    },
    passwordRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: borderRadius.md },
    passwordInput: { flex: 1, backgroundColor: 'transparent', paddingRight: 44 },
    eyeButton: { position: 'absolute', right: 12, padding: 4 },
    inputError: { borderWidth: 1, borderColor: '#ef4444' },
    labelError: { color: '#ef4444' },
    textArea: { minHeight: 64, textAlignVertical: 'top' },
    button: {
        backgroundColor: colors.foreground, borderRadius: borderRadius.full,
        paddingVertical: 16, alignItems: 'center', marginTop: spacing.md,
        ...shadows.md,
    },
    buttonDisabled: { opacity: 0.5 },
    buttonText: { ...typography.button },
    linkContainer: { marginTop: spacing.xl, alignItems: 'center' },
    linkText: { fontSize: 13, color: colors.textSecondary },
    linkBold: { color: colors.foreground, fontWeight: '600' },
});
