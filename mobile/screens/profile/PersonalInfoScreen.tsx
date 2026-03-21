import React, { useState, useMemo } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  TextInput,
  Alert,
  KeyboardAvoidingView,
  Platform,
  useWindowDimensions,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const USERNAME_COOLDOWN_MS = 14 * 24 * 60 * 60 * 1000;

export default function PersonalInfoScreen() {
  const navigation = useNavigation<any>();
  const { width } = useWindowDimensions();
  const isWide = width > 600;
  const { user, refreshUser } = useAuth();

  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [lastName, setLastName] = useState(user?.last_name || '');
  const [username, setUsername] = useState(user?.username || '');
  const [saving, setSaving] = useState(false);

  const usernameCooldown = useMemo(() => {
    const last = user?.last_username_change;
    if (!last) return null;
    const end = new Date(last).getTime() + USERNAME_COOLDOWN_MS;
    const now = Date.now();
    if (now >= end) return null;
    const daysLeft = Math.ceil((end - now) / (24 * 60 * 60 * 1000));
    return daysLeft;
  }, [user?.last_username_change]);

  const usernameChanged = (username || '').toLowerCase() !== (user?.username || '').toLowerCase();
  const usernameLocked = usernameChanged && usernameCooldown !== null;

  const hasChanges =
    firstName.trim() !== (user?.first_name || '') ||
    lastName.trim() !== (user?.last_name || '') ||
    usernameChanged;

  const performSave = async () => {
    const trimmedUsername = username.trim();
    setSaving(true);
    try {
      const updates: Record<string, string | null> = {};
      if (firstName.trim() !== (user?.first_name || '')) updates.first_name = firstName.trim() || null;
      if (lastName.trim() !== (user?.last_name || '')) updates.last_name = lastName.trim() || null;
      if (usernameChanged) updates.username = trimmedUsername || null;

      await api.updateAccount(updates);
      await refreshUser();
      Alert.alert('Saved', 'Personal info updated.');
      navigation.goBack();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Could not save. Try again.';
      Alert.alert('Error', typeof msg === 'string' ? msg : 'Could not save. Try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleSave = () => {
    if (!hasChanges) return;

    if (usernameLocked) {
      Alert.alert(
        'Username locked',
        `You can change your username again in ${usernameCooldown} day${usernameCooldown !== 1 ? 's' : ''}.`
      );
      return;
    }

    const trimmedUsername = username.trim();
    if (usernameChanged && trimmedUsername) {
      if (trimmedUsername.length < 3) {
        Alert.alert('Error', 'Username must be at least 3 characters');
        return;
      }
      if (!/^[a-zA-Z0-9_]+$/.test(trimmedUsername)) {
        Alert.alert('Error', 'Username can only contain letters, numbers, and underscores');
        return;
      }
    }

    if (usernameChanged) {
      const nextName = trimmedUsername || '(remove username)';
      Alert.alert(
        'Change username?',
        `You're about to set your username to "${nextName}". You can only change your username once every 2 weeks after this — make sure it's what you want.`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Yes, save',
            style: 'default',
            onPress: () => {
              void performSave();
            },
          },
        ]
      );
      return;
    }

    void performSave();
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Edit personal info</Text>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView
          contentContainerStyle={[styles.content, isWide && styles.contentWide]}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.inputLabel}>FIRST NAME</Text>
          <TextInput
            style={styles.input}
            value={firstName}
            onChangeText={setFirstName}
            placeholder="First name"
            placeholderTextColor={colors.textMuted}
            autoCapitalize="words"
          />

          <Text style={styles.inputLabel}>LAST NAME</Text>
          <TextInput
            style={styles.input}
            value={lastName}
            onChangeText={setLastName}
            placeholder="Last name"
            placeholderTextColor={colors.textMuted}
            autoCapitalize="words"
          />

          <Text style={styles.inputLabel}>USERNAME</Text>
          <TextInput
            style={[styles.input, usernameLocked && styles.inputDisabled]}
            value={username}
            onChangeText={setUsername}
            placeholder="username"
            placeholderTextColor={colors.textMuted}
            autoCapitalize="none"
            autoCorrect={false}
          />
          {usernameCooldown !== null && (
            <Text style={styles.cooldownHint}>
              Username can be changed again in {usernameCooldown} day{usernameCooldown !== 1 ? 's' : ''}
            </Text>
          )}

          <Text style={styles.inputLabel}>EMAIL (Cannot be changed)</Text>
          <TextInput
            style={[styles.input, styles.inputDisabled]}
            value={user?.email || ''}
            editable={false}
            placeholderTextColor={colors.textMuted}
          />

          <Text style={styles.inputLabel}>PHONE (Cannot be changed)</Text>
          <TextInput
            style={[styles.input, styles.inputDisabled]}
            value={user?.phone_number || ''}
            editable={false}
            placeholderTextColor={colors.textMuted}
            placeholder="—"
          />

          <View style={{ height: 100 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.saveBtn, (!hasChanges || saving) && { opacity: 0.5 }]}
          onPress={handleSave}
          disabled={!hasChanges || saving}
          activeOpacity={0.7}
        >
          <Text style={styles.saveBtnText}>{saving ? 'Saving...' : 'Save Changes'}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 60,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  headerTitle: { ...typography.h3, color: colors.foreground },
  backButton: { padding: 4 },
  content: { padding: spacing.xl },
  contentWide: {
    maxWidth: 560,
    alignSelf: 'center',
    width: '100%',
    paddingHorizontal: spacing.xxl,
  },
  inputLabel: {
    ...typography.label,
    color: colors.textMuted,
    marginBottom: spacing.sm,
    marginTop: spacing.lg,
    marginLeft: 2,
  },
  input: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    padding: spacing.lg,
    color: colors.foreground,
    fontSize: 16,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  inputDisabled: {
    opacity: 0.6,
    backgroundColor: colors.card,
  },
  cooldownHint: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 6,
    marginLeft: 2,
  },
  footer: {
    padding: spacing.xl,
    paddingBottom: Platform.OS === 'ios' ? 40 : 24,
    backgroundColor: colors.background,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  saveBtn: {
    backgroundColor: colors.foreground,
    borderRadius: borderRadius.full,
    paddingVertical: 18,
    alignItems: 'center',
    ...shadows.md,
  },
  saveBtnText: { ...typography.button, color: colors.background },
});
