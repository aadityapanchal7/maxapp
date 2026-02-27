/**
 * Signup Screen
 */

import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert, KeyboardAvoidingView, Platform, Image } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { colors, spacing, borderRadius, typography } from '../../theme/dark';

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

        if (!result.canceled) {
            setAvatarUri(result.assets[0].uri);
        }
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
            // 1. Signup (sends bio)
            await signup(email, password, bio);

            // 2. Upload Avatar (if selected)
            if (avatarUri) {
                try {
                    await api.uploadAvatar(avatarUri);
                } catch (uploadError) {
                    console.error('Avatar upload failed:', uploadError);
                    // Don't block signup success, just warn
                    Alert.alert('Warning', 'Account created but profile picture could not be uploaded.');
                }
            }
        } catch (error: any) {
            Alert.alert('Signup Failed', error.response?.data?.detail || 'Could not create account');
        } finally {
            setLoading(false);
        }
    };

    return (
        <LinearGradient colors={[colors.gradientStart, colors.gradientEnd]} style={styles.container}>
            <KeyboardAvoidingView style={styles.keyboardView} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
                <View style={styles.content}>
                    <Text style={styles.logo}>CANNON</Text>
                    <Text style={styles.subtitle}>Create Your Account</Text>

                    <View style={styles.form}>
                        {/* Avatar Picker */}
                        <TouchableOpacity style={styles.avatarContainer} onPress={pickImage}>
                            {avatarUri ? (
                                <Image source={{ uri: avatarUri }} style={styles.avatar} />
                            ) : (
                                <View style={styles.avatarPlaceholder}>
                                    <Ionicons name="camera" size={32} color="rgba(255,255,255,0.5)" />
                                    <Text style={styles.avatarText}>Add Photo</Text>
                                </View>
                            )}
                            <View style={styles.editBadge}>
                                <Ionicons name="pencil" size={12} color="#FFFFFF" />
                            </View>
                        </TouchableOpacity>

                        <TextInput
                            style={styles.input}
                            placeholder="Email"
                            placeholderTextColor="rgba(255,255,255,0.5)"
                            value={email}
                            onChangeText={setEmail}
                            keyboardType="email-address"
                            autoCapitalize="none"
                        />
                        <TextInput
                            style={styles.input}
                            placeholder="Password"
                            placeholderTextColor="rgba(255,255,255,0.5)"
                            value={password}
                            onChangeText={setPassword}
                            secureTextEntry
                        />
                        <TextInput
                            style={styles.input}
                            placeholder="Confirm Password"
                            placeholderTextColor="rgba(255,255,255,0.5)"
                            value={confirmPassword}
                            onChangeText={setConfirmPassword}
                            secureTextEntry
                        />
                        <TextInput
                            style={styles.input}
                            placeholder="Bio (Optional)"
                            placeholderTextColor="rgba(255,255,255,0.5)"
                            value={bio}
                            onChangeText={setBio}
                            multiline
                            numberOfLines={2}
                            maxLength={150}
                        />

                        <TouchableOpacity style={styles.button} onPress={handleSignup} disabled={loading}>
                            <Text style={styles.buttonText}>{loading ? 'Creating Account...' : 'Create Account'}</Text>
                        </TouchableOpacity>
                    </View>

                    <TouchableOpacity onPress={() => navigation.navigate('Login')}>
                        <Text style={styles.linkText}>
                            Already have an account? <Text style={styles.linkHighlight}>Login</Text>
                        </Text>
                    </TouchableOpacity>
                </View>
            </KeyboardAvoidingView>
        </LinearGradient>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1 },
    keyboardView: { flex: 1 },
    content: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.lg },
    logo: { fontSize: 48, fontFamily: 'Matter-Medium', fontWeight: '500', color: '#FFFFFF', textAlign: 'center', letterSpacing: 8 },
    subtitle: { ...typography.bodySmall, textAlign: 'center', marginTop: spacing.sm, marginBottom: spacing.xl, color: 'rgba(255,255,255,0.7)' },
    form: { gap: spacing.md },
    input: { backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: borderRadius.md, padding: spacing.md, color: '#FFFFFF', fontSize: 16, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
    button: { backgroundColor: '#FFFFFF', borderRadius: borderRadius.md, padding: spacing.md, alignItems: 'center', marginTop: spacing.sm },
    buttonText: { ...typography.button, color: '#000000' },
    linkText: { ...typography.bodySmall, textAlign: 'center', marginTop: spacing.xl, color: 'rgba(255,255,255,0.7)' },
    linkHighlight: { color: '#FFFFFF', fontWeight: '600' },
    avatarContainer: { alignSelf: 'center', marginBottom: spacing.md },
    avatar: { width: 100, height: 100, borderRadius: 50, borderWidth: 2, borderColor: 'rgba(255,255,255,0.3)' },
    avatarPlaceholder: { width: 100, height: 100, borderRadius: 50, backgroundColor: 'rgba(255,255,255,0.1)', justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: 'rgba(255,255,255,0.3)', borderStyle: 'dashed' },
    avatarText: { ...typography.caption, color: 'rgba(255,255,255,0.5)', marginTop: 4 },
    editBadge: { position: 'absolute', bottom: 0, right: 0, backgroundColor: '#000000', borderRadius: 12, width: 24, height: 24, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: '#FFFFFF' },
});

