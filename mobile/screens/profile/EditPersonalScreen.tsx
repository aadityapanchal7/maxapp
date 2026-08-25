import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  useWindowDimensions,
} from 'react-native'
import { Alert } from '../../components/InAppAlert';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { queryClient, queryKeys } from '../../lib/queryClient';
import { useAuth } from '../../context/AuthContext';
import OnairosConnectModal from '../../components/OnairosConnectModal';
import { useOnairosConfig } from '../../hooks/useOnairosConfig';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { maxHomeMaxxesForUser } from '../../utils/maxxLimits';
import {
  PRIORITY_LABELS,
  type PriorityKey,
  APPEARANCE_OPTIONS,
  SKIN_CONCERNS,
  SCREEN_TIME_BANDS,
  mapSkinConcernToType,
  mapTrainingToExperience,
  mapEquipmentToList,
  formatTime12h,
  hhmm,
  heavyScreenFromBand,
  inferScreenBand,
  normalizePriorityOrder,
  inferFitEquipmentFromOnboarding,
} from '../../constants/profileLifestyleQuestionnaire';
import { isHHMM, toMin } from '../../components/planner/plannerModel';

const ACTIVITY_LEVELS = [
  { id: 'sedentary', label: 'Sedentary', desc: 'Little to no exercise' },
  { id: 'light', label: 'Light', desc: '1-3 days/week' },
  { id: 'moderate', label: 'Moderate', desc: '3-5 days/week' },
  { id: 'active', label: 'Active', desc: '6-7 days/week' },
];

function hydrateFromOnboarding(ob: Record<string, any>) {
  // Mirrors the live onboarding flow — only the basics we ask there
  // (gender + age + body + the wake/sleep/get-ready anchors + priority).
  // The workout WINDOW and recurring commitments (work/school) now live in
  // the Day Planner, not here — work is just an obligation and the workout is
  // a range, so editing them as a scalar here would fork the planner's data.
  // Older fields like appearance_concerns / skin / hair / training are kept in
  // user.onboarding as-is on save (via {...base} spread) so downstream engines
  // that still depend on them keep working, but we don't surface those edits.
  // Get-ready is a [start,end] WINDOW now; read the start + width from it (the
  // canonical field), falling back to the legacy get_ready_time + minutes.
  const grWin = Array.isArray(ob.get_ready_window) ? ob.get_ready_window : null;
  const grStart = grWin && isHHMM(grWin[0]) ? (grWin[0] as string) : ((ob.get_ready_time as string) || null);
  const grMin =
    grWin && isHHMM(grWin[0]) && isHHMM(grWin[1])
      ? Math.max(5, toMin(grWin[1]) - toMin(grWin[0]))
      : typeof ob.get_ready_minutes === 'number' && ob.get_ready_minutes > 0
        ? ob.get_ready_minutes
        : 30;
  // Bedtime = the END of the wind-down window when present, else sleep_time.
  const wdWin = Array.isArray(ob.wind_down_window) ? ob.wind_down_window : null;
  const bedtime = wdWin && isHHMM(wdWin[1]) ? (wdWin[1] as string) : (ob.sleep_time || '23:00');
  return {
    priorityRanking: Array.isArray(ob.priority_ranking)
      ? [...ob.priority_ranking]
      : normalizePriorityOrder(ob.priority_order),
    wakeTime: ob.wake_time || '07:00',
    sleepTime: bedtime,
    // Precise day anchor — null means "auto" (coach derives from wake/sleep).
    getReadyTime: isHHMM(grStart) ? (grStart as string) : null,
    getReadyMinutes: grMin,
  };
}

const GET_READY_DURATIONS = [15, 30, 45, 60] as const;

type TimePickerKey = 'wake' | 'getReady' | 'sleep';

export default function EditPersonalScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { width } = useWindowDimensions();
  const isWide = width > 600;
  const { user, refreshUser } = useAuth();
  const { enabled: onairosEnabled } = useOnairosConfig();
  const [loading, setLoading] = useState(false);
  // Onairos modal — opens from the "external personalization" card.
  // Connecting refreshes user data; coaching_service picks up the new
  // traits on the next chat turn (no client-side cache to bust).
  const [onairosVisible, setOnairosVisible] = useState(false);


  const [unitSystem, setUnitSystem] = useState<'metric' | 'imperial'>((user?.onboarding?.unit_system as any) || 'imperial');
  const [selectedGoals, setSelectedGoals] = useState<string[]>(user?.onboarding?.goals || []);
  const [gender, setGender] = useState(user?.onboarding?.gender || '');
  const [age, setAge] = useState(user?.onboarding?.age?.toString() || '');

  const getInitialValues = () => {
    let h = '', hFt = '', hIn = '', w = '';
    const ob = user?.onboarding;
    if (ob) {
      if (unitSystem === 'imperial') {
        w = ob.weight ? Number(ob.weight).toFixed(1) : '';
        if (ob.height) {
          const totalInches = Number(ob.height);
          hFt = Math.floor(totalInches / 12).toString();
          hIn = Math.round(totalInches % 12).toString();
        }
      } else {
        h = ob.height?.toString() || '';
        w = ob.weight?.toString() || '';
      }
    }
    return { h, hFt, hIn, w };
  };

  const initial = getInitialValues();
  const [height, setHeight] = useState(initial.h);
  const [heightFt, setHeightFt] = useState(initial.hFt);
  const [heightIn, setHeightIn] = useState(initial.hIn);
  const [weight, setWeight] = useState(initial.w);

  const [activityLevel, setActivityLevel] = useState(user?.onboarding?.activity_level || 'moderate');

  const v2 = hydrateFromOnboarding((user?.onboarding || {}) as Record<string, any>);
  const [priorityRanking, setPriorityRanking] = useState<string[]>(v2.priorityRanking);
  const [wakeTime, setWakeTime] = useState(v2.wakeTime);
  const [sleepTime, setSleepTime] = useState(v2.sleepTime);
  const [getReadyTime, setGetReadyTime] = useState<string | null>(v2.getReadyTime);
  const [getReadyMinutes, setGetReadyMinutes] = useState<number>(v2.getReadyMinutes);

  const movePriority = useCallback((index: number, dir: -1 | 1) => {
    const j = index + dir;
    if (j < 0 || j >= priorityRanking.length) return;
    const next = [...priorityRanking];
    [next[index], next[j]] = [next[j], next[index]];
    setPriorityRanking(next);
  }, [priorityRanking]);

  useEffect(() => {
    if (!user?.onboarding) return;
    const ob = user.onboarding;
    setUnitSystem((ob.unit_system as any) || 'imperial');
    const maxG = maxHomeMaxxesForUser(user);
    const g = (ob.goals || []) as string[];
    setSelectedGoals(g.slice(0, maxG));
    setGender(ob.gender || '');
    setAge(ob.age?.toString() || '');
    setActivityLevel(ob.activity_level || 'moderate');

    const u = (ob.unit_system as any) || 'imperial';
    if (u === 'imperial') {
      if (ob.weight) setWeight(Number(ob.weight).toFixed(1));
      if (ob.height) {
        const totalInches = Number(ob.height);
        setHeightFt(Math.floor(totalInches / 12).toString());
        setHeightIn(Math.round(totalInches % 12).toString());
        setHeight('');
      }
    } else {
      setHeight(ob.height?.toString() || '');
      setWeight(ob.weight?.toString() || '');
      setHeightFt('');
      setHeightIn('');
    }

    const h = hydrateFromOnboarding(ob as Record<string, any>);
    setPriorityRanking(h.priorityRanking);
    setWakeTime(h.wakeTime);
    setSleepTime(h.sleepTime);
    setGetReadyTime(h.getReadyTime);
    setGetReadyMinutes(h.getReadyMinutes);
  }, [user]);

  const handleSave = async () => {
    setLoading(true);

    let finalHeight: number | undefined;
    let finalWeight: number | undefined;
    if (unitSystem === 'imperial') {
      const ft = parseInt(heightFt, 10) || 0;
      const inch = parseInt(heightIn, 10) || 0;
      if (ft > 0 || inch > 0) finalHeight = ft * 12 + inch;
      if (weight && parseFloat(weight) > 0) finalWeight = parseFloat(weight);
    } else {
      if (height && parseFloat(height) > 0) finalHeight = parseFloat(height);
      if (weight && parseFloat(weight) > 0) finalWeight = parseFloat(weight);
    }

    const base = { ...(user?.onboarding || {}) } as Record<string, any>;
    const tz =
      base.timezone ||
      (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC');


    // Spread `base` so any older onboarding keys (skin/hair/training/etc.)
    // saved by previous app versions persist for downstream services that
    // still reference them. We only OVERWRITE the keys this screen now
    // controls — gender/age/body + the schedule anchors the chatbot uses.
    const onboardingData: Record<string, any> = {
      ...base,
      completed: true,
      timezone: tz,
      unit_system: unitSystem,
      priority_ranking: [...priorityRanking],
      wake_time: hhmm(wakeTime),
      // Bedtime is edited here as a single exact time. Write the window fields
      // too (an exact bedtime = a collapsed wind-down window) so this clears any
      // wind-down RANGE the planner stored — otherwise the canonical window
      // would silently override the bedtime the user just set here.
      sleep_time: hhmm(sleepTime),
      sleep_window: [hhmm(sleepTime), hhmm(sleepTime)],
      wind_down_window: null,
      // Get-ready window is canonical; keep the legacy scalar + duration in sync.
      // Writing the window here is what makes a get-ready edit actually take
      // effect (hydrate trusts get_ready_window first).
      get_ready_time: getReadyTime ? hhmm(getReadyTime) : null,
      get_ready_minutes: getReadyMinutes,
      get_ready_window: getReadyTime
        ? [hhmm(getReadyTime), shiftTime(hhmm(getReadyTime), getReadyMinutes)]
        : null,
      // The workout WINDOW and recurring commitments (work/school) are owned by
      // the Day Planner now — work is just an obligation, the workout is a range.
      // We deliberately DON'T write preferred_workout_time / preferred_workout_window
      // / work_schedule / work_start / work_end / obligations here; the {...base}
      // spread above preserves whatever the planner stored, so editing lifestyle
      // can never clobber or fork the planner's schedule data.
    };

    if (gender) onboardingData.gender = gender;
    if (age && !Number.isNaN(parseInt(age, 10)) && parseInt(age, 10) > 0) onboardingData.age = parseInt(age, 10);
    if (finalHeight !== undefined && finalHeight > 0) onboardingData.height = Math.round(finalHeight * 10) / 10;
    if (finalWeight !== undefined && finalWeight > 0) onboardingData.weight = Math.round(finalWeight * 10) / 10;

    try {
      await api.saveOnboarding(onboardingData as any);
      await refreshUser();
      // Lifestyle edits feed the chatbot's USER CONTEXT (wake/sleep/work
      // hours, priority) and may change downstream schedule state. Force
      // refetch so every screen sees the new data on next mount.
      queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull, refetchType: 'all' });
      queryClient.invalidateQueries({ queryKey: queryKeys.activeSchedulesSummary, refetchType: 'all' });
      queryClient.invalidateQueries({ queryKey: queryKeys.maxes, refetchType: 'all' });
      Alert.alert('Success', 'Profile updated successfully.');
      navigation.goBack();
    } catch (error: any) {
      const msg =
        typeof error?.response?.data?.detail === 'string'
          ? error.response.data.detail
          : error?.message || 'Could not save changes.';
      Alert.alert('Error', msg);
    } finally {
      setLoading(false);
    }
  };

  const shiftTime = (hhmm0: string, delta: number): string => {
    const [h, m] = (hhmm0 || '07:00').split(':').map((x) => parseInt(x, 10) || 0);
    const total = (((h * 60 + m + delta) % 1440) + 1440) % 1440;
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  };

  const renderStepper = (value: string, setter: (s: string) => void) => (
    <View style={styles.stepperRow}>
      <TouchableOpacity style={styles.stepBtn} activeOpacity={0.7} onPress={() => setter(shiftTime(value, -15))}>
        <Ionicons name="remove" size={18} color={colors.foreground} />
      </TouchableOpacity>
      <Text style={styles.stepperValue}>{formatTime12h(value)}</Text>
      <TouchableOpacity style={styles.stepBtn} activeOpacity={0.7} onPress={() => setter(shiftTime(value, 15))}>
        <Ionicons name="add" size={18} color={colors.foreground} />
      </TouchableOpacity>
    </View>
  );

  const timeRow = (
    label: string,
    _which: TimePickerKey,
    value: string,
    setter: (s: string) => void,
  ) => (
    <View style={styles.timeBlock}>
      <Text style={styles.inputLabel}>{label}</Text>
      {renderStepper(value, setter)}
    </View>
  );

  // Optional precise anchor (workout / get-ready). null = "Auto": the coach
  // derives it from wake/sleep. Picking a time pins every related routine to
  // it across all maxxes; an "Auto" entry at the top clears back to default.
  const anchorRow = (
    label: string,
    _which: TimePickerKey,
    value: string | null,
    setter: (s: string | null) => void,
    autoHint: string,
    iconName: keyof typeof Ionicons.glyphMap,
  ) => (
    <View style={styles.timeBlock}>
      <View style={styles.anchorLabelRow}>
        <Ionicons name={iconName} size={13} color={colors.textMuted} style={{ marginRight: 6 }} />
        <Text style={[styles.inputLabel, { marginTop: 0, marginBottom: 0 }]}>{label}</Text>
      </View>
      <View style={styles.anchorSeg}>
        <TouchableOpacity style={[styles.anchorSegItem, !value && styles.anchorSegItemOn]} activeOpacity={0.8} onPress={() => setter(null)}>
          <Text style={[styles.anchorSegText, !value && styles.anchorSegTextOn]}>Auto</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.anchorSegItem, !!value && styles.anchorSegItemOn]} activeOpacity={0.8} onPress={() => setter(value || '08:00')}>
          <Text style={[styles.anchorSegText, !!value && styles.anchorSegTextOn]}>Set time</Text>
        </TouchableOpacity>
      </View>
      {value ? renderStepper(value, (s) => setter(s)) : <Text style={styles.anchorAutoHint}>{autoHint}</Text>}
    </View>
  );

  const sectionKicker = (t: string) => <Text style={styles.kicker}>{t}</Text>;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Edit lifestyle</Text>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView
          scrollEnabled
          contentContainerStyle={[
            styles.content,
            isWide && styles.contentWide,
          ]}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.lead}>Update your profile. Changes take effect when you save.</Text>

              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>Body</Text>
                <View style={styles.unitToggle}>
                  <TouchableOpacity onPress={() => setUnitSystem('metric')} style={[styles.unitBtn, unitSystem === 'metric' && styles.unitBtnActive]}>
                    <Text style={[styles.unitLabel, unitSystem === 'metric' && styles.unitLabelActive]}>Metric</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => setUnitSystem('imperial')} style={[styles.unitBtn, unitSystem === 'imperial' && styles.unitBtnActive]}>
                    <Text style={[styles.unitLabel, unitSystem === 'imperial' && styles.unitLabelActive]}>US</Text>
                  </TouchableOpacity>
                </View>
              </View>

              <Text style={styles.inputLabel}>GENDER</Text>
              <View style={styles.chipRow}>
                {['Male', 'Female', 'Other'].map((g) => (
                  <TouchableOpacity key={g} style={[styles.chip, gender === g && styles.chipSelected]} onPress={() => setGender(g)}>
                    <Text style={[styles.chipText, gender === g && styles.chipTextSelected]}>{g}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.inputGroup}>
                <View style={styles.inputHalf}>
                  <Text style={styles.inputLabel}>AGE</Text>
                  <TextInput style={styles.field} keyboardType="numeric" value={age} onChangeText={setAge} placeholder="Years" placeholderTextColor={colors.textMuted} />
                </View>
                <View style={styles.inputHalf}>
                  <Text style={styles.inputLabel}>WEIGHT ({unitSystem === 'metric' ? 'KG' : 'LBS'})</Text>
                  <TextInput
                    style={styles.field}
                    keyboardType="numeric"
                    value={weight}
                    onChangeText={setWeight}
                    placeholder={unitSystem === 'metric' ? 'kg' : 'lbs'}
                    placeholderTextColor={colors.textMuted}
                  />
                </View>
              </View>

              <Text style={styles.inputLabel}>HEIGHT ({unitSystem === 'metric' ? 'CM' : 'FT/IN'})</Text>
              {unitSystem === 'metric' ? (
                <TextInput style={styles.field} keyboardType="numeric" value={height} onChangeText={setHeight} placeholder="cm" placeholderTextColor={colors.textMuted} />
              ) : (
                <View style={styles.inputGroup}>
                  <View style={styles.inputHalf}>
                    <TextInput style={styles.field} keyboardType="numeric" value={heightFt} onChangeText={setHeightFt} placeholder="ft" placeholderTextColor={colors.textMuted} />
                  </View>
                  <View style={styles.inputHalf}>
                    <TextInput style={styles.field} keyboardType="numeric" value={heightIn} onChangeText={setHeightIn} placeholder="in" placeholderTextColor={colors.textMuted} />
                  </View>
                </View>
              )}

              <View style={styles.card}>
                {sectionKicker('DAILY TIMINGS')}
                <Text style={styles.cardTitle}>Your day, hour by hour</Text>
                <Text style={styles.cardHint}>
                  These anchor all your routines. Leave anything on Auto and the coach picks the time.
                </Text>
                {timeRow('Wake', 'wake', wakeTime, setWakeTime)}
                {anchorRow(
                  'Get ready',
                  'getReady',
                  getReadyTime,
                  setGetReadyTime,
                  'Start of your morning routine. Edit the full window in the Day Planner.',
                  'water-outline',
                )}
                <View style={styles.timeBlock}>
                  <View style={styles.anchorLabelRow}>
                    <Ionicons name="time-outline" size={13} color={colors.textMuted} style={{ marginRight: 6 }} />
                    <Text style={[styles.inputLabel, { marginTop: 0, marginBottom: 0 }]}>
                      How long to get ready
                    </Text>
                  </View>
                  <View style={styles.anchorSeg}>
                    {GET_READY_DURATIONS.map((d) => {
                      const on = getReadyMinutes === d;
                      return (
                        <TouchableOpacity
                          key={d}
                          style={[styles.anchorSegItem, on && styles.anchorSegItemOn]}
                          activeOpacity={0.8}
                          onPress={() => setGetReadyMinutes(d)}
                          accessibilityRole="button"
                          accessibilityState={{ selected: on }}
                          accessibilityLabel={`${d} minutes to get ready`}
                        >
                          <Text style={[styles.anchorSegText, on && styles.anchorSegTextOn]}>
                            {d === 60 ? '60+' : d}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                  <Text style={styles.anchorAutoHint}>
                    Longer prep gives your morning routine more room before the rest of your day.
                  </Text>
                </View>
                {timeRow('Bedtime', 'sleep', sleepTime, setSleepTime)}
                <TouchableOpacity
                  style={styles.plannerPointer}
                  activeOpacity={0.7}
                  onPress={() => navigation.navigate('DayPlanner')}
                >
                  <View style={styles.plannerPointerIcon}>
                    <Ionicons name="calendar-outline" size={16} color={colors.foreground} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.plannerPointerTitle}>Workout window & commitments</Text>
                    <Text style={styles.plannerPointerText}>
                      Set a workout window and recurring commitments. They can vary by day in the Day Planner.
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              </View>

              {/* Onairos personalization card — let users connect or refresh
                  their cross-app personality/habit data. The chatbot picks up
                  the new traits on the next turn via coaching_service. */}
              {onairosEnabled ? (
                <View style={styles.card}>
                  {sectionKicker('EXTERNAL PERSONALIZATION')}
                  <Text style={styles.cardTitle}>Connect your apps</Text>
                  <Text style={styles.cardHint}>
                    Pull personality + habit signals from apps you already use. Re-run any time to refresh.
                  </Text>
                  <TouchableOpacity
                    onPress={() => setOnairosVisible(true)}
                    activeOpacity={0.85}
                    style={styles.onairosBtn}
                  >
                    <Ionicons name="link-outline" size={15} color={colors.background} />
                    <Text style={styles.onairosBtnText}>Connect with Onairos</Text>
                  </TouchableOpacity>
                </View>
              ) : null}

              {/* What Max knows — the unified personalization profile across
                  food, culture, work, rhythm, personality and comms style. */}
              <TouchableOpacity
                style={styles.card}
                activeOpacity={0.85}
                onPress={() => navigation.navigate('Personalization' as never)}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <View style={{ flex: 1, paddingRight: 12 }}>
                    {sectionKicker('PERSONALIZATION')}
                    <Text style={styles.cardTitle}>What Max knows about you</Text>
                    <Text style={styles.cardHint}>
                      Food, culture, work, how you like to be coached. Add or fix anything.
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                </View>
              </TouchableOpacity>

              {priorityRanking.length > 0 ? (
                <View style={styles.card}>
                  {sectionKicker('PRIORITY')}
                  <Text style={styles.cardTitle}>What matters most</Text>
                  {priorityRanking.map((key, i) => (
                    <View key={key} style={styles.rankRow}>
                      <Text style={styles.rankNum}>{i + 1}</Text>
                      <Text style={styles.rankLabel}>{PRIORITY_LABELS[key as PriorityKey] || key}</Text>
                      <View style={styles.rankArrows}>
                        <TouchableOpacity onPress={() => movePriority(i, -1)} disabled={i === 0} style={styles.iconBtn}>
                          <Ionicons name="chevron-up" size={22} color={i === 0 ? colors.border : colors.foreground} />
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => movePriority(i, 1)}
                          disabled={i === priorityRanking.length - 1}
                          style={styles.iconBtn}
                        >
                          <Ionicons
                            name="chevron-down"
                            size={22}
                            color={i === priorityRanking.length - 1 ? colors.border : colors.foreground}
                          />
                        </TouchableOpacity>
                      </View>
                    </View>
                  ))}
                </View>
              ) : null}

          <View style={{ height: 100 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      <View style={styles.footer}>
        <TouchableOpacity style={[styles.saveBtn, loading && { opacity: 0.7 }]} onPress={handleSave} disabled={loading}>
          {loading ? <ActivityIndicator color={colors.background} /> : <Text style={styles.saveBtnText}>Save all changes</Text>}
        </TouchableOpacity>
      </View>

      <OnairosConnectModal
        visible={onairosVisible}
        onClose={() => setOnairosVisible(false)}
        onConnected={() => {
          // Refresh user object so any auth-side onairos flag flips, and
          // bust schedules so the next chat turn rebuilds with the new
          // coaching context (which now includes the fresh traits).
          void refreshUser?.();
          queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull, refetchType: 'all' });
          setOnairosVisible(false);
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  /* Quieter top bar — hairline divider instead of 1px, more breathing room. */
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 60,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderLight,
    backgroundColor: colors.background,
  },
  /* Editorial header title in the same serif as the rest of the app. */
  headerTitle: {
    fontFamily: fonts.serif,
    fontSize: 22,
    fontWeight: '400',
    color: colors.foreground,
    letterSpacing: -0.4,
  },
  backButton: { padding: 4 },
  lead: {
    fontSize: 13.5,
    color: colors.textMuted,
    lineHeight: 19,
    letterSpacing: 0.05,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  content: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.xxl },
  contentWide: { maxWidth: 560, alignSelf: 'center', width: '100%', paddingHorizontal: spacing.xxl },
  /* Tighter, more spaced kicker. Reads as a section divider, not a label. */
  kicker: {
    fontFamily: fonts.sansSemiBold,
    fontSize: 10,
    color: colors.textMuted,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
    marginBottom: 6,
    opacity: 0.7,
  },
  /* Card: drop the heavy 1px border, lift with subtle shadow on iOS,
     plus hairline border on Android so it still has an edge. */
  card: {
    backgroundColor: colors.card,
    borderRadius: 18,
    padding: spacing.lg,
    marginTop: spacing.lg,
    ...(Platform.OS === 'ios'
      ? {
          shadowColor: '#0a0a0b',
          shadowOpacity: 0.04,
          shadowRadius: 10,
          shadowOffset: { width: 0, height: 2 },
        }
      : {
          borderWidth: StyleSheet.hairlineWidth,
          borderColor: colors.border,
        }),
  },
  /* Card title in serif — matches the rest of the app's editorial tone. */
  cardTitle: {
    fontFamily: fonts.serif,
    fontSize: 20,
    fontWeight: '400',
    color: colors.foreground,
    letterSpacing: -0.3,
    marginBottom: 4,
  },
  cardHint: {
    fontSize: 13,
    color: colors.textMuted,
    marginBottom: spacing.md,
    lineHeight: 18,
    letterSpacing: 0.05,
  },
  sectionTitle: {
    fontFamily: fonts.serif,
    fontSize: 22,
    fontWeight: '400',
    color: colors.foreground,
    letterSpacing: -0.4,
    marginBottom: spacing.sm,
    marginTop: spacing.xl,
  },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.xl, marginBottom: spacing.md },
  /** Cancels scroll horizontal padding so rows span screen width (with inner lg inset). */
  unitToggle: {
    flexDirection: 'row',
    backgroundColor: colors.card,
    borderRadius: borderRadius.full,
    padding: 4,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  unitBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: borderRadius.full },
  unitBtnActive: { backgroundColor: colors.foreground },
  unitLabel: { fontSize: 12, fontWeight: '600', color: colors.textMuted },
  unitLabelActive: { color: colors.background },
  /* Field labels: tracked uppercase, smaller — feel like form micro-labels. */
  inputLabel: {
    fontFamily: fonts.sansSemiBold,
    fontSize: 10,
    color: colors.textMuted,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    marginBottom: 8,
    marginTop: spacing.lg,
    opacity: 0.85,
  },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  /* Modern chip: hairline border, subtle shadow on iOS, tighter padding. */
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    ...(Platform.OS === 'ios'
      ? { shadowColor: '#0a0a0b', shadowOpacity: 0.03, shadowRadius: 4, shadowOffset: { width: 0, height: 1 } }
      : null),
  },
  chipSelected: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  chipText: { fontSize: 13, fontWeight: '500', color: colors.textSecondary, letterSpacing: 0.1 },
  chipTextSelected: { color: colors.background, fontWeight: '600' },
  inputGroup: { flexDirection: 'row', gap: spacing.md },
  inputHalf: { flex: 1 },
  /* Soft field — no visible border, just a tinted surface. Feels modern. */
  field: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 14,
    color: colors.foreground,
    fontSize: 15,
    fontWeight: '500',
  },
  list: { gap: 8 },
  /* List card: hairline border, slightly tighter padding, no internal shadow. */
  listCard: {
    backgroundColor: colors.card,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'transparent',
  },
  listCardSelected: {
    backgroundColor: colors.surface,
    borderColor: colors.foreground,
  },
  listLabel: {
    fontSize: 14.5,
    fontWeight: '500',
    color: colors.foreground,
    letterSpacing: 0.05,
  },
  listDesc: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 2,
    letterSpacing: 0.05,
  },
  rankRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderLight,
  },
  rankNum: {
    width: 26,
    fontFamily: fonts.sansSemiBold,
    fontSize: 13,
    color: colors.textMuted,
    letterSpacing: 0.4,
  },
  rankLabel: {
    flex: 1,
    fontSize: 15,
    color: colors.foreground,
    fontWeight: '500',
    letterSpacing: 0.05,
  },
  rankArrows: { flexDirection: 'row', gap: 4 },
  iconBtn: { padding: 6 },
  tagWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tag: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  tagOn: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  tagText: { fontSize: 12.5, fontWeight: '500', color: colors.textSecondary, letterSpacing: 0.1 },
  tagTextOn: { color: colors.background, fontWeight: '600' },
  dayPill: {
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  dayPillOn: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  dayPillText: { fontSize: 13.5, fontWeight: '500', color: colors.textSecondary },
  dayPillTextOn: { color: colors.background, fontWeight: '600' },
  timeBlock: { marginBottom: 6 },
  /* Inline time stepper (−/+ 15m) — consistent with onboarding, no dropdown. */
  stepperRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    borderRadius: 12,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  stepBtn: {
    width: 34,
    height: 34,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  stepperValue: {
    fontSize: 16,
    color: colors.foreground,
    fontWeight: '600',
    letterSpacing: 0.05,
  },
  anchorSeg: {
    flexDirection: 'row',
    gap: 4,
    padding: 4,
    backgroundColor: colors.surface,
    borderRadius: 12,
    marginBottom: 8,
  },
  anchorSegItem: { flex: 1, paddingVertical: 9, alignItems: 'center', borderRadius: 9 },
  anchorSegItemOn: { backgroundColor: colors.foreground },
  anchorSegText: { fontSize: 13.5, fontWeight: '500', color: colors.textSecondary },
  anchorSegTextOn: { color: '#fff' },
  anchorLabelRow: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.lg, marginBottom: 8 },
  anchorAutoHint: {
    fontSize: 11.5,
    color: colors.textMuted,
    lineHeight: 15,
    marginTop: 5,
    marginLeft: 2,
    opacity: 0.8,
  },
  /* Tappable pointer into the Day Planner — workout range + commitments live
     there now (work is an obligation, the workout is a window). */
  plannerPointer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: spacing.lg,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderLight,
  },
  plannerPointerIcon: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  plannerPointerTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.foreground,
    letterSpacing: 0.05,
    marginBottom: 2,
  },
  plannerPointerText: {
    fontSize: 12,
    color: colors.textMuted,
    lineHeight: 16,
    letterSpacing: 0.05,
  },
  /* Onairos card button — same shape as saveBtn but inline in the card. */
  onairosBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: colors.foreground,
    borderRadius: borderRadius.full,
    paddingVertical: 12,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md,
  },
  onairosBtnText: {
    color: colors.background,
    fontWeight: '600',
    fontSize: 13.5,
    letterSpacing: 0.3,
  },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: Platform.OS === 'ios' ? 40 : 24,
    backgroundColor: colors.background,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderLight,
  },
  /* Modern primary action — full pill, slightly taller. */
  saveBtn: {
    backgroundColor: colors.foreground,
    borderRadius: borderRadius.full,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.foreground,
  },
  saveBtnText: {
    fontFamily: fonts.sansSemiBold,
    fontSize: 14,
    color: colors.background,
    letterSpacing: 0.4,
  },
});

/* "Your Maxxes" editorial row — mirrors ModuleSelect. */
