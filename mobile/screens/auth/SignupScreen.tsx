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
    const [bio, setBio] = useState('');
    const [phone, setPhone] = useState('');
    const [avatarUri, setAvatarUri] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const fadeCard = useRef(new Animated.Value(0)).current;
    const slideCard = useRef(new Animated.Value(30)).current;

    useEffect(() => {
        Animated.parallel([
            Animated.timing(fadeCard, { toValue: 1, duration: 600, delay: 200, useNativeDriver: true }),
            Animated.timing(slideCard, { toValue: 0, duration: 600, delay: 200, useNativeDriver: true }),
        ]).start();
    }, []);

    const pickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, aspect: [1, 1], quality: 0.8 });
        if (!result.canceled) setAvatarUri(result.assets[0].uri);
    };

    const handleSignup = async () => {
        if (!email || !password || !confirmPassword) { Alert.alert('Error', 'Please fill in all required fields'); return; }
        if (password !== confirmPassword) { Alert.alert('Error', 'Passwords do not match'); return; }
        if (password.length < 8) { Alert.alert('Error', 'Password must be at least 8 characters'); return; }
        setLoading(true);
        try {
            await signup(email, password, bio, phone || undefined);
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
                                <Text style={styles.label}>EMAIL</Text>
                                <TextInput style={styles.input} placeholder="you@example.com" placeholderTextColor={colors.textMuted} value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>PASSWORD</Text>
                                <TextInput style={styles.input} placeholder="Min. 8 characters" placeholderTextColor={colors.textMuted} value={password} onChangeText={setPassword} secureTextEntry />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>CONFIRM PASSWORD</Text>
                                <TextInput style={styles.input} placeholder="Re-enter password" placeholderTextColor={colors.textMuted} value={confirmPassword} onChangeText={setConfirmPassword} secureTextEntry />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>WHATSAPP (OPTIONAL)</Text>
                                <TextInput style={styles.input} placeholder="+91 98765 43210" placeholderTextColor={colors.textMuted} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
                            </View>
                            <View style={styles.inputGroup}>
                                <Text style={styles.label}>BIO (OPTIONAL)</Text>
                                <TextInput style={[styles.input, styles.textArea]} placeholder="Tell us about yourself" placeholderTextColor={colors.textMuted} value={bio} onChangeText={setBio} multiline numberOfLines={2} maxLength={150} />
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
