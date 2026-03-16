import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Alert, TextInput, KeyboardAvoidingView, Platform, ActivityIndicator, useWindowDimensions } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const GOALS = [
  { id: 'bonemax', label: 'Bonemax', icon: 'fitness-outline' },
  { id: 'heightmax', label: 'Heightmax', icon: 'resize-outline' },
  { id: 'skinmax', label: 'Skinmax', icon: 'sparkles-outline' },
  { id: 'hairmax', label: 'Hairmax', icon: 'cut-outline' },
  { id: 'fitmax', label: 'Fitmax', icon: 'body-outline' },
];

const EXPERIENCE = [
  { id: 'beginner', label: 'Beginner', desc: 'Just getting started' },
  { id: 'intermediate', label: 'Intermediate', desc: 'Some experience' },
  { id: 'advanced', label: 'Advanced', desc: 'Experienced practitioner' },
];

const ACTIVITY_LEVELS = [
  { id: 'sedentary', label: 'Sedentary', desc: 'Little to no exercise' },
  { id: 'light', label: 'Light', desc: '1-3 days/week' },
  { id: 'moderate', label: 'Moderate', desc: '3-5 days/week' },
  { id: 'active', label: 'Active', desc: '6-7 days/week' },
];

const EQUIPMENT = [
  { id: 'none', label: 'None / Bodyweight', icon: 'hand-left' },
  { id: 'dumbbells', label: 'Dumbbells', icon: 'barbell' },
  { id: 'gym', label: 'Full Gym Access', icon: 'business' },
];

const SKIN_TYPES = [
  { id: 'oily', label: 'Oily' },
  { id: 'dry', label: 'Dry' },
  { id: 'combination', label: 'Combination' },
  { id: 'sensitive', label: 'Sensitive' },
];

export default function EditPersonalScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const { width } = useWindowDimensions();
  const isWide = width > 600;
  const { user, refreshUser } = useAuth();
  const [loading, setLoading] = useState(false);

  /** When true (e.g. from Home "Add More Maxxes"), only show and save goals. Onboarding info is edit-only from Profile. */
  const onlyGoals = route.params?.onlyGoals === true;

  // Initial Unit System
  const [unitSystem, setUnitSystem] = useState<'metric' | 'imperial'>((user?.onboarding?.unit_system as any) || 'metric');

  // Form State
  const [selectedGoals, setSelectedGoals] = useState<string[]>(user?.onboarding?.goals || []);
  const [gender, setGender] = useState(user?.onboarding?.gender || '');
  const [age, setAge] = useState(user?.onboarding?.age?.toString() || '');

  // Height & Weight handling
  const getInitialValues = () => {
    let h = '', hFt = '', hIn = '', w = '';
    const ob = user?.onboarding;
    if (ob) {
      if (unitSystem === 'imperial') {
        w = ob.weight ? (ob.weight * 2.20462).toFixed(1) : '';
        if (ob.height) {
          const totalInches = ob.height / 2.54;
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

  const [activityLevel, setActivityLevel] = useState(user?.onboarding?.activity_level || '');
  const [selectedEquipment, setSelectedEquipment] = useState<string[]>(user?.onboarding?.equipment || []);
  const [experience, setExperience] = useState(user?.onboarding?.experience_level || '');
  const [skinType, setSkinType] = useState(user?.onboarding?.skin_type || '');

  // Update state when user data loads or changes
  useEffect(() => {
    if (user?.onboarding) {
      const ob = user.onboarding;
      setUnitSystem((ob.unit_system as any) || 'metric');
      setSelectedGoals(ob.goals || []);
      setGender(ob.gender || '');
      setAge(ob.age?.toString() || '');
      setActivityLevel(ob.activity_level || '');
      setSelectedEquipment(ob.equipment || []);
      setExperience(ob.experience_level || '');
      setSkinType(ob.skin_type || '');
      
      // Update height and weight based on current unit system
      const currentUnitSystem = (ob.unit_system as any) || 'metric';
      if (currentUnitSystem === 'imperial') {
        if (ob.weight) {
          setWeight((ob.weight * 2.20462).toFixed(1));
        }
        if (ob.height) {
          const totalInches = ob.height / 2.54;
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
    }
  }, [user]);

  const handleSave = async () => {
    setLoading(true);

    let finalHeight: number | undefined = undefined;
    let finalWeight: number | undefined = undefined;

    if (unitSystem === 'imperial') {
      const ft = parseInt(heightFt) || 0;
      const inch = parseInt(heightIn) || 0;
      if (ft > 0 || inch > 0) {
        finalHeight = (ft * 30.48) + (inch * 2.54);
      }
      if (weight && parseFloat(weight) > 0) {
        finalWeight = parseFloat(weight) * 0.453592;
      }
    } else {
      if (height && parseFloat(height) > 0) {
        finalHeight = parseFloat(height);
      }
      if (weight && parseFloat(weight) > 0) {
        finalWeight = parseFloat(weight);
      }
    }

    // Prepare the data payload
    let onboardingData: any;

    if (onlyGoals) {
      // From Home "Add More Maxxes": only update goals, keep existing onboarding otherwise
      onboardingData = {
        ...(user?.onboarding || {}),
        goals: selectedGoals || [],
        timezone: user?.onboarding?.timezone || (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC'),
        completed: true
      };
    } else {
      onboardingData = {
        goals: selectedGoals || [],
        experience_level: experience || 'beginner',
        equipment: selectedEquipment || [],
        unit_system: unitSystem,
        timezone: user?.onboarding?.timezone || (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC'),
        completed: true
      };
      if (gender) onboardingData.gender = gender;
      if (age && !isNaN(parseInt(age)) && parseInt(age) > 0) onboardingData.age = parseInt(age);
      if (finalHeight !== undefined && finalHeight > 0) onboardingData.height = Math.round(finalHeight * 10) / 10;
      if (finalWeight !== undefined && finalWeight > 0) onboardingData.weight = Math.round(finalWeight * 10) / 10;
      if (activityLevel) onboardingData.activity_level = activityLevel;
      if (skinType) onboardingData.skin_type = skinType;
    }

    try {
      console.log('Saving onboarding data:', JSON.stringify(onboardingData, null, 2));
      const response = await api.saveOnboarding(onboardingData);
      console.log('Save response:', response);
      
      // Wait a bit to ensure backend has processed
      await new Promise(resolve => setTimeout(resolve, 500));
      
      await refreshUser();
      console.log('User refreshed after save');
      
      Alert.alert('Success', 'Profile updated successfully!');
      navigation.goBack();
    } catch (error: any) {
      console.error('Error saving onboarding:', error);
      console.error('Error response:', error?.response);
      console.error('Error response data:', error?.response?.data);
      
      let errorMessage = 'Could not save changes. Please try again.';
      
      if (error?.response?.data) {
        if (error.response.data.detail) {
          errorMessage = Array.isArray(error.response.data.detail) 
            ? error.response.data.detail.map((e: any) => e.msg || e).join(', ')
            : error.response.data.detail;
        } else if (error.response.data.message) {
          errorMessage = error.response.data.message;
        }
      } else if (error?.message) {
        errorMessage = error.message;
      }
      
      Alert.alert('Error', errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={colors.foreground} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{onlyGoals ? 'Your Maxxes' : 'Edit Personal Info'}</Text>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[styles.content, isWide && styles.contentWide]} showsVerticalScrollIndicator={false}>

          {/* Goals Section */}
          <Text style={styles.sectionTitle}>Your Goals</Text>
          <View style={styles.goalsGrid}>
            {GOALS.map((goal) => {
              const selected = selectedGoals.includes(goal.id);
              return (
                <TouchableOpacity
                  key={goal.id}
                  style={[styles.goalCard, selected && styles.goalCardSelected]}
                  onPress={() => setSelectedGoals(prev => prev.includes(goal.id) ? prev.filter(g => g !== goal.id) : [...prev, goal.id])}
                >
                  <Ionicons name={goal.icon as any} size={20} color={selected ? colors.foreground : colors.textMuted} />
                  <Text style={[styles.goalLabel, selected && styles.goalLabelSelected]}>{goal.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {onlyGoals ? (
            <View style={{ height: 80 }} />
          ) : (
            <>
          {/* Physical Section */}
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Physical Profile</Text>
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
            {['Male', 'Female', 'Other'].map(g => (
              <TouchableOpacity key={g} style={[styles.chip, gender === g && styles.chipSelected]} onPress={() => setGender(g)}>
                <Text style={[styles.chipText, gender === g && styles.chipTextSelected]}>{g}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={styles.inputGroup}>
            <View style={styles.inputHalf}>
              <Text style={styles.inputLabel}>AGE</Text>
              <TextInput style={styles.input} keyboardType="numeric" value={age} onChangeText={setAge} placeholder="Years" placeholderTextColor={colors.textMuted} />
            </View>
            <View style={styles.inputHalf}>
              <Text style={styles.inputLabel}>WEIGHT ({unitSystem === 'metric' ? 'KG' : 'LBS'})</Text>
              <TextInput style={styles.input} keyboardType="numeric" value={weight} onChangeText={setWeight} placeholder={unitSystem === 'metric' ? "kg" : "lbs"} placeholderTextColor={colors.textMuted} />
            </View>
          </View>

          <Text style={styles.inputLabel}>HEIGHT ({unitSystem === 'metric' ? 'CM' : 'FT/IN'})</Text>
          {unitSystem === 'metric' ? (
            <TextInput style={styles.input} keyboardType="numeric" value={height} onChangeText={setHeight} placeholder="cm" placeholderTextColor={colors.textMuted} />
          ) : (
            <View style={styles.inputGroup}>
              <View style={styles.inputHalf}><TextInput style={styles.input} keyboardType="numeric" value={heightFt} onChangeText={setHeightFt} placeholder="ft" placeholderTextColor={colors.textMuted} /></View>
              <View style={styles.inputHalf}><TextInput style={styles.input} keyboardType="numeric" value={heightIn} onChangeText={setHeightIn} placeholder="in" placeholderTextColor={colors.textMuted} /></View>
            </View>
          )}

          {/* Lifestyle Section */}
          <Text style={[styles.sectionTitle, { marginTop: spacing.xl }]}>Lifestyle</Text>

          <Text style={styles.inputLabel}>ACTIVITY LEVEL</Text>
          <View style={styles.list}>
            {ACTIVITY_LEVELS.map(level => (
              <TouchableOpacity key={level.id} style={[styles.listCard, activityLevel === level.id && styles.listCardSelected]} onPress={() => setActivityLevel(level.id)}>
                <View>
                  <Text style={styles.listLabel}>{level.label}</Text>
                  <Text style={styles.listDesc}>{level.desc}</Text>
                </View>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.inputLabel, { marginTop: spacing.lg }]}>EQUIPMENT ACCESS</Text>
          <View style={styles.chipRow}>
            {EQUIPMENT.map(item => {
              const selected = selectedEquipment.includes(item.id);
              return (
                <TouchableOpacity
                  key={item.id}
                  style={[styles.chip, selected && styles.chipSelected]}
                  onPress={() => setSelectedEquipment(prev => prev.includes(item.id) ? prev.filter(i => i !== item.id) : [...prev, item.id])}
                >
                  <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{item.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Last Details */}
          <Text style={[styles.sectionTitle, { marginTop: spacing.xl }]}>Experience & Skin</Text>

          <Text style={styles.inputLabel}>EXPERIENCE LEVEL</Text>
          <View style={styles.list}>
            {EXPERIENCE.map(exp => (
              <TouchableOpacity key={exp.id} style={[styles.listCard, experience === exp.id && styles.listCardSelected]} onPress={() => setExperience(exp.id)}>
                <View>
                  <Text style={styles.listLabel}>{exp.label}</Text>
                  <Text style={styles.listDesc}>{exp.desc}</Text>
                </View>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.inputLabel, { marginTop: spacing.lg }]}>SKIN TYPE</Text>
          <View style={styles.chipRow}>
            {SKIN_TYPES.map(type => (
              <TouchableOpacity key={type.id} style={[styles.chip, skinType === type.id && styles.chipSelected]} onPress={() => setSkinType(type.id)}>
                <Text style={[styles.chipText, skinType === type.id && styles.chipTextSelected]}>{type.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
            </>
          )}

          <View style={{ height: 100 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      <View style={styles.footer}>
        <TouchableOpacity style={[styles.saveBtn, loading && { opacity: 0.7 }]} onPress={handleSave} disabled={loading}>
          <Text style={styles.saveBtnText}>{loading ? 'Saving...' : onlyGoals ? 'Save Maxxes' : 'Save All Changes'}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingTop: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.borderLight
  },
  headerTitle: { ...typography.h3, color: colors.foreground },
  backButton: { padding: 4 },
  saveHeaderBtn: { padding: 4 },
  saveHeaderText: { fontSize: 16, fontWeight: '600', color: colors.accent },
  content: { padding: spacing.xl },
  contentWide: { maxWidth: 560, alignSelf: 'center', width: '100%', paddingHorizontal: spacing.xxl },
  sectionTitle: { ...typography.h2, fontSize: 20, marginBottom: spacing.lg, marginTop: spacing.lg },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.xxl, marginBottom: spacing.md },
  goalsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  goalCard: {
    width: '31%', backgroundColor: colors.card, borderRadius: borderRadius.lg,
    padding: spacing.lg, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: 'transparent', ...shadows.sm,
  },
  goalCardSelected: { backgroundColor: colors.accentMuted, borderColor: colors.foreground },
  goalLabel: { ...typography.caption, marginTop: spacing.xs, color: colors.textSecondary, textAlign: 'center' },
  goalLabelSelected: { color: colors.foreground, fontWeight: '600' },
  unitToggle: {
    flexDirection: 'row', backgroundColor: colors.card, borderRadius: borderRadius.full,
    padding: 4, borderWidth: 1, borderColor: colors.borderLight,
  },
  unitBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: borderRadius.full },
  unitBtnActive: { backgroundColor: colors.foreground },
  unitLabel: { fontSize: 12, fontWeight: '600', color: colors.textMuted },
  unitLabelActive: { color: colors.background },
  inputLabel: { ...typography.label, color: colors.textMuted, marginBottom: spacing.sm, marginTop: spacing.lg },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  chip: {
    paddingHorizontal: 18, paddingVertical: 10, borderRadius: borderRadius.full,
    backgroundColor: colors.card, borderWidth: 1, borderColor: colors.borderLight,
  },
  chipSelected: { backgroundColor: colors.foreground, borderColor: colors.foreground },
  chipText: { ...typography.bodySmall, color: colors.textSecondary },
  chipTextSelected: { color: colors.background, fontWeight: '600' },
  inputGroup: { flexDirection: 'row', gap: spacing.lg },
  inputHalf: { flex: 1 },
  input: {
    backgroundColor: colors.card, borderRadius: borderRadius.md, padding: spacing.lg,
    color: colors.foreground, fontSize: 16, borderWidth: 1, borderColor: colors.borderLight,
  },
  list: { gap: spacing.md },
  listCard: {
    backgroundColor: colors.card, borderRadius: borderRadius.lg, padding: spacing.lg,
    borderWidth: 1, borderColor: 'transparent',
  },
  listCardSelected: { backgroundColor: colors.accentMuted, borderColor: colors.foreground },
  listLabel: { ...typography.body, fontWeight: '600', color: colors.foreground },
  listDesc: { ...typography.caption, color: colors.textMuted, marginTop: 2 },
  footer: {
    padding: spacing.xl, paddingBottom: Platform.OS === 'ios' ? 40 : 24,
    backgroundColor: colors.background, borderTopWidth: 1, borderTopColor: colors.borderLight,
  },
  saveBtn: {
    backgroundColor: colors.foreground, borderRadius: borderRadius.full,
    paddingVertical: 18, alignItems: 'center', ...shadows.md,
  },
  saveBtnText: { ...typography.button, color: colors.background },
});
