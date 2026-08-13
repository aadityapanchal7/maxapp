/**
 * Onboarding v2 (flag `onboardingV2`) — a calm pass that learns the real shape
 * of someone's day so the scheduler can fit routines INTO their life instead of
 * on top of it.
 *
 * Aesthetic: Cal AI × Stoic. Soft gray canvas, white soft-shadow pill cards,
 * black-fill selection, centered bold headlines, a compact centered "Continue"
 * pill. Content is centered horizontally AND vertically on every screen. Every
 * choice option carries an icon (Cal AI). Times are set with a Stoic-style
 * wheel picker that slides up from the bottom. One decision per screen.
 *
 * The questions:
 *   1. Goals       — 5 maxx tiles, first tap = #1 priority, up to 3.
 *   2. Motivation  — one tap; Life-Model `motivation` (tunes Max's voice).
 *   3. Day shape   — wake / get-ready / wind-down (wheel picker rows).
 *   4. Work hours  — set weekday hours (toggle + start/end wheel rows).
 *   5. Where       — office/hybrid/home + commute  (only when they work).
 *   6. Meals       — breakfast / lunch / dinner, each with a skip toggle.
 *   7. Workout     — workout time (wheel picker row).
 *   8. Weekends    — same rhythm or shift later, icon cards.
 *   9. Shower      — when they usually shower (AM / PM / both), icon cards.
 *  10. Your day    — a read-only recap of the day we just learned.
 *
 * Saving (completed=false) triggers the backend starter-routine generation,
 * then we push RoutineReveal (RevealV2 renders behind the same route name).
 */
import React, { useEffect, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Modal,
    PanResponder,
    Platform,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Image as ExpoImage } from 'expo-image';

// Per-Max glossy icons (the same art used on Explore). Shown in the focus picker
// in place of flat glyphs.
const MAXX_THUMBS: Record<string, any> = {
    skinmax: require('../../assets/maxxThumbs/cut/skinmax.png'),
    fitmax: require('../../assets/maxxThumbs/cut/fitmax.png'),
    hairmax: require('../../assets/maxxThumbs/cut/hairmax.png'),
    heightmax: require('../../assets/maxxThumbs/cut/heightmax.png'),
    bonemax: require('../../assets/maxxThumbs/cut/bonemax.png'),
};
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
    Easing, Extrapolation, interpolate, useAnimatedStyle,
    useReducedMotion, useSharedValue, withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { track } from '../../lib/analytics';
import {
    saveOnboardingDraft,
    loadOnboardingDraft,
    clearOnboardingDraft,
} from '../../lib/onboardingDraft';

// Stable per-step keys for funnel analytics (title → slug), so step drop-off
// is queryable regardless of copy edits. Keep in sync with the step titles.
const STEP_KEYS: Record<string, string> = {
    'How old\nare you?': 'age',
    'You are…': 'gender',
    'What are we\nworking on?': 'goals',
    "What's pulling\nyou here?": 'motivation',
    'How hard do you\nwant to go?': 'effort',
    'The shape of\nyour day': 'day_shape',
    'Work or\nschool?': 'work',
    'Where do\nyou work?': 'work_location',
    'When do\nyou eat?': 'meals',
    'When do you\nwork out?': 'workout',
    'Weekends?': 'weekend_rhythm',
    'When do you\nusually shower?': 'shower',
    "Here's\nyour day": 'recap',
};

// Cal AI × Stoic palette — black ink, Stoic's soft gray canvas, white
// soft-shadow pill cards, black-fill selection.
const INK = '#000000';
const ON_INK = '#FFFFFF';        // text/icon on an ink-filled (selected) surface
const BG = '#F1F1EF';            // Stoic's soft off-white canvas
const CARD = '#FFFFFF';          // white pill card (lifts off the canvas)
const SUB = '#6B6B6B';           // secondary text
const MUTE = '#9A9A9A';          // tertiary / captions
const ICON_BG = '#F1F1EF';       // light circle behind a card icon (shows on white)
const TRACK = '#E2E1DE';         // progress / slider / toggle track on the canvas
const BACK_BG = '#FFFFFF';       // back-chevron circle (white on gray)
const DISABLED = '#DAD9D6';      // inactive Continue button
const DISABLED_TXT = '#A4A29D';
const HAIR = 'rgba(0,0,0,0.06)';   // hairline inside a white card
const WASH = 'rgba(0,0,0,0.05)';   // wheel centre band

// Stoic's soft, tactile lift under every white pill.
const SOFT = {
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
};

// One thin top progress bar that fills as the user advances.
function ProgressBar({ index, total }: { index: number; total: number }) {
    const p = useSharedValue((index + 1) / total);
    useEffect(() => {
        p.value = withTiming((index + 1) / total, { duration: 380, easing: Easing.out(Easing.cubic) });
    }, [index, total, p]);
    const style = useAnimatedStyle(() => ({ width: `${p.value * 100}%` }));
    return (
        <View style={styles.progressTrack}>
            <Animated.View style={[styles.progressFill, style]} />
        </View>
    );
}

// Stoic's compact, centered black "Continue" pill; solid gray when inactive.
function PrimaryButton({
    label,
    onPress,
    loading = false,
    disabled = false,
}: {
    label: string;
    onPress?: () => void;
    loading?: boolean;
    disabled?: boolean;
}) {
    const dim = disabled && !loading;
    return (
        <TouchableOpacity
            activeOpacity={0.9}
            onPress={onPress}
            disabled={disabled || loading}
            style={[styles.cta, dim && styles.ctaDisabled]}
            accessibilityRole="button"
            accessibilityLabel={label}
            accessibilityState={{ disabled: disabled || loading, busy: loading }}
        >
            {loading ? (
                <ActivityIndicator color={ON_INK} />
            ) : (
                <Text style={[styles.ctaText, dim && styles.ctaTextDisabled]}>{label}</Text>
            )}
        </TouchableOpacity>
    );
}

const MAXX_TILES = [
    { id: 'skinmax', token: 'skin', label: 'Skinmax', tagline: 'clearer, calmer skin', icon: 'sparkles-outline' },
    { id: 'fitmax', token: 'body', label: 'Fitmax', tagline: 'build your best body', icon: 'fitness-outline' },
    { id: 'hairmax', token: 'hair', label: 'Hairmax', tagline: 'fuller, healthier hair', icon: 'cut-outline' },
    { id: 'heightmax', token: 'height', label: 'Heightmax', tagline: 'posture and presence', icon: 'resize-outline' },
    { id: 'bonemax', token: 'face_structure', label: 'Bonemax', tagline: 'a sharper jaw and frame', icon: 'body-outline' },
] as const;

// Identity brackets (funnel V4). Multiple choice — a slider begs for lies;
// brackets are one honest tap.
const AGE_BANDS = ['Under 18', '18–24', '25–34', '35+'] as const;

const GENDERS = [
    { id: 'male', label: 'Male' },
    { id: 'female', label: 'Female' },
] as const;

// How hard they want to go — sets expectations before the paywall and feeds
// the scheduler's daily load.
const EFFORTS = [
    { id: 'light', label: 'Light touch', sub: 'some tips and tricks' },
    { id: 'steady', label: 'Steady', sub: 'tweaking my daily routine' },
    { id: 'all_in', label: 'All in', sub: 'becoming a new person' },
] as const;

const MOTIVATIONS = [
    { id: 'heartbreak', label: 'Someone broke my heart' },
    { id: 'no_respect', label: 'No one respects me' },
    { id: 'event', label: 'An upcoming date or event' },
    { id: 'mog', label: 'I just want to mog' },
    { id: 'curious', label: 'Just curious' },
    // Open-ended escape hatch — picking this reveals a text box so the real
    // reason isn't forced into one of the buckets above.
    { id: 'other', label: 'Something else' },
] as const;

// Each choice option carries its own icon (Cal AI style). When the user usually
// showers tells the scheduler where to anchor hygiene/skin routines — the AM
// get-ready window, the PM wind-down, or both.
const SHOWER_TIMES = [
    { id: 'morning', label: 'After I wake up', icon: 'sunny-outline' },
    { id: 'night', label: 'Before bed', icon: 'moon-outline' },
    { id: 'both', label: 'Both', icon: 'water-outline' },
] as const;

const WEEKENDS = [
    [true, 'I sleep in', 'bed-outline'],
    [false, 'Same rhythm', 'repeat-outline'],
] as const;

const LOCATIONS = [
    ['office', 'In office'],
    ['hybrid', 'Hybrid'],
    ['home', 'From home'],
] as const;

function fmt12(min: number): string {
    let h = Math.floor(min / 60);
    const m = min % 60;
    const suffix = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return `${h}:${String(m).padStart(2, '0')} ${suffix}`;
}

function hhmm(min: number): string {
    return `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;
}

// ── Stoic wheel time picker ────────────────────────────────────────────────
const ITEM_H = 44;
const VISIBLE = 5;
const HOURS = Array.from({ length: 12 }, (_, i) => String(i + 1));
const MINUTES = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'));
const PERIODS = ['AM', 'PM'];

function decompose(min: number) {
    const h24 = Math.floor(min / 60) % 24;
    const m = min % 60;
    const p = h24 >= 12 ? 1 : 0;
    const h12 = h24 % 12 || 12;
    return { h: h12 - 1, m, p };
}
function compose(hIdx: number, m: number, p: number) {
    const h12 = hIdx + 1;
    const base = h12 % 12;
    const h24 = p === 1 ? base + 12 : base;
    return ((h24 * 60) + m) % 1440;
}

// A single snapping column. Uncontrolled after its initial scroll position —
// reports the centred index up via onChange (fires on scroll, so it works on
// web where onMomentumScrollEnd may not).
function Wheel({
    values,
    initialIndex,
    onChange,
    width = 62,
    loop = false,
}: {
    values: string[];
    initialIndex: number;
    onChange: (i: number) => void;
    width?: number;
    // A looping column repeats its values so a value at the list's edge (e.g. the
    // 12 o'clock hour) still has neighbours in BOTH directions. Without this the
    // hour wheel dead-ends at 12: a midday default sits at the very bottom, so
    // scrolling "down" to pick a later time (1pm, 2pm…) hits a wall and the picker
    // feels capped at 12:59. Enabled for the hour column.
    loop?: boolean;
}) {
    const ref = useRef<ScrollView>(null);
    const inited = useRef(false);
    const N = values.length;
    // Render REPEATS copies and start centred in the middle copy; the committed
    // value is the scrolled index modulo N, so which copy you land on is irrelevant.
    // 5 copies give two full cycles of travel in each direction — a user never
    // reaches the ends in practice.
    const REPEATS = loop ? 5 : 1;
    const offset = loop ? N * Math.floor(REPEATS / 2) : 0;
    const display = loop
        ? Array.from({ length: N * REPEATS }, (_, i) => values[i % N])
        : values;
    const startIndex = offset + initialIndex;
    const [active, setActive] = useState(startIndex);
    const lastReal = useRef(initialIndex);

    const settle = (y: number) => {
        const raw = Math.max(0, Math.min(display.length - 1, Math.round(y / ITEM_H)));
        if (raw !== active) setActive(raw);
        const real = ((raw % N) + N) % N;
        if (real !== lastReal.current) { lastReal.current = real; onChange(real); }
    };

    return (
        <View style={{ width, height: ITEM_H * VISIBLE }}>
            <ScrollView
                ref={ref}
                showsVerticalScrollIndicator={false}
                snapToInterval={ITEM_H}
                decelerationRate="fast"
                scrollEventThrottle={16}
                onLayout={() => {
                    if (!inited.current) {
                        inited.current = true;
                        ref.current?.scrollTo({ y: startIndex * ITEM_H, animated: false });
                    }
                }}
                onScroll={(e) => settle(e.nativeEvent.contentOffset.y)}
                onMomentumScrollEnd={(e) => settle(e.nativeEvent.contentOffset.y)}
                contentContainerStyle={{ paddingVertical: ITEM_H * 2 }}
            >
                {display.map((v, i) => (
                    <View key={i} style={styles.wheelItem}>
                        <Text style={[styles.wheelText, i === active && styles.wheelTextActive]}>{v}</Text>
                    </View>
                ))}
            </ScrollView>
        </View>
    );
}

function TimePickerSheet({
    title,
    value,
    onClose,
    onConfirm,
}: {
    title: string;
    value: number;
    onClose: () => void;
    onConfirm: (v: number) => void;
}) {
    const init = decompose(value);
    const [h, setH] = useState(init.h);
    const [m, setM] = useState(init.m);
    const [p, setP] = useState(init.p);

    return (
        <Modal visible transparent animationType="slide" onRequestClose={onClose}>
            {/* Backdrop is a sibling BEHIND the sheet (not a parent), and the sheet
                is a plain View — NOT a TouchableOpacity. A touchable ancestor steals
                the pan gesture from the nested wheel ScrollViews on iOS, which is why
                the time couldn't be changed. */}
            <View style={styles.sheetBackdrop}>
                <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" />
                <View style={styles.sheet}>
                    <Text style={styles.sheetTitle}>{title}</Text>
                    <View style={styles.wheelRow}>
                        <View style={styles.wheelBand} pointerEvents="none" />
                        <Wheel values={HOURS} initialIndex={init.h} onChange={setH} loop />
                        <Wheel values={MINUTES} initialIndex={init.m} onChange={setM} />
                        <Wheel values={PERIODS} initialIndex={init.p} onChange={setP} width={56} />
                    </View>
                    <TouchableOpacity
                        style={styles.sheetDone}
                        activeOpacity={0.9}
                        onPress={() => onConfirm(compose(h, m, p))}
                        accessibilityRole="button"
                        accessibilityLabel="Done"
                    >
                        <Text style={styles.sheetDoneText}>Done</Text>
                    </TouchableOpacity>
                </View>
            </View>
        </Modal>
    );
}

// A Stoic notification-style row: small label, big time below, chevron right.
function TimeRow({
    label,
    caption,
    value,
    onPress,
}: {
    label: string;
    caption?: string;
    value: number;
    onPress: () => void;
}) {
    return (
        <TouchableOpacity
            style={styles.timeRow}
            onPress={onPress}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel={`${label}, ${fmt12(value)}`}
        >
            <View style={{ flex: 1 }}>
                <Text style={styles.timeRowLabel}>{label}</Text>
                {caption ? <Text style={styles.timeRowCaption}>{caption}</Text> : null}
            </View>
            <Text style={styles.timeRowValue}>{fmt12(value)}</Text>
            <Ionicons name="chevron-forward" size={18} color={MUTE} style={{ marginLeft: 8 }} />
        </TouchableOpacity>
    );
}

// Stoic-style switch — black when on (eating), gray when off (skipped).
function Toggle({ on, onToggle, label }: { on: boolean; onToggle: () => void; label: string }) {
    return (
        <TouchableOpacity
            onPress={onToggle}
            activeOpacity={0.85}
            style={[styles.toggle, on && styles.toggleOn]}
            accessibilityRole="switch"
            accessibilityState={{ checked: on }}
            accessibilityLabel={label}
        >
            <View style={styles.knob} />
        </TouchableOpacity>
    );
}

// A meal row: big time when kept, "Skipped" when off; a toggle on the right.
function MealRow({
    label,
    value,
    skipped,
    onToggleSkip,
    onPressTime,
}: {
    label: string;
    value: number;
    skipped: boolean;
    onToggleSkip: () => void;
    onPressTime: () => void;
}) {
    return (
        <View style={styles.timeRow}>
            <TouchableOpacity
                style={{ flex: 1 }}
                disabled={skipped}
                activeOpacity={0.7}
                onPress={onPressTime}
                accessibilityRole="button"
                accessibilityLabel={`${label}, ${skipped ? 'skipped' : fmt12(value)}`}
            >
                <Text style={styles.timeRowLabel}>{label}</Text>
                <Text style={[styles.timeRowValue, skipped && styles.timeRowValueDim]}>
                    {skipped ? 'Skipped' : fmt12(value)}
                </Text>
            </TouchableOpacity>
            <Toggle on={!skipped} onToggle={onToggleSkip} label={`Eat ${label.toLowerCase()}`} />
        </View>
    );
}

// A full-width icon choice card (Cal AI style). Single- or multi-select.
function OptionCard({
    icon,
    label,
    active,
    onPress,
    multi = false,
}: {
    icon: string;
    label: string;
    active: boolean;
    onPress: () => void;
    multi?: boolean;
}) {
    return (
        <TouchableOpacity
            style={[styles.tile, active && styles.tileActive]}
            onPress={onPress}
            activeOpacity={0.85}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            accessibilityLabel={label}
        >
            <View style={styles.tileIcon}>
                <Ionicons name={icon as any} size={19} color={INK} />
            </View>
            <Text style={[styles.tileLabel, { flex: 1 }, active && styles.tileLabelActive]}>{label}</Text>
            {multi && active ? <Ionicons name="checkmark-circle" size={22} color={ON_INK} /> : null}
        </TouchableOpacity>
    );
}

// A minimal, dependency-free slider (web + native via PanResponder).
const THUMB = 26;
function Slider({
    value,
    min,
    max,
    step,
    onChange,
    style,
}: {
    value: number;
    min: number;
    max: number;
    step: number;
    onChange: (v: number) => void;
    style?: any;
}) {
    const trackRef = useRef<View>(null);
    const wRef = useRef(0);
    const leftRef = useRef(0);

    const setFromAbsX = (absX: number) => {
        const w = wRef.current;
        if (w <= 0) return;
        const ratio = Math.max(0, Math.min(1, (absX - leftRef.current) / w));
        const snapped = Math.round((min + ratio * (max - min)) / step) * step;
        const clamped = Math.max(min, Math.min(max, snapped));
        onChange(clamped);
    };

    const pan = useRef(
        PanResponder.create({
            onStartShouldSetPanResponder: () => true,
            onMoveShouldSetPanResponder: () => true,
            onPanResponderTerminationRequest: () => false,
            onPanResponderGrant: (e) => {
                trackRef.current?.measure((_x, _y, w, _h, pageX) => {
                    wRef.current = w;
                    leftRef.current = pageX;
                    setFromAbsX(e.nativeEvent.pageX);
                });
            },
            onPanResponderMove: (e) => setFromAbsX(e.nativeEvent.pageX),
        }),
    ).current;

    const pct = max > min ? (value - min) / (max - min) : 0;
    const [w, setW] = useState(0);
    const thumbLeft = Math.max(0, pct * (w - THUMB));

    return (
        <View
            ref={trackRef}
            style={[styles.sliderWrap, style]}
            onLayout={(e) => { wRef.current = e.nativeEvent.layout.width; setW(e.nativeEvent.layout.width); }}
            {...pan.panHandlers}
        >
            <View style={styles.sliderTrack} />
            <View style={[styles.sliderFill, { width: thumbLeft + THUMB / 2 }]} />
            <View style={[styles.sliderThumb, { left: thumbLeft }]} />
        </View>
    );
}

// Funnel V4 phases. The scan capture is the FIRST thing after "Get started"
// (RootNavigator boots new users into FaceScan), so the whole question run
// doubles as loading time for the analysis:
//   intro    — age, gender, goals, motivation, effort (scan analyzes behind
//              them) → results gate → paywall → account
//   schedule — day-shape/work/meals/… after purchase + account → finish → Main
export type OnboardingPhase = 'intro' | 'schedule';

export default function OnboardingV2Screen() {
    const navigation = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { user, isPaid, isFreeTier, chooseFreeTier, refreshUser } = useAuth();

    const [step, setStep] = useState(0);
    const [dir, setDir] = useState(1); // +1 forward, -1 back — drives slide direction
    const [phase, setPhase] = useState<OnboardingPhase>(route?.params?.phase ?? 'intro');
    // Set when the user declined the scan at the offer screen — the intro run
    // then ends at the paywall instead of the (scan-less) results gate.
    const [scanSkipped, setScanSkipped] = useState<boolean>(!!route?.params?.scanSkipped);
    const [ageBand, setAgeBand] = useState<string | null>(null);
    const [gender, setGender] = useState<string | null>(null);
    const [effort, setEffort] = useState<string | null>(null);
    const [goals, setGoals] = useState<string[]>([]);
    const [motivation, setMotivation] = useState<string | null>(null);
    // Free-text reason when motivation === 'other' (the custom answer path).
    const [motivationOther, setMotivationOther] = useState('');
    const [wakeMin, setWakeMin] = useState(7 * 60);
    // Get-ready (AM routine) + wind-down (PM routine) are WINDOWS, not a time +
    // duration / a single bedtime. The wind-down window's END is bedtime.
    const [grStart, setGrStart] = useState(7 * 60);
    const [grEnd, setGrEnd] = useState(7 * 60 + 30);
    const [wdStart, setWdStart] = useState(22 * 60 + 15);
    const [wdEnd, setWdEnd] = useState(23 * 60);
    const [works, setWorks] = useState(true);
    const [workStartMin, setWorkStartMin] = useState(9 * 60);
    const [workEndMin, setWorkEndMin] = useState(17 * 60);
    const [workLocation, setWorkLocation] = useState<string>('office');
    const [commuteMin, setCommuteMin] = useState<number>(30);
    const [breakfastMin, setBreakfastMin] = useState(8 * 60);
    const [lunchMin, setLunchMin] = useState(12 * 60 + 30);
    const [dinnerMin, setDinnerMin] = useState(19 * 60);
    const [skipBreakfast, setSkipBreakfast] = useState(false);
    const [skipLunch, setSkipLunch] = useState(false);
    const [skipDinner, setSkipDinner] = useState(false);
    const [showerTime, setShowerTime] = useState<string | null>(null);
    const [workoutMin, setWorkoutMin] = useState(7 * 60); // 7 AM default
    const [weekendShift, setWeekendShift] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // Gates the first render until any saved draft is restored — without it the
    // wizard would flash step 0 / default answers before the saved step loads.
    const [draftLoaded, setDraftLoaded] = useState(false);

    // Restore an interrupted onboarding on mount. Each field is applied only
    // when present + the right type, so a partial/old draft falls back to
    // defaults instead of crashing.
    useEffect(() => {
        let cancelled = false;
        void loadOnboardingDraft()
            .then((d) => {
                if (cancelled || !d) return;
                const a = d.answers || {};
                if (typeof a.scanSkipped === 'boolean' && !route?.params?.scanSkipped) setScanSkipped(a.scanSkipped);
                if (typeof a.ageBand === 'string') setAgeBand(a.ageBand);
                if (typeof a.gender === 'string') setGender(a.gender);
                if (typeof a.effort === 'string') setEffort(a.effort);
                if (Array.isArray(a.goals)) setGoals(a.goals);
                if (a.motivation === null || typeof a.motivation === 'string') setMotivation(a.motivation);
                if (typeof a.motivationOther === 'string') setMotivationOther(a.motivationOther);
                if (typeof a.wakeMin === 'number') setWakeMin(a.wakeMin);
                if (typeof a.grStart === 'number') setGrStart(a.grStart);
                if (typeof a.grEnd === 'number') setGrEnd(a.grEnd);
                if (typeof a.wdStart === 'number') setWdStart(a.wdStart);
                if (typeof a.wdEnd === 'number') setWdEnd(a.wdEnd);
                if (typeof a.works === 'boolean') setWorks(a.works);
                if (typeof a.workStartMin === 'number') setWorkStartMin(a.workStartMin);
                if (typeof a.workEndMin === 'number') setWorkEndMin(a.workEndMin);
                if (typeof a.workLocation === 'string') setWorkLocation(a.workLocation);
                if (typeof a.commuteMin === 'number') setCommuteMin(a.commuteMin);
                if (typeof a.breakfastMin === 'number') setBreakfastMin(a.breakfastMin);
                if (typeof a.lunchMin === 'number') setLunchMin(a.lunchMin);
                if (typeof a.dinnerMin === 'number') setDinnerMin(a.dinnerMin);
                if (typeof a.skipBreakfast === 'boolean') setSkipBreakfast(a.skipBreakfast);
                if (typeof a.skipLunch === 'boolean') setSkipLunch(a.skipLunch);
                if (typeof a.skipDinner === 'boolean') setSkipDinner(a.skipDinner);
                if (typeof a.showerTime === 'string') setShowerTime(a.showerTime);
                if (typeof a.workoutMin === 'number') setWorkoutMin(a.workoutMin);
                if (typeof a.weekendShift === 'boolean') setWeekendShift(a.weekendShift);
                // Resume into the phase the user left — unless the navigator
                // explicitly routed here with a phase param (hand-off wins).
                if (!route?.params?.phase && (d.phase === 'intro' || d.phase === 'schedule')) {
                    setPhase(d.phase);
                }
                // Only restore the step INDEX when the draft's phase matches the
                // phase we're actually resuming into: step indices are relative
                // to a phase's own slice, so an intro draft's step applied to
                // the schedule phase (post-claim hand-off) silently skipped its
                // first questions (day-shape / work / meals).
                const effectivePhase =
                    route?.params?.phase ?? (d.phase === 'intro' || d.phase === 'schedule' ? d.phase : 'intro');
                if (typeof d.step === 'number' && d.step >= 0 && d.phase === effectivePhase) {
                    setStep(d.step);
                }
            })
            .catch(() => undefined)
            .finally(() => {
                if (!cancelled) setDraftLoaded(true);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    // Persist the draft after every change (only once the initial restore has
    // run, so we never overwrite a saved draft with the default state before
    // it's loaded). Fire-and-forget; onboarding edits aren't high-frequency.
    useEffect(() => {
        if (!draftLoaded) return;
        void saveOnboardingDraft(step, {
            scanSkipped, ageBand, gender, effort,
            goals, motivation, motivationOther, wakeMin, grStart, grEnd, wdStart, wdEnd, works,
            workStartMin, workEndMin, workLocation, commuteMin,
            breakfastMin, lunchMin, dinnerMin, skipBreakfast, skipLunch, skipDinner,
            showerTime, workoutMin, weekendShift,
        }, phase);
    }, [
        draftLoaded, step, phase, scanSkipped, ageBand, gender, effort,
        goals, motivation, motivationOther, wakeMin, grStart, grEnd, wdStart, wdEnd, works,
        workStartMin, workEndMin, workLocation, commuteMin,
        breakfastMin, lunchMin, dinnerMin, skipBreakfast, skipLunch, skipDinner,
        showerTime, workoutMin, weekendShift,
    ]);

    // Hand-offs back into the wizard (FaceScan → effort, CreateAccount →
    // schedule) arrive as a route-param change on the already-mounted screen.
    useEffect(() => {
        const p = route?.params?.phase;
        if ((p === 'intro' || p === 'schedule') && p !== phase) {
            setDir(1);
            setPhase(p);
            setStep(0);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [route?.params?.phase]);

    // Wheel picker — `picker` holds the field currently being edited. A bumping
    // key forces a fresh sheet (correct initial scroll) every time one opens.
    const [picker, setPicker] = useState<{ title: string; value: number; onSave: (v: number) => void } | null>(null);
    const [pickerKey, setPickerKey] = useState(0);
    const openTime = (title: string, value: number, onSave: (v: number) => void) => {
        // Never re-present while a sheet is already up: bumping `pickerKey` would
        // remount the native <Modal>, overlapping the old sheet's dismiss with the
        // new sheet's present — the classic iOS two-modal deadlock that freezes the
        // whole JS thread (every tap, incl. the DEV launcher, stops registering).
        if (picker) return;
        setPicker({ title, value, onSave });
        setPickerKey((k) => k + 1);
        if (Platform.OS !== 'web') Haptics.selectionAsync().catch(() => {});
    };

    const toggleGoal = (id: string) => {
        setGoals((g) =>
            g.includes(id) ? g.filter((x) => x !== id) : g.length < 3 ? [...g, id] : g,
        );
    };

    const hasCommute = works && workLocation !== 'home';

    // Keep each routine window inside a sane envelope and ordered (end after
    // start), matching the planner's editable ranges so onboarding can never
    // write a window the planner can't represent.
    //   Get-ready: 04:00–13:00 (all morning, no midnight wrap).
    //   Wind-down: 18:00–02:00, evening-normalised so a past-midnight bedtime
    //   still orders correctly.
    const GR_MIN = 4 * 60, GR_MAX = 13 * 60;
    const WD_LO = 18 * 60, WD_HI = 26 * 60; // 6 PM .. 2 AM (eve-normalised)
    const eve = (m: number) => (m < 4 * 60 ? m + 1440 : m); // 04:00 = day boundary
    const fromEve = (e: number) => e % 1440;
    const clampGr = (m: number) => Math.max(GR_MIN, Math.min(GR_MAX, m));
    const clampWdEve = (m: number) => Math.max(WD_LO, Math.min(WD_HI, eve(m)));
    // Get-ready / wind-down: the user only picks when each STARTS — the duration
    // doesn't matter to them, so we derive the window's end from a sensible
    // default (get-ready 30 min; wind-down 45 min → bedtime) to keep the window
    // payload the planner/scheduler expects valid.
    const GR_DUR = 30, WD_DUR = 45;
    const onGrStart = (v: number) => { const s = clampGr(v); setGrStart(s); setGrEnd(clampGr(s + GR_DUR)); };
    const onWdStart = (v: number) => { const se = clampWdEve(v); setWdStart(fromEve(se)); setWdEnd(fromEve(Math.min(WD_HI, se + WD_DUR))); };

    // Funnel V4: everything before the scan hand-off, persisted early so the
    // scan analysis + paywall personalization can read it (fire-and-forget —
    // a transient failure must never block the funnel; finish() re-sends it all).
    const introPayload = () => ({
        goals,
        priority_order: goals
            .map((id) => MAXX_TILES.find((t) => t.id === id)?.token)
            .filter(Boolean) as string[],
        motivation,
        motivation_other: motivation === 'other' ? motivationOther.trim() : null,
        age_band: ageBand,
        gender,
        completed: false,
    });

    const finish = async () => {
        setSaving(true);
        setError(null);
        const tokens = goals
            .map((id) => MAXX_TILES.find((t) => t.id === id)?.token)
            .filter(Boolean) as string[];
        const payload = {
                age_band: ageBand,
                gender,
                effort_level: effort,
                goals,
                priority_order: tokens,
                motivation,
                // Free-text reason when "Something else" was picked (custom path).
                motivation_other: motivation === 'other' ? motivationOther.trim() : null,
                wake_time: hhmm(wakeMin),
                // Get-ready (AM routine) window — keep legacy scalars in sync.
                get_ready_window: [hhmm(grStart), hhmm(grEnd)],
                get_ready_time: hhmm(grStart),
                get_ready_minutes: Math.max(5, ((grEnd - grStart + 1440) % 1440) || 30),
                // Wind-down (PM routine) window — bedtime is its end.
                wind_down_window: [hhmm(wdStart), hhmm(wdEnd)],
                sleep_window: [hhmm(wdStart), hhmm(wdEnd)],
                sleep_time: hhmm(wdEnd),
                obligations: works
                    ? [{ label: 'Work', start: hhmm(workStartMin), end: hhmm(workEndMin), days: 'weekdays' }]
                    : [],
                work_location: works ? workLocation : 'home',
                commute_minutes: hasCommute ? commuteMin : 0,
                breakfast_time: skipBreakfast ? null : hhmm(breakfastMin),
                lunch_time: skipLunch ? null : hhmm(lunchMin),
                dinner_time: skipDinner ? null : hhmm(dinnerMin),
                meals_skipped: [
                    skipBreakfast && 'breakfast',
                    skipLunch && 'lunch',
                    skipDinner && 'dinner',
                ].filter(Boolean) as string[],
                shower_time: showerTime,
                workout_time: hhmm(workoutMin),
                weekend_shift: weekendShift,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
                // V4: the schedule questions are the LAST funnel step (post-pay,
                // post-account), so finishing them completes onboarding outright —
                // the navigator remounts onto Main. No reveal step.
                completed: true,
            };
        const goHome = async () => {
            track('onboarding_step', {
                step: 'completed',
                goals,
                motivation,
                has_work: works,
            });
            // Onboarding is done — drop the resume draft so a later relaunch
            // doesn't drag the user back into the wizard.
            void clearOnboardingDraft();
            // Flipping onboarding.completed makes treatAsFull true → the
            // navigator remounts onto Main (Home). AWAIT the refresh (retry once
            // on a transient blip) so a paid user reliably lands home even if
            // getMe hiccups. treatAsFull ALSO requires paid||free-tier — but the
            // schedule questions are the LAST funnel step (V4: paywall → account
            // → schedule → Main), so anyone finishing here is already PAST the
            // hard paywall. A user who reaches this point yet is neither paid nor
            // free-tier (a dev bypass, or a funnel edge) must NOT be bounced
            // BACKWARD into Payment → "Save your results" (they already did the
            // account step) — grant browse-only free-tier so treatAsFull flips
            // and the navigator remounts straight onto Home. Paid features stay
            // gated at point-of-use by usePaywallGate.
            let fresh: any = null;
            for (let i = 0; i < 2 && !fresh; i++) {
                fresh = await refreshUser().catch(() => null);
                if (!fresh && i === 0) await new Promise((r) => setTimeout(r, 600));
            }
            const willBeFull =
                ((fresh?.is_paid ?? user?.is_paid ?? isPaid) === true) || isFreeTier;
            if (!willBeFull) {
                await chooseFreeTier().catch(() => {});
            }
        };
        try {
            await api.saveOnboarding(payload as any);
            goHome();
        } catch (e: any) {
            // On the computer/web dev build, don't trap the user behind a save
            // failure (e.g. no local backend) — proceed with the answers in
            // hand, exactly as a successful save would. Native/prod still
            // surfaces the real error so a genuine failure isn't hidden.
            if (Platform.OS === 'web' && __DEV__) {
                goHome();
            } else {
                setError("Couldn't save. Check your connection and try again.");
            }
        } finally {
            setSaving(false);
        }
    };

    // Built day-order, then sorted chronologically by start time so meals fall
    // where they actually happen (stable sort keeps Wake before a same-minute
    // Get ready, etc.).
    const recap: { icon: string; label: string; value: string; sort: number }[] = [
        { icon: 'sunny-outline', label: 'Wake', value: fmt12(wakeMin), sort: wakeMin },
        { icon: 'water-outline', label: 'Get ready', value: fmt12(grStart), sort: grStart },
        ...(works
            ? [{ icon: 'briefcase-outline', label: 'Work', value: `${fmt12(workStartMin)} – ${fmt12(workEndMin)}`, sort: workStartMin }]
            : []),
        ...(hasCommute
            ? [{ icon: 'car-outline', label: 'Commute', value: `${commuteMin} min each way`, sort: workStartMin - commuteMin }]
            : []),
        { icon: 'barbell-outline', label: 'Workout', value: fmt12(workoutMin), sort: workoutMin },
        ...(!skipBreakfast ? [{ icon: 'cafe-outline', label: 'Breakfast', value: fmt12(breakfastMin), sort: breakfastMin }] : []),
        ...(!skipLunch ? [{ icon: 'restaurant-outline', label: 'Lunch', value: fmt12(lunchMin), sort: lunchMin }] : []),
        ...(!skipDinner ? [{ icon: 'wine-outline', label: 'Dinner', value: fmt12(dinnerMin), sort: dinnerMin }] : []),
        { icon: 'moon-outline', label: 'Wind down', value: fmt12(wdStart), sort: wdStart },
    ].sort((a, b) => a.sort - b.sort);

    // Single-choice steps auto-advance ~a beat after the tap (the back chevron
    // is always there if they mis-tap). goNext is defined below the steps
    // array, so route the call through a ref to dodge the ordering.
    const goNextRef = useRef<() => void>(() => {});
    const autoNext = () => setTimeout(() => goNextRef.current(), 240);

    // One idea per screen. The "Where you work" step only exists when the user
    // works — it's spread in conditionally; the progress bar adapts to length.
    const allSteps = [
        // 0 — age (identity bracket)
        {
            title: 'How old\nare you?',
            sub: 'Your plan is calibrated to where you are.',
            canNext: !!ageBand,
            auto: true,
            body: (
                <View style={{ gap: 10 }}>
                    {AGE_BANDS.map((a) => {
                        const active = ageBand === a;
                        return (
                            <TouchableOpacity
                                key={a}
                                style={[styles.tile, active && styles.tileActive]}
                                onPress={() => { setAgeBand(a); autoNext(); }}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityState={{ selected: active }}
                                accessibilityLabel={a}
                            >
                                <Text style={[styles.tileLabel, styles.tileLabelCenter, active && styles.tileLabelActive]}>{a}</Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>
            ),
        },
        // 1 — gender
        {
            title: 'You are…',
            sub: 'Facial analysis differs by bone structure.',
            canNext: !!gender,
            auto: true,
            body: (
                <View style={{ gap: 10 }}>
                    {GENDERS.map((g) => {
                        const active = gender === g.id;
                        return (
                            <TouchableOpacity
                                key={g.id}
                                style={[styles.tile, active && styles.tileActive]}
                                onPress={() => { setGender(g.id); autoNext(); }}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityState={{ selected: active }}
                                accessibilityLabel={g.label}
                            >
                                <Text style={[styles.tileLabel, styles.tileLabelCenter, active && styles.tileLabelActive]}>{g.label}</Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>
            ),
        },
        // 2 — goals
        {
            title: 'What are we\nworking on?',
            sub: 'Pick up to 3.',
            canNext: goals.length > 0,
            body: (
                <View style={{ gap: 10 }}>
                    {MAXX_TILES.map((t) => {
                        const idx = goals.indexOf(t.id);
                        const active = idx >= 0;
                        return (
                            <TouchableOpacity
                                key={t.id}
                                style={[styles.tile, active && styles.tileActive]}
                                onPress={() => toggleGoal(t.id)}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityState={{ selected: active }}
                                accessibilityLabel={t.label}
                            >
                                <View style={styles.tileIcon}>
                                    {MAXX_THUMBS[t.id] ? (
                                        <ExpoImage source={MAXX_THUMBS[t.id]} style={styles.tileThumb} contentFit="contain" />
                                    ) : (
                                        <Ionicons name={t.icon as any} size={19} color={INK} />
                                    )}
                                </View>
                                <View style={{ flex: 1 }}>
                                    <Text style={[styles.tileLabel, active && styles.tileLabelActive]}>{t.label}</Text>
                                    <Text style={[styles.tileTag, active && styles.tileTagActive]}>{t.tagline}</Text>
                                </View>
                                {active ? (
                                    <View style={styles.rankBadge}>
                                        <Text style={styles.rankText}>{idx + 1}</Text>
                                    </View>
                                ) : null}
                            </TouchableOpacity>
                        );
                    })}
                </View>
            ),
        },
        // 2 — motivation
        {
            title: "What's pulling\nyou here?",
            sub: 'It helps Max talk to you straight.',
            // When "Something else" is picked, require a non-empty typed reason.
            canNext: !!motivation && (motivation !== 'other' || motivationOther.trim().length > 0),
            // Auto-advance on a bucket tap; "Something else" needs the text box
            // + an explicit Continue.
            auto: motivation !== 'other',
            body: (
                <View style={{ gap: 10 }}>
                    {MOTIVATIONS.map((m) => {
                        const active = motivation === m.id;
                        return (
                            <TouchableOpacity
                                key={m.id}
                                style={[styles.tile, active && styles.tileActive]}
                                onPress={() => { setMotivation(m.id); if (m.id !== 'other') autoNext(); }}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityState={{ selected: active }}
                                accessibilityLabel={m.label}
                            >
                                <Text style={[styles.tileLabel, styles.tileLabelCenter, active && styles.tileLabelActive]}>{m.label}</Text>
                            </TouchableOpacity>
                        );
                    })}
                    {motivation === 'other' && (
                        <TextInput
                            style={styles.otherInput}
                            value={motivationOther}
                            onChangeText={setMotivationOther}
                            placeholder="Tell Max in your own words…"
                            placeholderTextColor={MUTE}
                            autoFocus
                            multiline
                            maxLength={140}
                            accessibilityLabel="Your reason"
                        />
                    )}
                </View>
            ),
        },
        // 4 — effort (asked while the scan analyzes in the background)
        {
            title: 'How hard do you\nwant to go?',
            sub: 'The plan flexes to match — you can change this later.',
            canNext: !!effort,
            auto: true,
            body: (
                <View style={{ gap: 10 }}>
                    {EFFORTS.map((e) => {
                        const active = effort === e.id;
                        return (
                            <TouchableOpacity
                                key={e.id}
                                style={[styles.tile, active && styles.tileActive]}
                                onPress={() => { setEffort(e.id); autoNext(); }}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityState={{ selected: active }}
                                accessibilityLabel={e.label}
                            >
                                <View style={{ flex: 1 }}>
                                    <Text style={[styles.tileLabel, active && styles.tileLabelActive]}>{e.label}</Text>
                                    <Text style={[styles.tileTag, active && styles.tileTagActive]}>{e.sub}</Text>
                                </View>
                            </TouchableOpacity>
                        );
                    })}
                </View>
            ),
        },
        // 5 — day shape
        {
            title: 'The shape of\nyour day',
            sub: 'Max builds around your real hours, not over them.',
            canNext: true,
            body: (
                <View style={styles.shapeCard}>
                    <TimeRow label="Wake around" value={wakeMin} onPress={() => openTime('Wake around', wakeMin, setWakeMin)} />
                    <View style={styles.hairline} />
                    <TimeRow label="Get ready" caption="When your morning routine starts" value={grStart} onPress={() => openTime('Get ready', grStart, onGrStart)} />
                    <View style={styles.hairline} />
                    <TimeRow label="Wind down" caption="When your nighttime routine starts" value={wdStart} onPress={() => openTime('Wind down', wdStart, onWdStart)} />
                </View>
            ),
        },
        // 4 — work hours
        {
            title: 'Work or\nschool?',
            sub: 'So nothing ever gets scheduled over it.',
            canNext: true,
            body: (
                <View>
                    <TouchableOpacity
                        style={[styles.workChip, works && styles.workChipActive]}
                        onPress={() => setWorks((w) => !w)}
                        accessibilityRole="button"
                        accessibilityState={{ selected: works }}
                        accessibilityLabel="I have set weekday hours"
                    >
                        <Ionicons
                            name={works ? 'checkmark-circle' : 'ellipse-outline'}
                            size={18}
                            color={works ? ON_INK : MUTE}
                        />
                        <Text style={[styles.workChipText, works && styles.workChipTextActive]}>I have set weekday hours</Text>
                    </TouchableOpacity>

                    {works ? (
                        <View style={[styles.shapeCard, { marginTop: 12 }]}>
                            <TimeRow label="Starts" value={workStartMin} onPress={() => openTime('Work starts', workStartMin, setWorkStartMin)} />
                            <View style={styles.hairline} />
                            <TimeRow label="Ends" value={workEndMin} onPress={() => openTime('Work ends', workEndMin, setWorkEndMin)} />
                        </View>
                    ) : null}
                </View>
            ),
        },
        // 5 — where you work (only when they work)
        ...(works
            ? [{
                title: 'Where do\nyou work?',
                sub: 'Your commute becomes real protected time, not a guess.',
                canNext: true,
                body: (
                    <View>
                        <View style={styles.seg}>
                            {LOCATIONS.map(([id, label]) => {
                                const active = workLocation === id;
                                return (
                                    <TouchableOpacity
                                        key={id}
                                        style={[styles.segItem, active && styles.segItemActive]}
                                        onPress={() => setWorkLocation(id)}
                                        accessibilityRole="button"
                                        accessibilityState={{ selected: active }}
                                        accessibilityLabel={label}
                                    >
                                        <Text style={[styles.segText, active && styles.segTextActive]}>
                                            {label}
                                        </Text>
                                    </TouchableOpacity>
                                );
                            })}
                        </View>

                        {workLocation !== 'home' ? (
                            <View style={styles.commuteWrap}>
                                <View style={styles.commuteHead}>
                                    <Text style={[styles.groupLabel, styles.groupLabelInRow]}>COMMUTE EACH WAY</Text>
                                    <Text style={styles.commuteValue}>
                                        {commuteMin >= 60 ? '60+ min' : `${commuteMin} min`}
                                    </Text>
                                </View>
                                <Slider
                                    value={commuteMin}
                                    min={15}
                                    max={60}
                                    step={5}
                                    onChange={setCommuteMin}
                                />
                                <View style={styles.sliderEnds}>
                                    <Text style={styles.sliderEndText}>15 min</Text>
                                    <Text style={styles.sliderEndText}>60+ min</Text>
                                </View>
                            </View>
                        ) : null}
                    </View>
                ),
            }]
            : []),
        // 6 — meals
        {
            title: 'When do\nyou eat?',
            sub: 'Max keeps your routines clear of the meals you keep.',
            canNext: true,
            body: (
                <View>
                    <View style={styles.shapeCard}>
                        <MealRow
                            label="Breakfast"
                            value={breakfastMin}
                            skipped={skipBreakfast}
                            onToggleSkip={() => setSkipBreakfast((s) => !s)}
                            onPressTime={() => openTime('Breakfast', breakfastMin, setBreakfastMin)}
                        />
                        <View style={styles.hairline} />
                        <MealRow
                            label="Lunch"
                            value={lunchMin}
                            skipped={skipLunch}
                            onToggleSkip={() => setSkipLunch((s) => !s)}
                            onPressTime={() => openTime('Lunch', lunchMin, setLunchMin)}
                        />
                        <View style={styles.hairline} />
                        <MealRow
                            label="Dinner"
                            value={dinnerMin}
                            skipped={skipDinner}
                            onToggleSkip={() => setSkipDinner((s) => !s)}
                            onPressTime={() => openTime('Dinner', dinnerMin, setDinnerMin)}
                        />
                    </View>
                    <Text style={styles.helpNote}>
                        Toggle off any meal you don't eat — that frees the time for your routines.
                    </Text>
                </View>
            ),
        },
        // 7 — workout time
        {
            title: 'When do you\nwork out?',
            sub: 'So things land when they actually happen.',
            canNext: true,
            body: (
                <View style={styles.shapeCard}>
                    <TouchableOpacity
                        style={styles.timeRow}
                        activeOpacity={0.7}
                        onPress={() => openTime('When do you work out?', workoutMin, setWorkoutMin)}
                        accessibilityRole="button"
                        accessibilityLabel={`Workout time, ${fmt12(workoutMin)}`}
                    >
                        <View style={{ flex: 1 }}>
                            <Text style={styles.timeRowLabel}>Workout</Text>
                            <Text style={styles.timeRowValue}>{fmt12(workoutMin)}</Text>
                        </View>
                    </TouchableOpacity>
                </View>
            ),
        },
        // 8 — weekend rhythm
        {
            title: 'Weekends?',
            sub: 'Do you keep the same schedule, or shift things later?',
            canNext: true,
            auto: true,
            body: (
                <View style={{ gap: 10 }}>
                    {WEEKENDS.map(([val, label, icon]) => (
                        <OptionCard
                            key={label}
                            icon={icon}
                            label={label}
                            active={weekendShift === val}
                            onPress={() => { setWeekendShift(val); autoNext(); }}
                        />
                    ))}
                </View>
            ),
        },
        // 9 — shower timing (single-select; anchors hygiene/skin routines)
        {
            title: 'When do you\nusually shower?',
            sub: 'So Max anchors your skin and hygiene routines at the right time.',
            canNext: !!showerTime,
            auto: true,
            body: (
                <View style={{ gap: 10 }}>
                    {SHOWER_TIMES.map((s) => (
                        <OptionCard
                            key={s.id}
                            icon={s.icon}
                            label={s.label}
                            active={showerTime === s.id}
                            onPress={() => { setShowerTime(s.id); autoNext(); }}
                        />
                    ))}
                </View>
            ),
        },
        // 10 — recap
        {
            title: "Here's\nyour day",
            sub: 'Max fits your routines into the gaps. You can drag any of this later in Plan.',
            canNext: true,
            body: (
                <>
                    <View style={styles.recapList}>
                        {recap.map((r, i) => (
                            <View key={r.label}>
                                {i > 0 ? <View style={styles.hairline} /> : null}
                                <View style={styles.recapRow}>
                                    <View style={styles.recapIcon}>
                                        <Ionicons name={r.icon as any} size={17} color={MUTE} />
                                    </View>
                                    <Text style={styles.recapLabel}>{r.label}</Text>
                                    <Text style={styles.recapValue}>{r.value}</Text>
                                </View>
                            </View>
                        ))}
                    </View>
                    <Text style={styles.wellnessNote}>
                        General wellness only — not medical advice. Follow routines at your own risk.
                    </Text>
                </>
            ),
        },
    ];

    // Funnel V4 phase slices over the single ordered list above. The scan
    // capture ran BEFORE the wizard, so the whole intro run (incl. effort) is
    // background-loading time for the analysis:
    //   intro    = age, gender, goals, motivation, effort → results gate
    //   schedule = day-shape … recap                      → finish() → Main
    // The conditional work-location step lives in `schedule`, so slice from the
    // END for that phase and by fixed index for the fixed-size front.
    const INTRO_LEN = 5;
    const steps = phase === 'intro' ? allSteps.slice(0, INTRO_LEN) : allSteps.slice(INTRO_LEN);

    // A step removed beneath the current index (e.g. toggling work off while
    // past the Work step) would leave `step` dangling — clamp it so we never
    // read an undefined step.
    const safeStep = Math.min(step, steps.length - 1);
    const current = steps[safeStep];
    const isLast = safeStep === steps.length - 1;

    // Continuous funnel progress across phases + the screens between them
    // (scan first, then results/paywall/account between the phases), so the
    // bar never jumps backwards.
    const PHASE_OFFSET = { intro: 1, schedule: INTRO_LEN + 4 } as const;
    const FUNNEL_TOTAL = allSteps.length + 4;
    const progressIndex = PHASE_OFFSET[phase] + safeStep;

    const goNext = () => {
        if (Platform.OS !== 'web') {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        }
        if (isLast) {
            if (phase === 'intro') {
                // Persist identity + goals now so the paywall personalization can
                // read them (best-effort), then on to the results gate — the
                // classic results page reduced to its hero. It shows the
                // processing loader if the background analysis hasn't landed.
                void api.saveOnboarding(introPayload() as any).catch(() => {});
                track('onboarding_step', { step: 'intro_done' });
                // Skipped the scan → nothing to gate on; straight to the paywall.
                if (scanSkipped) navigation.navigate('Payment');
                else navigation.navigate('FaceScanResults', { gateV4: true });
                return;
            }
            finish();
            return;
        }
        // Dismiss any open wheel sheet before the step transition so a picker
        // <Modal> can never leak across steps and block taps on the next screen.
        if (picker) setPicker(null);
        setDir(1);
        setStep(safeStep + 1);
    };
    goNextRef.current = goNext;
    const goBack = () => {
        if (Platform.OS !== 'web') {
            Haptics.selectionAsync().catch(() => {});
        }
        if (picker) setPicker(null);
        setDir(-1);
        setStep(safeStep - 1);
    };

    // Shared-value driven page transition — robust on web AND native. On each
    // step change `t` runs 0->1; the header leads, the body staggers in.
    const reduced = useReducedMotion();
    const t = useSharedValue(1);
    useEffect(() => {
        if (reduced) { t.value = 1; return; }
        t.value = 0;
        t.value = withTiming(1, { duration: 460, easing: Easing.out(Easing.cubic) });
    }, [safeStep, reduced, t]);

    // Funnel analytics: one event per step VIEWED, so we can see exactly where
    // users drop off in the quiz. `step` is a stable slug; index/total let us
    // reconstruct the funnel even as the (conditional) step count varies.
    useEffect(() => {
        if (!draftLoaded) return;
        const title = steps[safeStep]?.title ?? '';
        track('onboarding_step', {
            step: STEP_KEYS[title] ?? `idx_${safeStep}`,
            index: safeStep,
            total: steps.length,
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [safeStep, draftLoaded]);
    const headStyle = useAnimatedStyle(() => ({
        opacity: interpolate(t.value, [0, 0.6], [0, 1], Extrapolation.CLAMP),
        transform: [{ translateX: interpolate(t.value, [0, 1], [dir * 34, 0], Extrapolation.CLAMP) }],
    }));
    const bodyStyle = useAnimatedStyle(() => ({
        opacity: interpolate(t.value, [0.18, 0.9], [0, 1], Extrapolation.CLAMP),
        transform: [{ translateY: interpolate(t.value, [0.18, 1], [16, 0], Extrapolation.CLAMP) }],
    }));

    // Hold the first paint until the saved draft (if any) has been applied, so
    // a resumed onboarding never flashes step 0 before jumping to the real step.
    if (!draftLoaded) {
        return <View style={styles.root} />;
    }

    return (
        <View style={styles.root}>
            <View style={{ flex: 1, width: '100%', maxWidth: 460, alignSelf: 'center', paddingTop: insets.top + 14, paddingHorizontal: 24 }}>
                <View style={styles.topRow}>
                    {safeStep > 0 ? (
                        <TouchableOpacity
                            onPress={goBack}
                            style={styles.backBtn}
                            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                            accessibilityRole="button"
                            accessibilityLabel="Back"
                        >
                            <Ionicons name="chevron-back" size={22} color={INK} />
                        </TouchableOpacity>
                    ) : (
                        <View style={styles.backBtnSpacer} />
                    )}
                    <ProgressBar index={progressIndex} total={FUNNEL_TOTAL} />
                </View>

                <ScrollView
                    style={{ flex: 1 }}
                    contentContainerStyle={styles.scrollBody}
                    showsVerticalScrollIndicator={false}
                >
                    <Animated.View style={[styles.headBlock, headStyle]}>
                        <Text style={styles.title}>{current.title}</Text>
                        <Text style={styles.sub}>{current.sub}</Text>
                    </Animated.View>

                    <Animated.View style={[styles.bodyBlock, bodyStyle]}>
                        {current.body}
                        {error ? <Text style={styles.error}>{error}</Text> : null}
                    </Animated.View>
                </ScrollView>

                <View style={{ paddingBottom: insets.bottom + 16 }}>
                    {/* Single-choice steps auto-advance on tap — no Continue button
                        (the tap IS the continue). Multi-select / compound steps keep it. */}
                    {(current as any).auto ? (
                        <View style={{ height: 52 }} />
                    ) : (
                        <PrimaryButton
                            label={isLast && phase === 'schedule' ? 'Build my day' : 'Continue'}
                            loading={saving}
                            disabled={!current.canNext}
                            onPress={goNext}
                        />
                    )}
                </View>
            </View>

            {picker ? (
                <TimePickerSheet
                    key={pickerKey}
                    title={picker.title}
                    value={picker.value}
                    onClose={() => setPicker(null)}
                    onConfirm={(v) => { picker.onSave(v); setPicker(null); }}
                />
            ) : null}
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },

    // top: back chevron in a white circle · thick rounded progress bar
    topRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
    backBtn: {
        width: 36, height: 36, borderRadius: 18,
        backgroundColor: BACK_BG,
        alignItems: 'center', justifyContent: 'center',
        ...SOFT,
    },
    backBtnSpacer: { width: 36, height: 36 },
    progressTrack: { flex: 1, height: 6, borderRadius: 3, backgroundColor: TRACK, overflow: 'hidden' },
    progressFill: { height: '100%', borderRadius: 3, backgroundColor: INK },

    // content centered horizontally + vertically (grows to fill, then scrolls)
    scrollBody: { flexGrow: 1, justifyContent: 'center', paddingVertical: 16 },

    // header — centered bold sans
    headBlock: { width: '100%', alignItems: 'center' },
    bodyBlock: { width: '100%', marginTop: 26 },
    title: { fontFamily: 'Matter-Bold', fontSize: 30, color: INK, letterSpacing: -0.6, lineHeight: 36, textAlign: 'center' },
    sub: { fontFamily: 'Matter-Regular', fontSize: 15, color: SUB, marginTop: 12, lineHeight: 21, textAlign: 'center', paddingHorizontal: 12 },
    helpNote: { fontFamily: 'Matter-Regular', fontSize: 13, color: MUTE, marginTop: 14, lineHeight: 18, textAlign: 'center' },

    // selection cards — Stoic's white soft-shadow pill, solid black when picked
    tile: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 15,
        minHeight: 66,
        borderRadius: 22,
        backgroundColor: CARD,
        ...SOFT,
    },
    tileActive: { backgroundColor: INK },
    tileIcon: {
        width: 38, height: 38, borderRadius: 19,
        backgroundColor: ICON_BG,
        alignItems: 'center', justifyContent: 'center',
        marginRight: 14,
        overflow: 'hidden',
    },
    tileThumb: { width: 34, height: 34 },
    tileLabel: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: INK },
    tileLabelCenter: { flex: 1, textAlign: 'center' },
    tileLabelActive: { color: ON_INK },
    otherInput: {
        fontFamily: 'Matter-Regular',
        fontSize: 16,
        color: INK,
        backgroundColor: CARD,
        borderRadius: 22,
        paddingHorizontal: 16,
        paddingVertical: 15,
        minHeight: 66,
        textAlignVertical: 'top',
        ...SOFT,
    },
    tileTag: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: MUTE, marginTop: 2 },
    tileTagActive: { color: 'rgba(255,255,255,0.6)' },
    rankBadge: { width: 24, height: 24, borderRadius: 12, backgroundColor: ON_INK, alignItems: 'center', justifyContent: 'center' },
    rankText: { fontFamily: 'Matter-SemiBold', fontSize: 12, color: INK },

    // grouped inputs in a white soft-shadow card (time rows / meals)
    shapeCard: { width: '100%', backgroundColor: CARD, borderRadius: 22, paddingHorizontal: 18, ...SOFT },
    hairline: { height: StyleSheet.hairlineWidth, backgroundColor: HAIR },

    // a tappable time row — label on top, big time below, chevron right
    timeRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14 },
    timeRowLabel: { fontFamily: 'Matter-Medium', fontSize: 13, color: SUB },
    timeRowCaption: { fontFamily: 'Matter-Regular', fontSize: 11.5, color: MUTE, marginTop: 1 },
    timeRowValue: { fontFamily: 'Matter-SemiBold', fontSize: 19, color: INK, letterSpacing: -0.3, marginTop: 2 },
    timeRowValueDim: { color: MUTE, fontFamily: 'Matter-Medium' },

    // Stoic switch
    toggle: { width: 48, height: 28, borderRadius: 14, backgroundColor: TRACK, padding: 3, alignItems: 'flex-start', justifyContent: 'center' },
    toggleOn: { backgroundColor: INK, alignItems: 'flex-end' },
    knob: {
        width: 22, height: 22, borderRadius: 11, backgroundColor: '#FFFFFF',
        shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 2, shadowOffset: { width: 0, height: 1 }, elevation: 2,
    },

    workChip: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        width: '100%',
        paddingHorizontal: 18,
        paddingVertical: 17,
        borderRadius: 22,
        backgroundColor: CARD,
        overflow: 'hidden',
        ...SOFT,
    },
    workChipActive: { backgroundColor: INK },
    workChipText: { fontFamily: 'Matter-SemiBold', fontSize: 15, color: INK },
    workChipTextActive: { color: ON_INK },

    groupLabel: { fontFamily: 'Matter-SemiBold', fontSize: 11, letterSpacing: 1.2, color: MUTE, marginTop: 24, marginBottom: 10, textTransform: 'uppercase', textAlign: 'center' },
    groupLabelInRow: { marginTop: 0, marginBottom: 0, textAlign: 'left' },
    commuteWrap: { width: '100%' },
    commuteHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 24, marginBottom: 4 },
    commuteValue: { fontFamily: 'Matter-SemiBold', fontSize: 15, color: INK, letterSpacing: -0.2 },
    sliderWrap: { height: 40, justifyContent: 'center', marginTop: 4 },
    sliderTrack: { height: 6, borderRadius: 3, backgroundColor: TRACK },
    sliderFill: { position: 'absolute', left: 0, top: 17.5, height: 5, borderRadius: 3, backgroundColor: INK },
    sliderThumb: {
        position: 'absolute', top: 7, width: THUMB, height: THUMB, borderRadius: THUMB / 2,
        backgroundColor: INK, borderWidth: 3, borderColor: CARD,
        shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 3,
    },
    sliderEnds: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 },
    sliderEndText: { fontFamily: 'Matter-Regular', fontSize: 11, color: MUTE },

    // segmented — ink thumb on a white soft-shadow track
    seg: { flexDirection: 'row', width: '100%', padding: 5, gap: 5, backgroundColor: CARD, borderRadius: 18, ...SOFT },
    segItem: { flex: 1, paddingVertical: 13, alignItems: 'center', borderRadius: 13 },
    segItemActive: { backgroundColor: INK },
    segText: { fontFamily: 'Matter-Medium', fontSize: 14, color: SUB },
    segTextActive: { color: ON_INK },

    // recap — hairline list grouped in a white soft-shadow card
    recapList: { width: '100%', backgroundColor: CARD, borderRadius: 22, paddingHorizontal: 18, ...SOFT },
    recapRow: { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 15 },
    recapIcon: { width: 24, alignItems: 'center', marginRight: 14, marginTop: 1 },
    recapLabel: { fontFamily: 'Matter-Regular', fontSize: 15.5, color: SUB, marginRight: 12 },
    recapValue: { fontFamily: 'Matter-Medium', fontSize: 15.5, color: INK, flex: 1, textAlign: 'right', lineHeight: 21 },
    wellnessNote: {
        fontFamily: 'Matter-Regular',
        fontSize: 11,
        lineHeight: 15,
        color: MUTE,
        textAlign: 'center',
        marginTop: 16,
        paddingHorizontal: 16,
    },

    // wheel time picker (bottom sheet)
    sheetBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end' },
    sheet: {
        backgroundColor: BG,
        borderTopLeftRadius: 28, borderTopRightRadius: 28,
        paddingTop: 22, paddingBottom: 34, paddingHorizontal: 24,
        alignItems: 'center',
        width: '100%', maxWidth: 460, alignSelf: 'center',
    },
    sheetTitle: { fontFamily: 'Matter-SemiBold', fontSize: 17, color: INK, marginBottom: 8 },
    wheelRow: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', height: ITEM_H * VISIBLE, position: 'relative' },
    wheelBand: { position: 'absolute', left: 12, right: 12, top: ITEM_H * 2, height: ITEM_H, borderRadius: 12, backgroundColor: WASH },
    wheelItem: { height: ITEM_H, alignItems: 'center', justifyContent: 'center' },
    wheelText: { fontFamily: 'Matter-Medium', fontSize: 21, color: MUTE },
    wheelTextActive: { fontFamily: 'Matter-SemiBold', color: INK },
    sheetDone: {
        marginTop: 18, height: 52, minWidth: 200, paddingHorizontal: 48,
        borderRadius: 999, backgroundColor: INK,
        alignItems: 'center', justifyContent: 'center', borderCurve: 'continuous',
        ...SOFT,
    },
    sheetDoneText: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: ON_INK, letterSpacing: 0.2 },

    // CTA — Stoic's compact, centered black pill; solid gray when inactive
    cta: {
        height: 56,
        minWidth: 200,
        alignSelf: 'center',
        paddingHorizontal: 56,
        borderRadius: 999,
        backgroundColor: INK,
        alignItems: 'center',
        justifyContent: 'center',
        borderCurve: 'continuous',
        ...SOFT,
    },
    ctaDisabled: { backgroundColor: DISABLED, shadowOpacity: 0 },
    ctaText: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: ON_INK, letterSpacing: 0.2 },
    ctaTextDisabled: { color: DISABLED_TXT },

    error: { fontFamily: 'Matter-Regular', fontSize: 13, color: '#C0452C', marginTop: 14, textAlign: 'center' },
});
