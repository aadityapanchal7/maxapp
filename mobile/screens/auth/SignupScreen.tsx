import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert, KeyboardAvoidingView, Platform, Image, ScrollView } from 'react-native';
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
    const [avatarUri, setAvatarUri] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const pickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ImagePicker.MediaTypeOptions.Images,
            allowsEditing: true,
            aspect: [1, 1],
            quality: 0.8,
        });
        if (!result.canceled) setAvatarUri(result.assets[0].uri);
    };

    const handleSignup = async () => {
        if (!email || !password || !confirmPassword) {
            Alert.alert('Error', 'Please fill in all required fields');
            return;
        }
        if (password !== confirmPassword) {
            Alert.alert('Error', 'Passwords do not match');
            return;
        }
        if (password.length < 8) {
            Alert.alert('Error', 'Password must be at least 8 characters');
            return;
        }
        setLoading(true);
        try {
            await signup(email, password, bio);
            if (avatarUri) {
                try { await api.uploadAvatar(avatarUri); }
                catch { Alert.alert('Note', 'Account created but profile picture could not be uploaded.'); }
            }
        } catch (error: any) {
            Alert.alert('Signup Failed', error.response?.data?.detail || 'Could not create account');
        } finally {
            setLoading(false);
        }
    };

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
                <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                    <View style={styles.content}>
                        <View style={styles.header}>
                            <Text style={styles.logo}>CANNON</Text>
                            <View style={styles.accentLine} />
                            <Text style={styles.subtitle}>Create Your Account</Text>
                        </View>

                        <View style={styles.form}>
                            <TouchableOpacity style={styles.avatarContainer} onPress={pickImage} activeOpacity={0.8}>
                                {avatarUri ? (
                                    <Image source={{ uri: avatarUri }} style={styles.avatar} />
                                ) : (
                                    <View style={styles.avatarPlaceholder}>
                                        <Ionicons name="camera-outline" size={28} color={colors.accent} />
                                        <Text style={styles.avatarText}>Photo</Text>
                                    </View>
                                )}
                                <View style={styles.editBadge}>
                                    <Ionicons name="add" size={14} color={colors.buttonText} />
                                </View>
                            </TouchableOpacity>

                            <View style={styles.inputContainer}>
                                <Text style={styles.label}>Email</Text>
                                <TextInput style={styles.input} placeholder="you@example.com" placeholderTextColor={colors.textMuted} value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
                            </View>
                            <View style={styles.inputContainer}>
                                <Text style={styles.label}>Password</Text>
                                <TextInput style={styles.input} placeholder="Min. 8 characters" placeholderTextColor={colors.textMuted} value={password} onChangeText={setPassword} secureTextEntry />
                            </View>
                            <View style={styles.inputContainer}>
                                <Text style={styles.label}>Confirm Password</Text>
                                <TextInput style={styles.input} placeholder="Re-enter password" placeholderTextColor={colors.textMuted} value={confirmPassword} onChangeText={setConfirmPassword} secureTextEntry />
                            </View>
                            <View style={styles.inputContainer}>
                                <Text style={styles.label}>Bio (Optional)</Text>
                                <TextInput style={[styles.input, styles.textArea]} placeholder="Tell us about yourself" placeholderTextColor={colors.textMuted} value={bio} onChangeText={setBio} multiline numberOfLines={2} maxLength={150} />
                            </View>

                            <TouchableOpacity
                                style={[styles.button, loading && styles.buttonDisabled]}
                                onPress={handleSignup}
                                disabled={loading}
                                activeOpacity={0.85}
                            >
                                <Text style={styles.buttonText}>{loading ? 'Creating Account...' : 'Create Account'}</Text>
                            </TouchableOpacity>
                        </View>

                        <TouchableOpacity onPress={() => navigation.navigate('Login')} activeOpacity={0.7}>
                            <Text style={styles.linkText}>
                                Already have an account?  <Text style={styles.linkHighlight}>Sign In</Text>
                            </Text>
                        </TouchableOpacity>
                    </View>
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    keyboardView: { flex: 1 },
    scroll: { flexGrow: 1, justifyContent: 'center' },
    content: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.xl, paddingVertical: spacing.xxl },
    header: { alignItems: 'center', marginBottom: spacing.xl },
    logo: { fontSize: 42, fontWeight: '700', color: colors.textPrimary, letterSpacing: 10 },
    accentLine: { width: 36, height: 3, backgroundColor: colors.accent, borderRadius: 2, marginTop: spacing.md, marginBottom: spacing.md },
    subtitle: { ...typography.bodySmall, textAlign: 'center', letterSpacing: 0.5 },
    form: { gap: spacing.md },
    inputContainer: { gap: spacing.xs },
    label: { ...typography.caption, textTransform: 'uppercase', letterSpacing: 1.2, marginLeft: spacing.xs, color: colors.textSecondary },
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
    textArea: { minHeight: 64, textAlignVertical: 'top' },
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
    linkText: { ...typography.bodySmall, textAlign: 'center', marginTop: spacing.xl },
    linkHighlight: { color: colors.accent, fontWeight: '600' },
    avatarContainer: { alignSelf: 'center', marginBottom: spacing.sm },
    avatar: { width: 96, height: 96, borderRadius: 48, borderWidth: 2, borderColor: colors.border },
    avatarPlaceholder: {
        width: 96, height: 96, borderRadius: 48,
        backgroundColor: colors.accentMuted,
        justifyContent: 'center', alignItems: 'center',
        borderWidth: 1.5, borderColor: colors.border, borderStyle: 'dashed',
    },
    avatarText: { ...typography.caption, marginTop: 2, color: colors.accent },
    editBadge: {
        position: 'absolute', bottom: 2, right: 2,
        backgroundColor: colors.accent, borderRadius: 12,
        width: 24, height: 24, justifyContent: 'center', alignItems: 'center',
        borderWidth: 2, borderColor: colors.background,
    },
});
