import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  useWindowDimensions,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import {
  PRIORITY_LABELS,
  type PriorityKey,
  APPEARANCE_OPTIONS,
  SKIN_CONCERNS,
  SCREEN_TIME_BANDS,
  TIME_OPTIONS,
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

const GOALS = [
  { id: 'bonemax', label: 'Bonemax', icon: 'body-outline' },
  { id: 'heightmax', label: 'Heightmax', icon: 'resize-outline' },
  { id: 'skinmax', label: 'skinmax', icon: 'sparkles-outline' },
  { id: 'hairmax', label: 'Hairmax', icon: 'cut-outline' },
  { id: 'fitmax', label: 'Fitmax', icon: 'fitness-outline' },
];

const ACTIVITY_LEVELS = [
  { id: 'sedentary', label: 'Sedentary', desc: 'Little to no exercise' },
  { id: 'light', label: 'Light', desc: '1-3 days/week' },
  { id: 'moderate', label: 'Moderate', desc: '3-5 days/week' },
  { id: 'active', label: 'Active', desc: '6-7 days/week' },
];

function hydrateFromOnboarding(ob: Record<string, any>) {
  return {
    priorityOrder: normalizePriorityOrder(ob.priority_order),
    appearanceConcerns: Array.isArray(ob.appearance_concerns) ? [...ob.appearance_concerns] : [],
    primarySkin: ob.primary_skin_concern || '',
    secondarySkin: ob.secondary_skin_concern && ob.secondary_skin_concern !== '' ? ob.secondary_skin_concern : 'none',
    skincareRoutine: ob.skincare_routine_level || '',
    hairFamily: ob.hair_family_history || '',
    hairLoss: ob.hair_current_loss || '',
    hairTreatments: ob.hair_treatments_current || '',
    hairSides: ob.hair_side_effect_sensitivity || '',
    fitGoal: ob.fitmax_primary_goal || ob.primary_goal || '',
    fitExperience: ob.fitmax_training_experience || ob.training_experience || 'beginner',
    fitEquipment: inferFitEquipmentFromOnboarding(ob),
    fitDays: typeof ob.fitmax_workout_days_per_week === 'number' ? ob.fitmax_workout_days_per_week : null,
    wakeTime: ob.wake_time || '07:00',
    sleepTime: ob.sleep_time || '23:00',
    workoutTime:
      ob.preferred_workout_time || ob.fitmax_preferred_workout_time || ob.heightmax_workout_time || '18:00',
    screenBand: inferScreenBand(ob),
  };
}

export default function EditPersonalScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { width } = useWindowDimensions();
  const isWide = width > 600;
  const { user, refreshUser } = useAuth();
  const [loading, setLoading] = useState(false);

  const onlyGoals = route.params?.onlyGoals === true;

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
  const [priorityOrder, setPriorityOrder] = useState<PriorityKey[]>(v2.priorityOrder);
  const [appearanceConcerns, setAppearanceConcerns] = useState<string[]>(v2.appearanceConcerns);
  const [primarySkin, setPrimarySkin] = useState(v2.primarySkin);
  const [secondarySkin, setSecondarySkin] = useState(v2.secondarySkin);
  const [skincareRoutine, setSkincareRoutine] = useState(v2.skincareRoutine);
  const [hairFamily, setHairFamily] = useState(v2.hairFamily);
  const [hairLoss, setHairLoss] = useState(v2.hairLoss);
  const [hairTreatments, setHairTreatments] = useState(v2.hairTreatments);
  const [hairSides, setHairSides] = useState(v2.hairSides);
  const [fitGoal, setFitGoal] = useState(v2.fitGoal);
  const [fitExperience, setFitExperience] = useState(v2.fitExperience);
  const [fitEquipment, setFitEquipment] = useState(v2.fitEquipment);
  const [fitDays, setFitDays] = useState<number | null>(v2.fitDays);
  const [wakeTime, setWakeTime] = useState(v2.wakeTime);
  const [sleepTime, setSleepTime] = useState(v2.sleepTime);
  const [workoutTime, setWorkoutTime] = useState(v2.workoutTime);
  const [screenBand, setScreenBand] = useState(v2.screenBand);
  const [openTimePicker, setOpenTimePicker] = useState<'wake' | 'sleep' | 'workout' | null>(null);

  const movePriority = useCallback((index: number, dir: -1 | 1) => {
    const j = index + dir;
    if (j < 0 || j >= priorityOrder.length) return;
    const next = [...priorityOrder];
    [next[index], next[j]] = [next[j], next[index]];
    setPriorityOrder(next);
  }, [priorityOrder]);

  const toggleAppearance = (id: string) => {
    setAppearanceConcerns((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  useEffect(() => {
    if (!user?.onboarding) return;
    const ob = user.onboarding;
    setUnitSystem((ob.unit_system as any) || 'imperial');
    setSelectedGoals(ob.goals || []);
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
    setPriorityOrder(h.priorityOrder);
    setAppearanceConcerns(h.appearanceConcerns);
    setPrimarySkin(h.primarySkin);
    setSecondarySkin(h.secondarySkin);
    setSkincareRoutine(h.skincareRoutine);
    setHairFamily(h.hairFamily);
    setHairLoss(h.hairLoss);
    setHairTreatments(h.hairTreatments);
    setHairSides(h.hairSides);
    setFitGoal(h.fitGoal);
    setFitExperience(h.fitExperience);
    setFitEquipment(h.fitEquipment);
    setFitDays(h.fitDays);
    setWakeTime(h.wakeTime);
    setSleepTime(h.sleepTime);
    setWorkoutTime(h.workoutTime);
    setScreenBand(h.screenBand);
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

    if (onlyGoals) {
      const onboardingData = {
        ...base,
        goals: selectedGoals || [],
        timezone: tz,
        completed: true,
      };
      try {
        await api.saveOnboarding(onboardingData as any);
        await refreshUser();
        Alert.alert('Success', 'Your Maxxes were updated.');
        navigation.goBack();
      } catch (error: any) {
        Alert.alert('Error', error?.response?.data?.detail || 'Could not save changes.');
      } finally {
        setLoading(false);
      }
      return;
    }

    const heavy = screenBand ? heavyScreenFromBand(screenBand) : base.heightmax_screen_hours;

    const onboardingData: Record<string, any> = {
      ...base,
      goals: selectedGoals || [],
      completed: true,
      timezone: tz,
      unit_system: unitSystem,
      questionnaire_v2_completed: base.questionnaire_v2_completed ?? true,
      priority_order: [...priorityOrder],
      appearance_concerns: [...appearanceConcerns],
      experience_level: mapTrainingToExperience(fitExperience),
      fitmax_training_experience: fitExperience,
      equipment: mapEquipmentToList(fitEquipment),
      fitmax_equipment: fitEquipment,
      activity_level: activityLevel || 'moderate',
      wake_time: hhmm(wakeTime),
      sleep_time: hhmm(sleepTime),
      preferred_workout_time: hhmm(workoutTime),
      fitmax_preferred_workout_time: hhmm(workoutTime),
      heightmax_workout_time: hhmm(workoutTime),
    };

    if (gender) onboardingData.gender = gender;
    if (age && !Number.isNaN(parseInt(age, 10)) && parseInt(age, 10) > 0) onboardingData.age = parseInt(age, 10);
    if (finalHeight !== undefined && finalHeight > 0) onboardingData.height = Math.round(finalHeight * 10) / 10;
    if (finalWeight !== undefined && finalWeight > 0) onboardingData.weight = Math.round(finalWeight * 10) / 10;

    if (primarySkin) {
      onboardingData.primary_skin_concern = primarySkin;
      onboardingData.secondary_skin_concern = secondarySkin || 'none';
      onboardingData.skincare_routine_level = skincareRoutine;
      onboardingData.skin_type = mapSkinConcernToType(primarySkin);
    }

    onboardingData.hair_family_history = hairFamily;
    onboardingData.hair_current_loss = hairLoss;
    onboardingData.hair_treatments_current = hairTreatments;
    onboardingData.hair_side_effect_sensitivity = hairSides;
    if (hairLoss === 'yes_active' || hairLoss === 'starting') {
      onboardingData.hair_thinning = 'yes';
      onboardingData.thinning = 'yes';
    } else if (hairLoss) {
      onboardingData.hair_thinning = 'no';
      onboardingData.thinning = 'no';
    }
    if (hairSides === 'had_sides') {
      onboardingData.hairmax_fin_sensitive = true;
      onboardingData.hair_finasteride_sensitive = true;
    } else if (hairSides) {
      onboardingData.hairmax_fin_sensitive = false;
      onboardingData.hair_finasteride_sensitive = false;
    }

    onboardingData.fitmax_primary_goal = fitGoal;
    onboardingData.primary_goal = fitGoal;
    onboardingData.training_experience = fitExperience;
    if (fitDays != null) onboardingData.fitmax_workout_days_per_week = fitDays;

    if (screenBand) {
      onboardingData.screen_hours_daily = screenBand;
      onboardingData.heightmax_screen_hours = heavy;
      onboardingData.bonemax_heavy_screen_time = heavy;
    }

    try {
      await api.saveOnboarding(onboardingData as any);
      await refreshUser();
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

  const timeRow = (
    label: string,
    which: 'wake' | 'sleep' | 'workout',
    value: string,
    setter: (s: string) => void,
  ) => (
    <View style={styles.timeBlock}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TouchableOpacity
        style={styles.timeTrigger}
        activeOpacity={0.85}
        onPress={() => setOpenTimePicker((p) => (p === which ? null : which))}
      >
        <Text style={styles.timeTriggerText}>{formatTime12h(value)}</Text>
        <Ionicons name={openTimePicker === which ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textMuted} />
      </TouchableOpacity>
      {openTimePicker === which ? (
        <View style={styles.timeDropdown}>
          <ScrollView nestedScrollEnabled style={styles.timeDropdownScroll} keyboardShouldPersistTaps="handled">
            {TIME_OPTIONS.map((t) => {
              const active = t === value;
              return (
                <TouchableOpacity
                  key={`${which}-${t}`}
                  style={[styles.timeOption, active && styles.timeOptionOn]}
                  onPress={() => {
                    setter(t);
                    setOpenTimePicker(null);
                  }}
                >
                  <Text style={[styles.timeOptionText, active && styles.timeOptionTextOn]}>{formatTime12h(t)}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      ) : null}
    </View>
  );

  const sectionKicker = (t: string) => <Text style={styles.kicker}>{t}</Text>;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{onlyGoals ? 'Your Maxxes' : 'Edit lifestyle'}</Text>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView
          contentContainerStyle={[styles.content, isWide && styles.contentWide]}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.lead}>
            {onlyGoals
              ? 'Choose which programs show on Home.'
              : 'Update what you shared at signup — one place, no quiz replay.'}
          </Text>

          <Text style={styles.sectionTitle}>Your Maxxes</Text>
          <View style={styles.goalsGrid}>
            {GOALS.map((goal) => {
              const selected = selectedGoals.includes(goal.id);
              return (
                <TouchableOpacity
                  key={goal.id}
                  style={[styles.goalCard, selected && styles.goalCardSelected]}
                  onPress={() =>
                    setSelectedGoals((prev) =>
                      prev.includes(goal.id) ? prev.filter((g) => g !== goal.id) : [...prev, goal.id],
                    )
                  }
                >
                  <Ionicons name={goal.icon as any} size={20} color={selected ? colors.foreground : colors.textMuted} />
                  <Text style={[styles.goalLabel, selected && styles.goalLabelSelected]}>{goal.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {onlyGoals ? <View style={{ height: 80 }} /> : null}

          {!onlyGoals && (
            <>
              <View style={styles.card}>
                {sectionKicker('NOTIFICATIONS')}
                <Text style={styles.cardTitle}>What we prioritize</Text>
                <Text style={styles.cardHint}>Top of the list = stronger nudges. Drag order with arrows.</Text>
                {priorityOrder.map((key, i) => (
                  <View key={key} style={styles.rankRow}>
                    <Text style={styles.rankNum}>{i + 1}</Text>
                    <Text style={styles.rankLabel}>{PRIORITY_LABELS[key]}</Text>
                    <View style={styles.rankArrows}>
                      <TouchableOpacity onPress={() => movePriority(i, -1)} disabled={i === 0} style={styles.iconBtn}>
                        <Ionicons name="chevron-up" size={22} color={i === 0 ? colors.border : colors.foreground} />
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => movePriority(i, 1)}
                        disabled={i === priorityOrder.length - 1}
                        style={styles.iconBtn}
                      >
                        <Ionicons
                          name="chevron-down"
                          size={22}
                          color={i === priorityOrder.length - 1 ? colors.border : colors.foreground}
                        />
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}
                <Text style={[styles.inputLabel, { marginTop: spacing.lg }]}>FOCUS AREAS</Text>
                <View style={styles.tagWrap}>
                  {APPEARANCE_OPTIONS.map((o) => {
                    const on = appearanceConcerns.includes(o.id);
                    return (
                      <TouchableOpacity key={o.id} style={[styles.tag, on && styles.tagOn]} onPress={() => toggleAppearance(o.id)}>
                        <Text style={[styles.tagText, on && styles.tagTextOn]}>{o.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>

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

              <Text style={[styles.inputLabel, { marginTop: spacing.lg }]}>ACTIVITY LEVEL</Text>
              <View style={styles.list}>
                {ACTIVITY_LEVELS.map((level) => (
                  <TouchableOpacity
                    key={level.id}
                    style={[styles.listCard, activityLevel === level.id && styles.listCardSelected]}
                    onPress={() => setActivityLevel(level.id)}
                  >
                    <Text style={styles.listLabel}>{level.label}</Text>
                    <Text style={styles.listDesc}>{level.desc}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.card}>
                {sectionKicker('SKIN')}
                <Text style={styles.cardTitle}>Skin details</Text>
                <Text style={styles.inputLabel}>PRIMARY CONCERN</Text>
                <View style={styles.tagWrap}>
                  {SKIN_CONCERNS.map((s) => (
                    <TouchableOpacity key={s.id} style={[styles.tag, primarySkin === s.id && styles.tagOn]} onPress={() => setPrimarySkin(s.id)}>
                      <Text style={[styles.tagText, primarySkin === s.id && styles.tagTextOn]}>{s.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.inputLabel}>SECONDARY</Text>
                <View style={styles.tagWrap}>
                  <TouchableOpacity style={[styles.tag, secondarySkin === 'none' && styles.tagOn]} onPress={() => setSecondarySkin('none')}>
                    <Text style={[styles.tagText, secondarySkin === 'none' && styles.tagTextOn]}>None</Text>
                  </TouchableOpacity>
                  {SKIN_CONCERNS.map((s) => (
                    <TouchableOpacity key={s.id} style={[styles.tag, secondarySkin === s.id && styles.tagOn]} onPress={() => setSecondarySkin(s.id)}>
                      <Text style={[styles.tagText, secondarySkin === s.id && styles.tagTextOn]}>{s.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={styles.inputLabel}>ROUTINE LEVEL</Text>
                {[
                  { id: 'none', label: 'Nothing consistent' },
                  { id: 'basic', label: 'Cleanser + moisturizer' },
                  { id: 'full', label: 'Full routine' },
                ].map((r) => (
                  <TouchableOpacity
                    key={r.id}
                    style={[styles.listCard, skincareRoutine === r.id && styles.listCardSelected]}
                    onPress={() => setSkincareRoutine(r.id)}
                  >
                    <Text style={styles.listLabel}>{r.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.card}>
                {sectionKicker('HAIR')}
                <Text style={styles.cardTitle}>Hair context</Text>
                <Text style={styles.inputLabel}>FAMILY HAIR LOSS</Text>
                {[
                  { id: 'mom', label: "Mom's side" },
                  { id: 'dad', label: "Dad's side" },
                  { id: 'both', label: 'Both sides' },
                  { id: 'no', label: 'No' },
                  { id: 'unknown', label: "Don't know" },
                ].map((x) => (
                  <TouchableOpacity key={x.id} style={[styles.listCard, hairFamily === x.id && styles.listCardSelected]} onPress={() => setHairFamily(x.id)}>
                    <Text style={styles.listLabel}>{x.label}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={styles.inputLabel}>CURRENT LOSS</Text>
                {[
                  { id: 'yes_active', label: 'Yes — actively' },
                  { id: 'starting', label: 'Starting to notice' },
                  { id: 'no', label: 'No' },
                  { id: 'unsure', label: 'Not sure' },
                ].map((x) => (
                  <TouchableOpacity key={x.id} style={[styles.listCard, hairLoss === x.id && styles.listCardSelected]} onPress={() => setHairLoss(x.id)}>
                    <Text style={styles.listLabel}>{x.label}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={styles.inputLabel}>TREATMENTS</Text>
                {[
                  { id: 'nothing', label: 'Nothing' },
                  { id: 'minoxidil', label: 'Minoxidil' },
                  { id: 'finasteride', label: 'Finasteride' },
                  { id: 'both', label: 'Both' },
                  { id: 'other', label: 'Other' },
                ].map((x) => (
                  <TouchableOpacity key={x.id} style={[styles.listCard, hairTreatments === x.id && styles.listCardSelected]} onPress={() => setHairTreatments(x.id)}>
                    <Text style={styles.listLabel}>{x.label}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={styles.inputLabel}>FIN / SIDE EFFECTS</Text>
                {[
                  { id: 'not_concerned', label: 'Not concerned' },
                  { id: 'somewhat', label: 'Somewhat concerned' },
                  { id: 'had_sides', label: 'Had sides before' },
                ].map((x) => (
                  <TouchableOpacity key={x.id} style={[styles.listCard, hairSides === x.id && styles.listCardSelected]} onPress={() => setHairSides(x.id)}>
                    <Text style={styles.listLabel}>{x.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.card}>
                {sectionKicker('TRAINING')}
                <Text style={styles.cardTitle}>Strength & physique</Text>
                <Text style={styles.inputLabel}>PRIMARY GOAL</Text>
                {[
                  { id: 'lean', label: 'Get lean (face gains)' },
                  { id: 'muscle', label: 'Build muscle' },
                  { id: 'both', label: 'Both / recomp' },
                  { id: 'maintain', label: 'Maintain' },
                ].map((x) => (
                  <TouchableOpacity key={x.id} style={[styles.listCard, fitGoal === x.id && styles.listCardSelected]} onPress={() => setFitGoal(x.id)}>
                    <Text style={styles.listLabel}>{x.label}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={styles.inputLabel}>EXPERIENCE</Text>
                {[
                  { id: 'never', label: 'Never trained' },
                  { id: 'beginner', label: 'Beginner (<1 yr)' },
                  { id: 'intermediate', label: 'Intermediate (1–3 yr)' },
                  { id: 'advanced', label: 'Advanced (3+ yr)' },
                ].map((x) => (
                  <TouchableOpacity key={x.id} style={[styles.listCard, fitExperience === x.id && styles.listCardSelected]} onPress={() => setFitExperience(x.id)}>
                    <Text style={styles.listLabel}>{x.label}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={styles.inputLabel}>EQUIPMENT</Text>
                {[
                  { id: 'full_gym', label: 'Full gym' },
                  { id: 'home_gym', label: 'Home gym (DB + bench + bar)' },
                  { id: 'bodyweight', label: 'Bodyweight only' },
                ].map((x) => (
                  <TouchableOpacity key={x.id} style={[styles.listCard, fitEquipment === x.id && styles.listCardSelected]} onPress={() => setFitEquipment(x.id)}>
                    <Text style={styles.listLabel}>{x.label}</Text>
                  </TouchableOpacity>
                ))}
                <Text style={styles.inputLabel}>DAYS PER WEEK</Text>
                <View style={styles.tagWrap}>
                  {[3, 4, 5, 6].map((d) => (
                    <TouchableOpacity key={d} style={[styles.dayPill, fitDays === d && styles.dayPillOn]} onPress={() => setFitDays(d)}>
                      <Text style={[styles.dayPillText, fitDays === d && styles.dayPillTextOn]}>{d}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View style={styles.card}>
                {sectionKicker('RHYTHM')}
                <Text style={styles.cardTitle}>Sleep, workouts & screen time</Text>
                <Text style={styles.cardHint}>Used for reminders across modules.</Text>
                {timeRow('Wake', 'wake', wakeTime, setWakeTime)}
                {timeRow('Bed', 'sleep', sleepTime, setSleepTime)}
                {timeRow('Typical workout start', 'workout', workoutTime, setWorkoutTime)}
                <Text style={styles.inputLabel}>SCREEN TIME (DAILY)</Text>
                <View style={styles.tagWrap}>
                  {SCREEN_TIME_BANDS.map((b) => (
                    <TouchableOpacity key={b.id} style={[styles.tag, screenBand === b.id && styles.tagOn]} onPress={() => setScreenBand(b.id)}>
                      <Text style={[styles.tagText, screenBand === b.id && styles.tagTextOn]}>{b.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </>
          )}

          <View style={{ height: 100 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      <View style={styles.footer}>
        <TouchableOpacity style={[styles.saveBtn, loading && { opacity: 0.7 }]} onPress={handleSave} disabled={loading}>
          {loading ? <ActivityIndicator color={colors.background} /> : <Text style={styles.saveBtnText}>{onlyGoals ? 'Save Maxxes' : 'Save all changes'}</Text>}
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
  lead: {
    fontSize: 14,
    color: colors.textSecondary,
    lineHeight: 20,
    marginBottom: spacing.md,
  },
  content: { padding: spacing.xl },
  contentWide: { maxWidth: 560, alignSelf: 'center', width: '100%', paddingHorizontal: spacing.xxl },
  kicker: { ...typography.label, color: colors.textMuted, marginBottom: spacing.xs, letterSpacing: 1 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius['2xl'],
    padding: spacing.lg,
    marginTop: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.sm,
  },
  cardTitle: { fontSize: 18, fontWeight: '700', color: colors.foreground, marginBottom: spacing.xs },
  cardHint: { fontSize: 13, color: colors.textMuted, marginBottom: spacing.md, lineHeight: 18 },
  sectionTitle: { ...typography.h2, fontSize: 20, marginBottom: spacing.lg, marginTop: spacing.lg },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.xl, marginBottom: spacing.md },
  goalsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  goalCard: {
    width: '31%',
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'transparent',
    ...shadows.sm,
  },
  goalCardSelected: { backgroundColor: colors.accentMuted, borderColor: colors.foreground },
  goalLabel: { ...typography.caption, marginTop: spacing.xs, color: colors.textSecondary, textAlign: 'center' },
  goalLabelSelected: { color: colors.foreground, fontWeight: '600' },
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
  inputLabel: { ...typography.label, color: colors.textMuted, marginBottom: spacing.sm, marginTop: spacing.lg },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  chip: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  chipSelected: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  chipText: { ...typography.bodySmall, color: colors.textSecondary },
  chipTextSelected: { color: colors.background, fontWeight: '600' },
  inputGroup: { flexDirection: 'row', gap: spacing.lg },
  inputHalf: { flex: 1 },
  field: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    padding: spacing.lg,
    color: colors.foreground,
    fontSize: 16,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  list: { gap: spacing.md },
  listCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  listCardSelected: { backgroundColor: colors.accentMuted, borderColor: colors.foreground },
  listLabel: { ...typography.body, fontWeight: '600', color: colors.foreground },
  listDesc: { ...typography.caption, color: colors.textMuted, marginTop: 2 },
  rankRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  rankNum: { width: 28, fontWeight: '700', color: colors.textMuted },
  rankLabel: { flex: 1, fontSize: 16, color: colors.foreground, fontWeight: '600' },
  rankArrows: { flexDirection: 'row', gap: 4 },
  iconBtn: { padding: 6 },
  tagWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  tag: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tagOn: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  tagText: { fontSize: 13, fontWeight: '600', color: colors.textSecondary },
  tagTextOn: { color: colors.background },
  dayPill: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: borderRadius.full,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  dayPillOn: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  dayPillText: { fontSize: 14, fontWeight: '600', color: colors.textSecondary },
  dayPillTextOn: { color: colors.background },
  timeBlock: { marginBottom: spacing.sm },
  timeTrigger: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    paddingVertical: 14,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  timeTriggerText: { fontSize: 17, color: colors.foreground, fontWeight: '600' },
  timeDropdown: {
    marginTop: spacing.xs,
    maxHeight: 200,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
    overflow: 'hidden',
  },
  timeDropdownScroll: { maxHeight: 200 },
  timeOption: {
    paddingVertical: 11,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  timeOptionOn: { backgroundColor: colors.accentMuted },
  timeOptionText: { fontSize: 15, color: colors.textSecondary, fontWeight: '600' },
  timeOptionTextOn: { color: colors.foreground },
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
