import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { HEIGHT_SCHEDULE_COMPONENTS } from '../../constants/heightScheduleComponents';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

function defaultSelection(): Record<string, boolean> {
  const m: Record<string, boolean> = {};
  HEIGHT_SCHEDULE_COMPONENTS.forEach((c) => {
    m[c.id] = true;
  });
  return m;
}

/** True if signup / global onboarding already has age, gender, and height (numbers or strings). */
function hasGlobalHeightProfile(ob: Record<string, unknown>): boolean {
  const age = ob.age;
  const ageNum = typeof age === 'number' ? age : parseInt(String(age ?? ''), 10);
  const hasAge = Number.isFinite(ageNum) && ageNum >= 8 && ageNum <= 100;
  const gender = String(ob.gender ?? ob.sex ?? '').trim();
  const h = ob.height;
  const hasHeight =
    h != null &&
    String(h).trim() !== '' &&
    String(h).trim() !== '0';
  return hasAge && gender.length > 0 && hasHeight;
}

export default function HeightScheduleComponentsScreen() {
  const navigation = useNavigation<any>();
  const [selected, setSelected] = useState<Record<string, boolean>>(defaultSelection);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [wakeTime, setWakeTime] = useState('07:00');
  const [sleepTime, setSleepTime] = useState('23:00');

  const loadProfile = useCallback(async () => {
    setLoading(true);
    try {
      const me = await api.getMe();
      const ob = me?.onboarding || {};
      const w = ob.wake_time || me?.schedule_preferences?.wake_time;
      const s = ob.sleep_time || me?.schedule_preferences?.sleep_time;
      if (w && typeof w === 'string') setWakeTime(w);
      if (s && typeof s === 'string') setSleepTime(s);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const toggle = (id: string, value: boolean) => {
    setSelected((prev) => ({ ...prev, [id]: value }));
  };

  const onCreate = async () => {
    const enabled = Object.entries(selected).filter(([, v]) => v);
    if (enabled.length === 0) {
      Alert.alert('Pick at least one', 'Turn on at least one part of the program to continue.');
      return;
    }
    try {
      const me = await api.getMe();
      const ob = (me?.onboarding || {}) as Record<string, unknown>;
      if (!hasGlobalHeightProfile(ob)) {
        Alert.alert(
          'Profile incomplete',
          'Add age, gender, and height in your profile or finish the heightmax chat so we can build your schedule.',
        );
        return;
      }
    } catch {
      /* continue; API will error if invalid */
    }

    setSaving(true);
    try {
      const res = await api.generateMaxxSchedule(
        'heightmax',
        wakeTime,
        sleepTime,
        false,
        7,
        selected,
      );
      const schedule = res?.schedule;
      if (schedule?.id) {
        navigation.navigate('Schedule', { scheduleId: schedule.id });
      } else {
        Alert.alert('Done', 'Your height schedule was created. Open it from the Heightmax module.');
        navigation.goBack();
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Could not create schedule';
      Alert.alert('Error', String(msg));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color={colors.foreground} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backButton}
          hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
        >
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>height schedule</Text>
        <Text style={styles.headerSubtitle}>
          turn on the pieces you want in your plan. you can change this later by starting a new
          schedule.
        </Text>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {HEIGHT_SCHEDULE_COMPONENTS.map((item) => (
          <View key={item.id} style={styles.card}>
            <View style={styles.cardRow}>
              <View style={styles.cardTextWrap}>
                <Text style={styles.cardTitle}>{item.title}</Text>
                <Text style={styles.cardDesc}>{item.description}</Text>
              </View>
              <Switch
                value={selected[item.id] !== false}
                onValueChange={(v) => toggle(item.id, v)}
                trackColor={{ false: colors.border, true: colors.foreground + '55' }}
                thumbColor={selected[item.id] !== false ? colors.foreground : colors.textMuted}
              />
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={[styles.primaryBtn, saving && styles.primaryBtnDisabled]}
          onPress={onCreate}
          disabled={saving}
          activeOpacity={0.85}
        >
          {saving ? (
            <ActivityIndicator color={colors.buttonText} />
          ) : (
            <Text style={styles.primaryBtnText}>create schedule</Text>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  center: { justifyContent: 'center', alignItems: 'center' },
  header: {
    paddingTop: 56,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.card,
  },
  backButton: { marginBottom: spacing.sm },
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.foreground,
    letterSpacing: -0.3,
    marginBottom: 8,
  },
  headerSubtitle: { fontSize: 14, color: colors.textMuted, lineHeight: 20 },
  scroll: { flex: 1 },
  scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxxl },
  card: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    marginBottom: spacing.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    ...shadows.sm,
  },
  cardRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  cardTextWrap: { flex: 1, paddingRight: spacing.sm },
  cardTitle: { fontSize: 16, fontWeight: '600', color: colors.foreground, marginBottom: 6 },
  cardDesc: { fontSize: 13, color: colors.textMuted, lineHeight: 20 },
  footer: {
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.background,
  },
  primaryBtn: {
    backgroundColor: colors.foreground,
    paddingVertical: 16,
    borderRadius: borderRadius.xl,
    alignItems: 'center',
    ...shadows.md,
  },
  primaryBtnDisabled: { opacity: 0.6 },
  primaryBtnText: { fontSize: 16, fontWeight: '600', color: colors.buttonText },
});
