/**
 * CreatorOnboardingScreen — post-approval studio wizard.
 * Aesthetic matches CreatorApplyScreen / OnboardingV2: Stoic cream canvas,
 * centered Matter headlines, Fraunces italic accents, liquid glass cards,
 * staggered page transitions, white pill back button.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView,
    ActivityIndicator, Platform, KeyboardAvoidingView, Modal, Pressable,
} from 'react-native';
import Animated, {
    Easing, Extrapolation, interpolate, useAnimatedStyle,
    useReducedMotion, useSharedValue, withTiming,
} from 'react-native-reanimated';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import * as DocumentPicker from 'expo-document-picker';
import * as Haptics from 'expo-haptics';
import { LiquidGlass } from '../../components/glass/LiquidGlass';
import api, { type CreatorHabitTemplate, type CreatorOnboardingState } from '../../services/api';

// How long a busy request stays escape-free before the Cancel link fades in
// (mirrors AnalyzingScreen's CANCEL_GRACE_MS — same spirit for the creator
// onboarding AI calls, which can run 20-60s server-side).
const CANCEL_GRACE_MS = 45_000;

// ── In-progress draft (typed-but-unsent text) ───────────────────────────────
// Step progress already persists server-side (setCreatorOnboardingStep). This
// covers the cheaper-to-lose-but-still-annoying case: a voice answer,
// correction, or welcome message the creator was mid-typing when the app got
// killed. Best-effort, debounced, keyed by creator id (maxx_id).
type CreatorDraft = {
    v: 1;
    creatorId: string;
    welcomeMsg?: string;
    voiceSampleId?: string;
    voiceAnswer?: string;
    correction?: string;
    ts: number;
};

const CREATOR_DRAFT_KEY_PREFIX = '@max_creator_onboarding_draft_v1:';

async function loadCreatorDraft(creatorId: string): Promise<CreatorDraft | null> {
    try {
        const raw = await AsyncStorage.getItem(CREATOR_DRAFT_KEY_PREFIX + creatorId);
        if (!raw) return null;
        const d = JSON.parse(raw) as CreatorDraft;
        if (!d || d.v !== 1 || d.creatorId !== creatorId) return null;
        return d;
    } catch {
        return null;
    }
}

async function saveCreatorDraft(creatorId: string, fields: Omit<CreatorDraft, 'v' | 'creatorId' | 'ts'>): Promise<void> {
    try {
        const draft: CreatorDraft = { v: 1, creatorId, ts: Date.now(), ...fields };
        await AsyncStorage.setItem(CREATOR_DRAFT_KEY_PREFIX + creatorId, JSON.stringify(draft));
    } catch {
        /* best-effort — a failed draft write must never break onboarding */
    }
}

async function clearCreatorDraft(creatorId: string): Promise<void> {
    try {
        await AsyncStorage.removeItem(CREATOR_DRAFT_KEY_PREFIX + creatorId);
    } catch {
        /* ignore */
    }
}

const INK = '#000000';
const ON_INK = '#FFFFFF';
const BG = '#F1F1EF';
const CARD = '#FFFFFF';
const SUB = '#6B6B6B';
const MUTE = '#9A9A9A';
const TRACK = '#E2E1DE';
const BACK_BG = '#FFFFFF';
const DISABLED = '#DAD9D6';
const DISABLED_TXT = '#A4A29D';
const HAIR = 'rgba(0,0,0,0.08)';
const DANGER = '#B23A3A';
const SERIF_I = 'Fraunces-Italic';

const SOFT = {
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 }, elevation: 2,
};

const STEP_KEYS = ['knowledge', 'reveal', 'voice_intro', 'voice_teach', 'habits', 'test_drive', 'pricing', 'media', 'launch'] as const;

const CARD_BORDER = {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: HAIR,
};

function normalizeDocUrl(raw: string): string {
    let url = raw.trim();
    if (!url) return url;
    if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
    return url;
}

function apiDetail(err: unknown): string {
    if (err instanceof Error && err.message && err.message !== 'Request failed') {
        return err.message;
    }
    const d = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
    return typeof d === 'string' ? d : 'Request failed';
}

function driveLinkDoc(url: string) {
    const source = /drive\.google|docs\.google/i.test(url) ? 'gdrive' : 'link';
    return { filename: 'Google Drive link', url, source };
}

function ProgressBar({ index, total }: { index: number; total: number }) {
    const p = useSharedValue((index + 1) / total);
    useEffect(() => {
        p.value = withTiming((index + 1) / total, { duration: 380, easing: Easing.out(Easing.cubic) });
    }, [index, total, p]);
    const style = useAnimatedStyle(() => ({ width: `${p.value * 100}%` }));
    return (
        <View style={s.progressTrack}>
            <Animated.View style={[s.progressFill, style]} />
        </View>
    );
}

function PrimaryButton({ label, onPress, loading, disabled }: {
    label: string; onPress?: () => void; loading?: boolean; disabled?: boolean;
}) {
    const dim = disabled && !loading;
    return (
        <TouchableOpacity
            activeOpacity={0.9}
            onPress={onPress}
            disabled={disabled || loading}
            style={[s.cta, dim && s.ctaDisabled]}
            accessibilityRole="button"
        >
            {loading ? <ActivityIndicator color={ON_INK} /> : (
                <Text style={[s.ctaText, dim && s.ctaTextDisabled]}>{label}</Text>
            )}
        </TouchableOpacity>
    );
}

function Field({ value, onChangeText, placeholder, multiline, autoCapitalize }: {
    value: string; onChangeText: (t: string) => void; placeholder: string;
    multiline?: boolean; autoCapitalize?: 'none' | 'sentences';
}) {
    return (
        <View style={s.fieldLine}>
            <TextInput
                style={[s.input, multiline && s.inputMulti]}
                value={value}
                onChangeText={onChangeText}
                placeholder={placeholder}
                placeholderTextColor={MUTE}
                multiline={multiline}
                autoCapitalize={autoCapitalize ?? 'sentences'}
            />
        </View>
    );
}

function MeterRow({ label, pct }: { label: string; pct: number }) {
    return (
        <View style={s.meterRow}>
            <View style={s.meterHead}>
                <Text style={s.meterLabel}>{label}</Text>
                <Text style={s.meterPct}>{pct > 0 ? `${pct}%` : 'not started'}</Text>
            </View>
            <View style={s.meterTrack}>
                <View style={[s.meterFill, { width: `${Math.max(pct, pct > 0 ? 4 : 0)}%` }]} />
            </View>
        </View>
    );
}

function GlassMeter({ protocols, voice }: { protocols: number; voice: number }) {
    return (
        <LiquidGlass radius={22} intensity={68} noShadow style={[s.glassShell, { width: '100%' }]} contentStyle={s.glassPad}>
            <MeterRow label="Your protocols" pct={protocols} />
            <View style={s.meterHair} />
            <MeterRow label="Your voice" pct={voice} />
            <Text style={s.revealCopy}>
                Right now it answers like a textbook. Let's fix that — but you're going to teach it, by talking.
                Takes a few minutes now, and it keeps getting sharper as you use it.
            </Text>
        </LiquidGlass>
    );
}

export default function CreatorOnboardingScreen() {
    const insets = useSafeAreaInsets();
    const navigation = useNavigation<any>();
    const reduced = useReducedMotion();
    const [state, setState] = useState<CreatorOnboardingState | null>(null);
    const [step, setStep] = useState(0);
    const [dir, setDir] = useState(1);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [voiceAnswer, setVoiceAnswer] = useState('');
    const [correction, setCorrection] = useState('');
    const [driveUrl, setDriveUrl] = useState('');
    const [chatInput, setChatInput] = useState('');
    const [welcomeMsg, setWelcomeMsg] = useState('');
    const [introUrl, setIntroUrl] = useState('');
    const [habitFilter, setHabitFilter] = useState('All');
    const [habitSearch, setHabitSearch] = useState('');
    const [testMode, setTestMode] = useState<'stress' | 'chat'>('stress');
    const [habitDraft, setHabitDraft] = useState<CreatorHabitTemplate | null>(null);
    const [showCorrection, setShowCorrection] = useState(false);
    const [docErr, setDocErr] = useState<string | null>(null);
    // Escape hatch for long-running AI calls (analyze / voice-draft / test-drive).
    const [longWait, setLongWait] = useState(false);
    const [retryAction, setRetryAction] = useState<(() => void) | null>(null);
    // Sticky "has the creator engaged the test drive at all" latch (stress-test
    // complete OR ever sent a chat message) — independent of which tab is open.
    const [testEngaged, setTestEngaged] = useState(false);
    // Which step a busy request launched from (goNext only) — combined with
    // reqSeqRef below to guard goNext's continuations against applying a
    // stale result after the user has moved off that step.
    const stepRef = useRef(step);
    // Monotonic request-token counter. Every async action below mints its own
    // id by pre-incrementing this ref; the request is "stale" the instant any
    // other action (a newer request from the same or a different handler, or
    // an explicit cancel-bump) advances the counter past that id. A single
    // shared boolean can't express "only THIS request was cancelled" — it
    // re-arms and silently un-cancels whichever request happens to run next,
    // which is exactly what let a late-resolving cancelled request resurrect
    // itself. The counter has no such ambiguity: each request gets a unique
    // id and only an exact match to the *current* counter value is fresh.
    const reqSeqRef = useRef(0);

    const appendKnowledgeDoc = useCallback((doc: { filename: string; url: string; source?: string }) => {
        setState((prev) => prev ? {
            ...prev,
            knowledge_docs: [...(prev.knowledge_docs || []), doc],
        } : prev);
    }, []);

    const load = useCallback(async () => {
        try {
            const data = await api.getCreatorOnboarding();
            setState(data);
            if (!data.complete) setStep(Math.min(data.step, STEP_KEYS.length - 1));
            setWelcomeMsg(data.welcome_message || '');
            setIntroUrl(data.intro_video_url || '');
        } catch {
            setError('Could not load onboarding.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    useEffect(() => {
        if (step === 3) void load();
    }, [step, load]);

    useEffect(() => {
        setShowCorrection(false);
        setCorrection('');
        setVoiceAnswer('');
    }, [state?.current_voice_sample?.id]);

    useEffect(() => { stepRef.current = step; }, [step]);

    // Reveal the "taking longer than usual" escape hatch only after a busy
    // request has been in flight past the grace period — a normal request
    // never sees it, but a hung one always gets a way out.
    useEffect(() => {
        if (!busy) { setLongWait(false); return; }
        const t = setTimeout(() => setLongWait(true), CANCEL_GRACE_MS);
        return () => clearTimeout(t);
    }, [busy]);

    // Stress-test / chat engagement is sticky — once the creator has run the
    // gauntlet OR sent a single test-chat message, Continue stays unlocked
    // even if they flip back to the other tab.
    useEffect(() => {
        if (state?.test_drive?.complete || (state?.test_chat || []).length > 0) {
            setTestEngaged(true);
        }
    }, [state?.test_drive?.complete, state?.test_chat]);

    // Restore any unsent voice answer/correction/welcome message from a prior
    // session, once the creator id is known. Runs once per mount — later
    // sample transitions intentionally clear the box (see effect above).
    useEffect(() => {
        const creatorId = state?.max_name;
        if (!creatorId) return;
        let cancelled = false;
        (async () => {
            const draft = await loadCreatorDraft(creatorId);
            if (cancelled || !draft) return;
            if (draft.welcomeMsg && !state?.welcome_message) setWelcomeMsg(draft.welcomeMsg);
            if (draft.voiceSampleId && draft.voiceSampleId === state?.current_voice_sample?.id) {
                if (draft.voiceAnswer) setVoiceAnswer(draft.voiceAnswer);
                if (draft.correction) setCorrection(draft.correction);
            }
        })();
        return () => { cancelled = true; };
        // Intentionally only re-runs when the creator id first resolves.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [state?.max_name]);

    // Debounced save of in-progress unsent text — cheap insurance against an
    // app kill mid-edit. Step progress already persists separately.
    useEffect(() => {
        const creatorId = state?.max_name;
        if (!creatorId) return;
        const t = setTimeout(() => {
            void saveCreatorDraft(creatorId, {
                welcomeMsg: welcomeMsg || undefined,
                voiceSampleId: state?.current_voice_sample?.id,
                voiceAnswer: voiceAnswer || undefined,
                correction: correction || undefined,
            });
        }, 600);
        return () => clearTimeout(t);
    }, [state?.max_name, state?.current_voice_sample?.id, welcomeMsg, voiceAnswer, correction]);

    const maxName = state?.max_name?.replace(/max$/i, '') || 'Your max';
    const maxLabel = maxName.charAt(0).toUpperCase() + maxName.slice(1);
    const habits = state?.habit_library || [];
    const habitTags = useMemo(() => {
        const tags = new Set<string>();
        habits.forEach((h) => (h.tags || []).forEach((t) => tags.add(t)));
        return ['All', ...Array.from(tags).slice(0, 8)];
    }, [habits]);
    const targetingPresets = state?.targeting_presets || [
        'All subscribers', 'Beginners (first 2 weeks)', 'Intermediate (week 3+)',
        'Advanced practitioners', 'Morning routine focus', 'Evening recovery focus',
    ];
    const filteredHabits = habits.filter((h) => {
        if (h.enabled === false) return false;
        const q = habitSearch.trim().toLowerCase();
        const tagMatch = habitFilter === 'All'
            || (h.tags || []).some((t) => t.toLowerCase().includes(habitFilter.toLowerCase()))
            || h.title.toLowerCase().includes(habitFilter.toLowerCase());
        if (!tagMatch) return false;
        if (!q) return true;
        const hay = [
            h.title,
            h.description || '',
            ...(h.tags || []),
            ...(h.conditions || []),
            ...(h.sample_questions || []),
        ].join(' ').toLowerCase();
        return hay.includes(q);
    });

    const persistStep = async (next: number) => {
        try { await api.setCreatorOnboardingStep(next); } catch { /* best-effort */ }
    };

    // Aborts the current wait: bumping the token invalidates every in-flight
    // request at once (whichever action started it), so each becomes a no-op
    // when it resolves — busy clears immediately, and the creator lands back
    // on the same step with whatever they'd typed still in the fields.
    const cancelLongWait = useCallback(() => {
        reqSeqRef.current++;
        setLongWait(false);
        setBusy(false);
    }, []);

    const goNext = async () => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        setError(null);
        setRetryAction(null);
        const key = STEP_KEYS[step];
        const fromStep = step;
        const reqId = ++reqSeqRef.current;
        setBusy(true);
        // Bail out of applying a result if a newer request has started (via
        // this or any other action, or an explicit cancel-bump), or —
        // defense in depth — the creator has already moved off the step this
        // call started from: never force them forward, clear busy, or
        // surface an error for a stale response.
        const stale = () => reqSeqRef.current !== reqId || stepRef.current !== fromStep;
        try {
            if (key === 'knowledge') {
                const data = await api.analyzeCreatorKnowledge();
                if (stale()) return;
                setState(data);
                setDir(1); setStep(1);
                await persistStep(1);
            } else if (key === 'voice_intro') {
                setDir(1); setStep(3);
                await persistStep(3);
            } else if (key === 'habits') {
                await api.updateCreatorHabitLibrary(habits);
                await api.syncCreatorOnboardingHabits();
                if (stale()) return;
                setDir(1); setStep(5);
                await persistStep(5);
            } else if (key === 'pricing') {
                setDir(1); setStep(7);
                await persistStep(7);
            } else if (key === 'media') {
                const data = await api.setCreatorOnboardingMedia(introUrl.trim() || undefined, welcomeMsg.trim());
                if (stale()) return;
                setState(data);
                if (state?.max_name) void clearCreatorDraft(state.max_name);
                setDir(1); setStep(8);
                await persistStep(8);
            } else if (key === 'launch') {
                const data = await api.launchCreatorMax();
                if (stale()) return;
                setState(data);
                Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
                navigation.replace('CreatorStudio');
                return;
            } else if (step < STEP_KEYS.length - 1) {
                setDir(1); setStep(step + 1);
                await persistStep(step + 1);
            }
        } catch (e: any) {
            if (stale()) return;
            setError(e?.response?.data?.detail || 'Something went wrong.');
            setRetryAction(() => () => { void latestRef.current.goNext(); });
        } finally {
            if (!stale()) setBusy(false);
        }
    };

    const goBack = () => {
        if (busy) return; // don't let the creator navigate away from an in-flight step request
        if (step === 0) { navigation.goBack(); return; }
        Haptics.selectionAsync().catch(() => {});
        setDir(-1); setStep(step - 1); setError(null);
    };

    const pickDoc = async () => {
        setBusy(true); setDocErr(null);
        try {
            if (Platform.OS === 'web') {
                await new Promise<void>((resolve) => {
                    const input = document.createElement('input');
                    input.type = 'file';
                    input.accept = '.pdf,.doc,.docx,.ppt,.pptx,.txt,.md,image/*';
                    let settled = false;
                    const done = () => {
                        if (settled) return;
                        settled = true;
                        resolve();
                    };
                    input.onchange = async () => {
                        try {
                            const file = input.files?.[0];
                            if (!file) return;
                            const data = await api.uploadCreatorOnboardingDoc(file);
                            appendKnowledgeDoc(data);
                        } catch (e) {
                            setDocErr(apiDetail(e) || 'Upload failed.');
                        } finally {
                            done();
                        }
                    };
                    input.addEventListener('cancel', done, { once: true });
                    window.addEventListener('focus', () => {
                        setTimeout(() => {
                            if (!input.files?.length) done();
                        }, 400);
                    }, { once: true });
                    input.click();
                });
                return;
            }
            const picked = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true });
            if (!picked.canceled && picked.assets?.[0]) {
                const a = picked.assets[0];
                const data = await api.uploadCreatorOnboardingDoc({
                    uri: a.uri, name: a.name || 'doc', type: a.mimeType || undefined,
                });
                appendKnowledgeDoc(data);
            }
        } catch (e) {
            setDocErr(apiDetail(e) || 'Upload failed.');
        } finally {
            setBusy(false);
        }
    };

    const addDrive = async () => {
        const url = normalizeDocUrl(driveUrl);
        if (!url) return;
        setBusy(true); setDocErr(null);
        try {
            try {
                const data = await api.linkCreatorOnboardingDoc(url);
                appendKnowledgeDoc(data);
            } catch {
                // Show link immediately even if the server is unreachable; analyze will retry.
                appendKnowledgeDoc(driveLinkDoc(url));
            }
            setDriveUrl('');
        } catch (e) {
            setDocErr(apiDetail(e) || 'Could not add that link.');
        } finally {
            setBusy(false);
        }
    };

    const removeDoc = async (url: string) => {
        setBusy(true); setDocErr(null);
        try {
            const data = await api.deleteCreatorOnboardingDoc(url);
            setState(data);
        } catch {
            setState((prev) => prev ? {
                ...prev,
                knowledge_docs: (prev.knowledge_docs || []).filter((d) => d.url !== url),
            } : prev);
        } finally {
            setBusy(false);
        }
    };

    const openHabitEditor = (h: CreatorHabitTemplate) => {
        setHabitDraft({ ...h, conditions: [...(h.conditions || [])], sample_questions: [...(h.sample_questions || [])] });
    };

    const addHabit = () => {
        openHabitEditor({
            id: `habit-${Date.now()}`,
            title: 'New habit',
            description: '',
            duration_minutes: 10,
            conditions: ['All subscribers'],
            tags: [],
            sample_questions: [],
            enabled: true,
        });
    };

    const saveHabitEdit = async () => {
        if (!habitDraft) return;
        const exists = habits.some((h) => h.id === habitDraft.id);
        const updated = exists
            ? habits.map((h) => (h.id === habitDraft.id ? habitDraft : h))
            : [...habits, habitDraft];
        setBusy(true);
        try {
            const data = await api.updateCreatorHabitLibrary(updated);
            setState(data);
            setHabitDraft(null);
        } catch {
            setError('Could not save habit.');
        } finally {
            setBusy(false);
        }
    };

    const removeHabit = async () => {
        if (!habitDraft) return;
        const updated = habits.filter((h) => h.id !== habitDraft.id);
        setBusy(true);
        try {
            const data = await api.updateCreatorHabitLibrary(updated);
            setState(data);
            setHabitDraft(null);
        } catch {
            setError('Could not remove habit.');
        } finally {
            setBusy(false);
        }
    };

    const toggleHabitCondition = (preset: string) => {
        if (!habitDraft) return;
        const cur = habitDraft.conditions || [];
        const next = cur.includes(preset) ? cur.filter((c) => c !== preset) : [...cur, preset];
        setHabitDraft({ ...habitDraft, conditions: next });
    };

    const submitTestDrive = async (answer: string) => {
        const cur = state?.test_drive?.current;
        if (!cur) return;
        setError(null); setRetryAction(null);
        const reqId = ++reqSeqRef.current;
        const stale = () => reqSeqRef.current !== reqId;
        setBusy(true);
        try {
            const data = await api.submitTestDriveAnswer(cur.id, answer);
            if (stale()) return;
            setState(data);
            // testEngaged flips to true reactively (see effect above) only once
            // state.test_drive.complete — a single answer isn't "engaged" yet.
        } catch {
            if (stale()) return;
            setError('Could not save answer.');
            setRetryAction(() => () => { void latestRef.current.submitTestDrive(answer); });
        } finally {
            if (!stale()) setBusy(false);
        }
    };

    const submitVoice = async () => {
        const sample = state?.current_voice_sample;
        if (!sample || !voiceAnswer.trim()) return;
        setError(null); setRetryAction(null);
        const reqId = ++reqSeqRef.current;
        const stale = () => reqSeqRef.current !== reqId;
        setBusy(true);
        try {
            const data = await api.submitCreatorVoiceAnswer(sample.id, voiceAnswer.trim());
            if (stale()) return;
            setState(data);
            setVoiceAnswer('');
            setShowCorrection(false);
        } catch {
            if (stale()) return;
            setError('Could not save answer.');
            setRetryAction(() => () => { void latestRef.current.submitVoice(); });
        }
        finally { if (!stale()) setBusy(false); }
    };

    const voiceFeedback = async (approved: boolean) => {
        const sample = state?.current_voice_sample;
        if (!sample) return;
        setError(null); setRetryAction(null);
        const reqId = ++reqSeqRef.current;
        const stale = () => reqSeqRef.current !== reqId;
        setBusy(true);
        try {
            const data = await api.submitCreatorVoiceFeedback(
                sample.id, approved, approved ? undefined : correction.trim(),
            );
            if (stale()) return;
            setState(data);
            setCorrection('');
            setShowCorrection(false);
        } catch {
            if (stale()) return;
            setError('Could not save feedback.');
            setRetryAction(() => () => { void latestRef.current.voiceFeedback(approved); });
        }
        finally { if (!stale()) setBusy(false); }
    };

    const sendChat = async () => {
        if (!chatInput.trim()) return;
        const sent = chatInput.trim();
        setError(null); setRetryAction(null);
        const reqId = ++reqSeqRef.current;
        const stale = () => reqSeqRef.current !== reqId;
        setBusy(true);
        try {
            const data = await api.creatorOnboardingTestChat(sent);
            if (stale()) return;
            setState(data);
            setTestEngaged(true);
            setChatInput('');
        } catch {
            if (stale()) return;
            // chatInput is left untouched on failure, and retry dispatches
            // through latestRef, so it re-sends whatever's in the box at
            // Retry time (a corrected message, if the creator edited it).
            setError('Chat failed.');
            setRetryAction(() => () => { void latestRef.current.sendChat(); });
        }
        finally { if (!stale()) setBusy(false); }
    };

    // Keep the freshest handler closures reachable from a stored retryAction.
    // retryAction is captured once, at the moment an error is caught — but a
    // creator can edit a field (voiceAnswer, welcomeMsg, chatInput, …) before
    // tapping Retry, and the retry must submit THAT value, not whatever was
    // in scope when the error fired. Dispatching through this ref (updated
    // every render) instead of calling the handler directly closes that gap:
    // by the time Retry runs, latestRef.current points at the newest
    // closures, which read current state.
    const latestRef = useRef({ goNext, submitTestDrive, submitVoice, voiceFeedback, sendChat });
    useEffect(() => {
        latestRef.current = { goNext, submitTestDrive, submitVoice, voiceFeedback, sendChat };
    });

    const t = useSharedValue(1);
    useEffect(() => {
        if (reduced) { t.value = 1; return; }
        t.value = 0;
        t.value = withTiming(1, { duration: 460, easing: Easing.out(Easing.cubic) });
    }, [step, reduced, t]);

    const headStyle = useAnimatedStyle(() => ({
        opacity: interpolate(t.value, [0, 0.6], [0, 1], Extrapolation.CLAMP),
        transform: [{ translateX: interpolate(t.value, [0, 1], [dir * 34, 0], Extrapolation.CLAMP) }],
    }));
    const bodyStyle = useAnimatedStyle(() => ({
        opacity: interpolate(t.value, [0.18, 0.9], [0, 1], Extrapolation.CLAMP),
        transform: [{ translateY: interpolate(t.value, [0.18, 1], [16, 0], Extrapolation.CLAMP) }],
    }));

    const steps = useMemo(() => {
        const sample = state?.current_voice_sample;
        const samplePhase = sample?.sample_phase ?? 1;
        const globalPhase = state?.voice_phase || 1;
        return [
            {
                key: 'knowledge',
                title: (
                    <Text style={s.title}>
                        What does{'\n'}<Text style={s.titleItalic}>{maxLabel}</Text> need to know?
                    </Text>
                ),
                sub: 'Drop in your guides, scripts, protocols.',
                canNext: (state?.knowledge_docs?.length || 0) > 0,
                body: (
                    <View style={{ gap: 12 }}>
                        <Text style={s.docHint}>
                            Upload guides, PDFs, or paste Google Drive links. Set sharing to "Anyone with the link can view" so Max can read them.
                        </Text>
                        {(state?.knowledge_docs || []).map((d, i) => (
                            <View key={`${d.url}-${i}`} style={s.docRow}>
                                <View style={s.docIcon}>
                                    <Ionicons
                                        name={d.source === 'gdrive' ? 'logo-google' : 'document-text-outline'}
                                        size={18}
                                        color={INK}
                                    />
                                </View>
                                <View style={{ flex: 1 }}>
                                    <Text style={s.docName} numberOfLines={1}>{d.filename}</Text>
                                    <Text style={s.docSub} numberOfLines={1}>
                                        {d.source === 'gdrive' ? 'Google Drive link' : d.source === 'local' ? 'Uploaded file' : 'External link'}
                                    </Text>
                                </View>
                                <TouchableOpacity onPress={() => void removeDoc(d.url)} hitSlop={8}>
                                    <Ionicons name="trash-outline" size={18} color={DANGER} />
                                </TouchableOpacity>
                            </View>
                        ))}
                        <TouchableOpacity style={s.docBtn} onPress={pickDoc} disabled={busy} activeOpacity={0.85}>
                            <Ionicons name="folder-open-outline" size={18} color={INK} />
                            <Text style={s.docBtnText}>Add from device</Text>
                        </TouchableOpacity>
                        <View style={s.driveRow}>
                            <TextInput
                                style={s.driveInput}
                                value={driveUrl}
                                onChangeText={setDriveUrl}
                                placeholder="Paste Google Drive link"
                                placeholderTextColor={MUTE}
                                autoCapitalize="none"
                                keyboardType="url"
                                onSubmitEditing={() => void addDrive()}
                            />
                            <TouchableOpacity
                                style={[s.linkBtn, (!driveUrl.trim() || busy) && s.linkBtnOff]}
                                onPress={addDrive}
                                disabled={busy || !driveUrl.trim()}
                            >
                                <Text style={s.linkBtnText}>Add</Text>
                            </TouchableOpacity>
                        </View>
                        {docErr ? <Text style={s.docErr}>{docErr}</Text> : null}
                    </View>
                ),
            },
            {
                key: 'reveal',
                title: (
                    <Text style={s.title}>
                        {maxLabel} knows{'\n'}<Text style={s.titleItalic}>your stuff</Text>.
                    </Text>
                ),
                sub: '',
                canNext: true,
                body: <GlassMeter protocols={state?.protocols_pct || 0} voice={state?.voice_pct || 0} />,
            },
            {
                key: 'voice_intro',
                title: (
                    <Text style={s.title}>
                        Teach your{'\n'}<Text style={s.titleItalic}>voice</Text>
                    </Text>
                ),
                sub: 'Three phases — most of it happens over time, not in one sitting.',
                canNext: true,
                body: (
                    <View style={{ gap: 12 }}>
                        {[
                            ['Phase 1', 'You write. Max just listens.', 'First ~8 answers — no draft. Max learns your patterns silently.'],
                            ['Phase 2', 'Max tries, you correct.', 'Once it has enough samples, it drafts — you fix what\'s off.'],
                            ['Phase 3', 'Max drafts, you approve.', 'Eventually it handles it and you spot-check.'],
                        ].map(([phase, title, desc]) => (
                            <LiquidGlass key={phase} radius={18} intensity={58} noShadow style={s.glassShell} contentStyle={s.phaseCard}>
                                <Text style={s.phaseKicker}>{phase}</Text>
                                <Text style={s.phaseTitle}>{title}</Text>
                                <Text style={s.phaseDesc}>{desc}</Text>
                            </LiquidGlass>
                        ))}
                    </View>
                ),
            },
            {
                key: 'voice_teach',
                title: samplePhase === 1 ? (
                    <Text style={s.title}>
                        Your{'\n'}<Text style={s.titleItalic}>answer</Text>
                    </Text>
                ) : samplePhase === 2 ? (
                    <Text style={s.title}>
                        Fix what's{'\n'}<Text style={s.titleItalic}>off</Text>
                    </Text>
                ) : (
                    <Text style={s.title}>
                        Approve or{'\n'}<Text style={s.titleItalic}>improve</Text>
                    </Text>
                ),
                sub: sample
                    ? samplePhase === 1
                        ? `Phase 1 · Question ${sample.index || 1} of ${state?.voice_samples_total || 0} — you write, Max listens`
                        : samplePhase === 2
                            ? `Phase 2 · Question ${sample.index || 1} — Max tries, you correct`
                            : `Phase 3 · Question ${sample.index || 1} — spot-check Max's drafts`
                    : 'Loading questions…',
                canNext: (state?.voice_samples_answered || 0) >= Math.min(8, state?.voice_samples_total || 8),
                body: sample ? (
                    <View style={{ gap: 14 }}>
                        <LiquidGlass radius={16} intensity={55} noShadow style={s.glassShell} contentStyle={s.quoteCard}>
                            <Text style={s.quoteLabel}>A subscriber asks</Text>
                            <Text style={s.quoteText}>"{sample.question}"</Text>
                        </LiquidGlass>
                        {samplePhase === 1 ? (
                            <>
                                <Text style={s.phaseLead}>No draft — write from scratch so Max learns your voice, not the other way around.</Text>
                                <Field value={voiceAnswer} onChangeText={setVoiceAnswer} placeholder="Type your answer from scratch…" multiline />
                                {voiceAnswer.trim() ? (
                                    <TouchableOpacity style={s.secondaryPill} onPress={submitVoice} disabled={busy} activeOpacity={0.85}>
                                        <Text style={s.secondaryPillText}>Submit answer</Text>
                                    </TouchableOpacity>
                                ) : null}
                            </>
                        ) : !sample.draft_answer ? (
                            <View style={s.draftLoading}>
                                <ActivityIndicator color={INK} />
                                <Text style={s.phaseLead}>{maxLabel} is drafting an answer in your voice…</Text>
                            </View>
                        ) : (
                            <>
                                <Text style={s.phaseLead}>
                                    {samplePhase === 2
                                        ? "I think I'm starting to get you. Let me try one — fix whatever's off:"
                                        : 'Voice still learning — approve this draft or improve it whenever you have a minute.'}
                                </Text>
                                <Text style={s.draftLabel}>{maxLabel} drafted</Text>
                                <LiquidGlass radius={16} intensity={62} noShadow style={s.glassShell} contentStyle={s.draftCard}>
                                    <Text style={s.draftText}>{sample.draft_answer}</Text>
                                </LiquidGlass>
                                <View style={s.feedbackRow}>
                                    <TouchableOpacity style={s.approveBtn} onPress={() => void voiceFeedback(true)} disabled={busy} activeOpacity={0.85}>
                                        <Ionicons name="checkmark" size={16} color={ON_INK} />
                                        <Text style={s.approveBtnText}>That's me</Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity
                                        style={s.editBtn}
                                        activeOpacity={0.85}
                                        onPress={() => setShowCorrection(true)}
                                    >
                                        <Ionicons name="pencil-outline" size={16} color={INK} />
                                        <Text style={s.editBtnText}>{samplePhase === 3 ? 'Improve' : 'Not quite'}</Text>
                                    </TouchableOpacity>
                                </View>
                                {showCorrection ? (
                                    <>
                                        <Field
                                            value={correction}
                                            onChangeText={setCorrection}
                                            placeholder={samplePhase === 3 ? 'Improve this draft…' : 'Type your correction…'}
                                            multiline
                                        />
                                        {correction.trim() ? (
                                            <TouchableOpacity style={s.secondaryPill} onPress={() => void voiceFeedback(false)} activeOpacity={0.85}>
                                                <Text style={s.secondaryPillText}>Save {samplePhase === 3 ? 'improvement' : 'correction'}</Text>
                                            </TouchableOpacity>
                                        ) : null}
                                    </>
                                ) : null}
                            </>
                        )}
                        <View style={s.voiceMeterCard}>
                            <Text style={s.voiceMeterLabel}>Voice training</Text>
                            <View style={s.meterTrack}><View style={[s.meterFill, { width: `${state?.voice_pct || 0}%` }]} /></View>
                            <Text style={s.voiceMeterSub}>
                                {state?.voice_pct || 0}% — {state?.voice_samples_answered || 0} of {state?.voice_samples_total || 0} answered
                                {globalPhase === 1 ? ' · Phase 1: you write' : globalPhase === 2 ? ' · Phase 2: you correct drafts' : ' · Phase 3: you approve'}
                            </Text>
                        </View>
                    </View>
                ) : null,
            },
            {
                key: 'habits',
                title: (
                    <Text style={s.title}>
                        {maxLabel}'s habit{'\n'}<Text style={s.titleItalic}>library</Text>
                    </Text>
                ),
                sub: `${habits.filter((h) => h.enabled !== false).length} habits Max personalizes from — tap to edit who sees each one`,
                canNext: habits.filter((h) => h.enabled !== false).length >= 2,
                body: (
                    <View style={{ gap: 12 }}>
                        <View style={s.searchRow}>
                            <Ionicons name="search-outline" size={16} color={MUTE} />
                            <TextInput
                                style={s.searchInput}
                                value={habitSearch}
                                onChangeText={setHabitSearch}
                                placeholder="Search habits, tags, questions…"
                                placeholderTextColor={MUTE}
                            />
                        </View>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.tagRow}>
                            {habitTags.map((tag) => (
                                <TouchableOpacity
                                    key={tag}
                                    style={[s.tagChip, habitFilter === tag && s.tagChipOn]}
                                    onPress={() => setHabitFilter(tag)}
                                    activeOpacity={0.85}
                                >
                                    <Text style={[s.tagChipText, habitFilter === tag && s.tagChipTextOn]}>{tag}</Text>
                                </TouchableOpacity>
                            ))}
                        </ScrollView>
                        {filteredHabits.slice(0, 20).map((h) => (
                            <TouchableOpacity key={h.id} onPress={() => openHabitEditor(h)} activeOpacity={0.85}>
                                <LiquidGlass radius={16} intensity={56} noShadow style={s.glassShell} contentStyle={s.habitCard}>
                                    <Ionicons name="menu-outline" size={16} color={MUTE} />
                                    <View style={{ flex: 1 }}>
                                        <Text style={s.habitTitle}>{h.title}</Text>
                                        <Text style={s.habitMeta} numberOfLines={1}>
                                            Shown when: {(h.conditions || ['All subscribers']).join(' · ')}
                                        </Text>
                                        {(h.sample_questions || []).length > 0 ? (
                                            <Text style={s.habitQuestion} numberOfLines={1}>
                                                e.g. "{h.sample_questions![0]}"
                                            </Text>
                                        ) : null}
                                    </View>
                                    <Ionicons name="chevron-forward" size={14} color={MUTE} />
                                </LiquidGlass>
                            </TouchableOpacity>
                        ))}
                        {filteredHabits.length === 0 ? (
                            <Text style={s.docHint}>No habits match your search.</Text>
                        ) : habits.length > 20 ? (
                            <Text style={s.moreText}>… {habits.length - 20} more</Text>
                        ) : null}
                        <TouchableOpacity style={s.docBtn} onPress={addHabit} activeOpacity={0.85}>
                            <Ionicons name="add-outline" size={18} color={INK} />
                            <Text style={s.docBtnText}>Add a habit</Text>
                        </TouchableOpacity>
                    </View>
                ),
            },
            {
                key: 'test_drive',
                title: (
                    <Text style={s.title}>
                        Try your{'\n'}<Text style={s.titleItalic}>own Max</Text>
                    </Text>
                ),
                sub: testMode === 'chat'
                    ? 'Chat as a subscriber — see how your Max responds.'
                    : state?.test_drive?.complete
                        ? 'Here\'s the routine Max built for this subscriber.'
                        : 'Stress-test onboarding — answer as a real subscriber would.',
                // Gate on the sticky testEngaged latch, not the currently-selected tab —
                // once the creator has run the gauntlet or sent a chat message, Continue
                // stays unlocked even if they flip tabs afterward.
                canNext: testEngaged,
                body: (
                    <View style={{ gap: 12 }}>
                        <View style={s.testModeRow}>
                            <TouchableOpacity
                                style={[s.testModeBtn, testMode === 'chat' && s.testModeBtnOn]}
                                onPress={() => setTestMode('chat')}
                                activeOpacity={0.85}
                            >
                                <Ionicons name="chatbubble-outline" size={14} color={testMode === 'chat' ? ON_INK : INK} />
                                <Text style={[s.testModeText, testMode === 'chat' && s.testModeTextOn]}>Chat as subscriber</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={[s.testModeBtn, testMode === 'stress' && s.testModeBtnOn]}
                                onPress={() => setTestMode('stress')}
                                activeOpacity={0.85}
                            >
                                <Ionicons name="flash-outline" size={14} color={testMode === 'stress' ? ON_INK : INK} />
                                <Text style={[s.testModeText, testMode === 'stress' && s.testModeTextOn]}>Stress-test</Text>
                            </TouchableOpacity>
                        </View>
                        {testMode === 'stress' ? (
                            <>
                                {state?.test_drive?.complete && (state.test_drive.schedule || []).length > 0 ? (
                                    <>
                                        {(state.test_drive.schedule || []).map((day) => (
                                            <View key={day.day} style={s.scheduleDay}>
                                                <Text style={s.scheduleDayLabel}>{day.day}</Text>
                                                <Text style={s.scheduleFocus}>{day.focus}</Text>
                                                {(day.tasks || []).map((t, i) => (
                                                    <View key={i} style={s.scheduleTask}>
                                                        <Ionicons name="ellipse" size={6} color={INK} />
                                                        <Text style={s.scheduleTaskText}>
                                                            {t.title} · {t.duration_min} min · {t.window}
                                                        </Text>
                                                    </View>
                                                ))}
                                            </View>
                                        ))}
                                    </>
                                ) : state?.test_drive?.current ? (
                                    <>
                                        <Text style={s.testStepLabel}>
                                            Step {(state.test_drive.current.index || 0) + 1} of {state.test_drive.total_steps}
                                        </Text>
                                        <LiquidGlass radius={18} intensity={60} noShadow style={s.glassShell} contentStyle={s.quoteCard}>
                                            <Text style={s.quoteText}>{state.test_drive.current.question}</Text>
                                        </LiquidGlass>
                                        {(state.test_drive.current.options || []).map((opt) => (
                                            <TouchableOpacity
                                                key={opt}
                                                style={s.optionBtn}
                                                onPress={() => void submitTestDrive(opt)}
                                                disabled={busy}
                                                activeOpacity={0.85}
                                            >
                                                <Text style={s.optionBtnText}>{opt}</Text>
                                            </TouchableOpacity>
                                        ))}
                                    </>
                                ) : (
                                    <Text style={s.chatEmpty}>Loading onboarding questions…</Text>
                                )}
                            </>
                        ) : (
                            <>
                                <LiquidGlass radius={20} intensity={62} noShadow style={s.glassShell} contentStyle={s.chatBox}>
                                    <ScrollView style={{ maxHeight: 220 }} nestedScrollEnabled showsVerticalScrollIndicator={false}>
                                        {(state?.test_chat || []).length === 0 ? (
                                            <Text style={s.chatEmpty}>Ask something this subscriber would…</Text>
                                        ) : (state?.test_chat || []).map((m, i) => (
                                            <View key={i} style={[s.chatBubble, m.role === 'user' ? s.chatUser : s.chatMax]}>
                                                <Text style={m.role === 'user' ? s.chatTextUser : s.chatText}>{m.text}</Text>
                                            </View>
                                        ))}
                                    </ScrollView>
                                </LiquidGlass>
                                <View style={s.driveRow}>
                                    <TextInput
                                        style={[s.driveInput, { flex: 1 }]}
                                        value={chatInput}
                                        onChangeText={setChatInput}
                                        placeholder="Ask as this subscriber…"
                                        placeholderTextColor={MUTE}
                                    />
                                    <TouchableOpacity style={[s.linkBtn, busy && s.linkBtnOff]} onPress={sendChat} disabled={busy}>
                                        <Text style={s.linkBtnText}>Send</Text>
                                    </TouchableOpacity>
                                </View>
                            </>
                        )}
                        <TouchableOpacity
                            onPress={() => api.resetCreatorOnboardingTest().then(setState)}
                            activeOpacity={0.85}
                            style={s.resetLink}
                        >
                            <Ionicons name="refresh-outline" size={14} color={SUB} />
                            <Text style={s.resetLinkText}>Reset test drive</Text>
                        </TouchableOpacity>
                    </View>
                ),
            },
            {
                key: 'pricing',
                title: (
                    <Text style={s.title}>
                        Set your{'\n'}<Text style={s.titleItalic}>price</Text>
                    </Text>
                ),
                sub: 'Monthly subscription — pick a tier.',
                canNext: !!state?.price_tier,
                body: (
                    <View style={{ gap: 10 }}>
                        {Object.entries(state?.price_tiers || { t1: 499, t2: 999, t3: 1999, t4: 2999 })
                            .filter(([k]) => k !== 'free')
                            .map(([tier, cents]) => {
                                const selected = state?.price_tier === tier;
                                return (
                                    <TouchableOpacity
                                        key={tier}
                                        onPress={() => api.setCreatorOnboardingPricing(tier).then(setState)}
                                        activeOpacity={0.85}
                                    >
                                        <LiquidGlass
                                            radius={18}
                                            intensity={selected ? 70 : 52}
                                            style={{ width: '100%' }}
                                            contentStyle={[s.priceCard, selected && s.priceCardOn]}
                                        >
                                            <Text style={s.priceLabel}>${(cents / 100).toFixed(2)}<Text style={s.pricePer}>/mo</Text></Text>
                                            {selected ? <Ionicons name="checkmark-circle" size={22} color={INK} /> : null}
                                        </LiquidGlass>
                                    </TouchableOpacity>
                                );
                            })}
                    </View>
                ),
            },
            {
                key: 'media',
                title: (
                    <Text style={s.title}>
                        Course{'\n'}<Text style={s.titleItalic}>intro</Text>
                    </Text>
                ),
                sub: 'Video link + welcome message for new subscribers.',
                canNext: welcomeMsg.trim().length > 0,
                body: (
                    <View style={{ gap: 16 }}>
                        <Field value={introUrl} onChangeText={setIntroUrl} placeholder="Intro video URL (YouTube, Drive…)" autoCapitalize="none" />
                        <Field value={welcomeMsg} onChangeText={setWelcomeMsg} placeholder="Message when someone joins your course…" multiline />
                    </View>
                ),
            },
            {
                key: 'launch',
                title: (
                    <Text style={s.title}>
                        Launch &{'\n'}<Text style={s.titleItalic}>go live</Text>
                    </Text>
                ),
                sub: 'Your max goes on the marketplace.',
                canNext: true,
                body: (
                    <LiquidGlass radius={22} intensity={68} noShadow style={[s.glassShell, { width: '100%' }]} contentStyle={s.glassPad}>
                        {[
                            `${habits.filter((h) => h.enabled !== false).length} habits ready`,
                            `Voice ${state?.voice_pct || 0}% trained (${state?.voice_samples_answered || 0} answers)`,
                            `$${((state?.price_cents || 0) / 100).toFixed(2)}/mo`,
                            welcomeMsg.trim() ? 'Welcome message set' : 'Welcome message missing',
                        ].map((line) => (
                            <View key={line} style={s.launchRow}>
                                <Ionicons name="checkmark-circle" size={18} color={INK} />
                                <Text style={s.launchLine}>{line}</Text>
                            </View>
                        ))}
                    </LiquidGlass>
                ),
            },
        ];
    }, [state, maxLabel, habits, habitTags, habitFilter, habitSearch, filteredHabits, voiceAnswer, correction, showCorrection, driveUrl, chatInput, welcomeMsg, introUrl, busy, docErr, testMode, testEngaged]);

    const current = steps[Math.min(step, steps.length - 1)];
    const isLast = step === steps.length - 1;

    if (loading) {
        return <View style={[s.root, s.center]}><ActivityIndicator color={INK} /></View>;
    }
    if (state?.complete) {
        navigation.replace('CreatorStudio');
        return null;
    }

    const ctaLabel = step === 2 ? 'Start teaching my voice →' : isLast ? 'Launch & go live' : 'Continue';

    return (
        <View style={s.root}>
            <View style={[s.frame, { paddingTop: insets.top + 14 }]}>
                <Text style={s.kicker}>STUDIO SETUP · {step + 1}/{steps.length}</Text>
                <View style={s.topRow}>
                    <TouchableOpacity
                        onPress={goBack}
                        style={[s.backBtn, busy && s.backBtnDisabled]}
                        hitSlop={12}
                        disabled={busy}
                        accessibilityLabel="Back"
                    >
                        <Ionicons name="chevron-back" size={22} color={busy ? MUTE : INK} />
                    </TouchableOpacity>
                    <ProgressBar index={step} total={steps.length} />
                </View>

                <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={8} style={{ flex: 1 }}>
                    <ScrollView
                        style={{ flex: 1 }}
                        contentContainerStyle={s.scrollBody}
                        showsVerticalScrollIndicator={false}
                        keyboardShouldPersistTaps="handled"
                    >
                        <Animated.View style={[s.headBlock, headStyle]}>
                            {current.title}
                            {current.sub ? <Text style={s.sub}>{current.sub}</Text> : null}
                        </Animated.View>
                        <Animated.View style={[s.bodyBlock, bodyStyle]}>
                            {current.body}
                            {error ? (
                                retryAction ? (
                                    <TouchableOpacity
                                        onPress={() => {
                                            const fn = retryAction;
                                            setError(null);
                                            setRetryAction(null);
                                            fn();
                                        }}
                                        activeOpacity={0.75}
                                        style={s.retryRow}
                                    >
                                        <Text style={s.error}>{error}</Text>
                                        <Text style={s.retryLink}>Retry</Text>
                                    </TouchableOpacity>
                                ) : (
                                    <Text style={s.error}>{error}</Text>
                                )
                            ) : null}
                        </Animated.View>
                    </ScrollView>

                    <View style={{ paddingBottom: insets.bottom + 16 }}>
                        {longWait && busy ? (
                            <TouchableOpacity onPress={cancelLongWait} activeOpacity={0.75} style={s.cancelWaitRow}>
                                <Text style={s.cancelWaitText}>Taking longer than usual? Cancel</Text>
                            </TouchableOpacity>
                        ) : null}
                        <PrimaryButton label={ctaLabel} onPress={goNext} loading={busy} disabled={!current.canNext} />
                    </View>
                </KeyboardAvoidingView>
            </View>

            <Modal visible={habitDraft != null} transparent animationType="slide" onRequestClose={() => setHabitDraft(null)}>
                <Pressable style={s.modalBackdrop} onPress={() => setHabitDraft(null)}>
                    <Pressable style={s.modalSheet} onPress={() => {}}>
                        {habitDraft ? (
                            <ScrollView contentContainerStyle={s.modalBody} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
                                <View style={s.modalHandle} />
                                <Text style={s.modalLabel}>Habit title</Text>
                                <Field
                                    value={habitDraft.title}
                                    onChangeText={(t) => setHabitDraft({ ...habitDraft, title: t })}
                                    placeholder="Habit name"
                                />
                                <Text style={s.modalLabel}>Description</Text>
                                <Field
                                    value={habitDraft.description || ''}
                                    onChangeText={(t) => setHabitDraft({ ...habitDraft, description: t })}
                                    placeholder="What subscribers do in this habit"
                                    multiline
                                />
                                <Text style={s.modalLabel}>Duration (minutes)</Text>
                                <Field
                                    value={String(habitDraft.duration_minutes || 10)}
                                    onChangeText={(t) => setHabitDraft({ ...habitDraft, duration_minutes: parseInt(t, 10) || 10 })}
                                    placeholder="10"
                                />
                                <Text style={s.modalLabel}>Shown to a user when</Text>
                                <Text style={s.docHint}>Tap to toggle who sees this habit.</Text>
                                <View style={s.presetWrap}>
                                    {targetingPresets.map((preset) => {
                                        const on = (habitDraft.conditions || []).includes(preset);
                                        return (
                                            <TouchableOpacity
                                                key={preset}
                                                style={[s.presetChip, on && s.presetChipOn]}
                                                onPress={() => toggleHabitCondition(preset)}
                                                activeOpacity={0.85}
                                            >
                                                <Text style={[s.presetChipText, on && s.presetChipTextOn]}>{preset}</Text>
                                            </TouchableOpacity>
                                        );
                                    })}
                                </View>
                                <Text style={s.modalLabel}>Questions subscribers ask</Text>
                                <Text style={s.docHint}>These are the kinds of questions that trigger this habit for a user.</Text>
                                {(habitDraft.sample_questions || []).map((q, i) => (
                                    <View key={i} style={s.bulletRow}>
                                        <Text style={s.bullet}>•</Text>
                                        <Text style={s.conditionLine}>{q}</Text>
                                    </View>
                                ))}
                                {(habitDraft.sample_questions || []).length === 0 ? (
                                    <Text style={s.docHint}>No sample questions yet — add some when editing via docs re-analyze.</Text>
                                ) : null}
                                <TouchableOpacity
                                    style={s.toggleRow}
                                    onPress={() => setHabitDraft({ ...habitDraft, enabled: !(habitDraft.enabled !== false) })}
                                    activeOpacity={0.85}
                                >
                                    <Ionicons
                                        name={habitDraft.enabled !== false ? 'checkbox' : 'square-outline'}
                                        size={20}
                                        color={INK}
                                    />
                                    <Text style={s.conditionLine}>Include in my max</Text>
                                </TouchableOpacity>
                                <PrimaryButton label="Save habit" onPress={saveHabitEdit} loading={busy} />
                                {habits.some((h) => h.id === habitDraft.id) ? (
                                    <TouchableOpacity style={s.removeHabitBtn} onPress={() => void removeHabit()} activeOpacity={0.85}>
                                        <Text style={s.removeHabitText}>Remove habit</Text>
                                    </TouchableOpacity>
                                ) : null}
                            </ScrollView>
                        ) : null}
                    </Pressable>
                </Pressable>
            </Modal>
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    frame: { flex: 1, width: '100%', maxWidth: 460, alignSelf: 'center', paddingHorizontal: 24 },
    center: { alignItems: 'center', justifyContent: 'center' },
    kicker: { fontFamily: 'Matter-SemiBold', fontSize: 11, letterSpacing: 1.2, color: MUTE, marginBottom: 10, textAlign: 'center' },
    topRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
    backBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: BACK_BG, alignItems: 'center', justifyContent: 'center', ...SOFT },
    backBtnDisabled: { opacity: 0.4 },
    progressTrack: { flex: 1, height: 6, borderRadius: 3, backgroundColor: TRACK, overflow: 'hidden' },
    progressFill: { height: '100%', borderRadius: 3, backgroundColor: INK },
    scrollBody: { flexGrow: 1, justifyContent: 'center', paddingVertical: 16 },
    headBlock: { width: '100%', alignItems: 'center' },
    bodyBlock: { width: '100%', marginTop: 26 },
    title: { fontFamily: 'Matter-Bold', fontSize: 30, color: INK, letterSpacing: -0.6, lineHeight: 36, textAlign: 'center' },
    titleItalic: { fontFamily: SERIF_I, fontStyle: 'italic' },
    sub: { fontFamily: 'Matter-Regular', fontSize: 15, color: SUB, marginTop: 12, lineHeight: 21, textAlign: 'center', maxWidth: 300, alignSelf: 'center' },
    error: { fontFamily: 'Matter-Medium', fontSize: 13.5, color: DANGER, marginTop: 18, lineHeight: 19, textAlign: 'center' },
    retryRow: { alignItems: 'center', gap: 4 },
    retryLink: { fontFamily: 'Matter-SemiBold', fontSize: 13.5, color: INK, textDecorationLine: 'underline' },
    cancelWaitRow: { alignItems: 'center', paddingVertical: 10 },
    cancelWaitText: { fontFamily: 'Matter-Medium', fontSize: 13, color: SUB, textDecorationLine: 'underline' },

    cta: { height: 54, borderRadius: 27, backgroundColor: INK, alignItems: 'center', justifyContent: 'center' },
    ctaDisabled: { backgroundColor: DISABLED },
    ctaText: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: ON_INK, letterSpacing: 0.2 },
    ctaTextDisabled: { color: DISABLED_TXT },

    fieldLine: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: HAIR, paddingBottom: 10 },
    input: { fontFamily: 'Matter-Medium', fontSize: 18, color: INK, padding: 0, lineHeight: 26 },
    inputMulti: { minHeight: 96, textAlignVertical: 'top', fontFamily: 'Matter-Regular', fontSize: 16, lineHeight: 24 },

    docRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: CARD, borderRadius: 14, padding: 12, ...CARD_BORDER },
    docIcon: { width: 34, height: 34, borderRadius: 10, backgroundColor: BG, alignItems: 'center', justifyContent: 'center' },
    docName: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: INK },
    docSub: { fontFamily: 'Matter-Regular', fontSize: 11.5, color: MUTE, marginTop: 2 },
    docHint: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: SUB, lineHeight: 18 },
    docBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: CARD, borderRadius: 14, paddingVertical: 14, ...CARD_BORDER },
    docBtnText: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: INK },
    driveRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    driveInput: { flex: 1, fontFamily: 'Matter-Regular', fontSize: 14, color: INK, backgroundColor: CARD, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, ...CARD_BORDER },
    linkBtn: { paddingHorizontal: 16, height: 40, borderRadius: 20, backgroundColor: BG, alignItems: 'center', justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth, borderColor: HAIR },
    linkBtnOff: { opacity: 0.45 },
    linkBtnText: { fontFamily: 'Matter-SemiBold', fontSize: 13.5, color: INK },
    docErr: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: DANGER, marginTop: 4 },

    glassPad: { padding: 20, gap: 14 },
    glassShell: { width: '100%', ...CARD_BORDER },
    meterRow: { gap: 8 },
    meterHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    meterLabel: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: INK },
    meterPct: { fontFamily: 'Matter-Medium', fontSize: 13, color: SUB },
    meterTrack: { height: 6, borderRadius: 3, backgroundColor: TRACK, overflow: 'hidden' },
    meterFill: { height: '100%', borderRadius: 3, backgroundColor: INK },
    meterHair: { height: StyleSheet.hairlineWidth, backgroundColor: HAIR },
    revealCopy: { fontFamily: 'Matter-Regular', fontSize: 14.5, color: SUB, lineHeight: 21, marginTop: 4 },

    phaseCard: { padding: 16, gap: 4 },
    phaseKicker: { fontFamily: 'Matter-SemiBold', fontSize: 11, color: MUTE, letterSpacing: 0.8, textTransform: 'uppercase' },
    phaseTitle: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: INK },
    phaseDesc: { fontFamily: 'Matter-Regular', fontSize: 13.5, color: SUB, lineHeight: 19 },

    quoteCard: { padding: 16, gap: 6 },
    quoteLabel: { fontFamily: 'Matter-SemiBold', fontSize: 11, letterSpacing: 0.8, color: MUTE, textTransform: 'uppercase' },
    quoteText: { fontFamily: 'Matter-Regular', fontSize: 16, color: INK, lineHeight: 23, fontStyle: 'italic' },
    draftLabel: { fontFamily: 'Matter-SemiBold', fontSize: 12, letterSpacing: 0.6, color: MUTE, textTransform: 'uppercase' },
    draftCard: { padding: 16 },
    draftText: { fontFamily: 'Matter-Regular', fontSize: 15, color: INK, lineHeight: 22 },
    feedbackRow: { flexDirection: 'row', gap: 10 },
    approveBtn: { flex: 1, flexDirection: 'row', gap: 6, backgroundColor: INK, borderRadius: 22, paddingVertical: 13, alignItems: 'center', justifyContent: 'center' },
    approveBtnText: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: ON_INK },
    editBtn: { flex: 1, flexDirection: 'row', gap: 6, backgroundColor: CARD, borderRadius: 22, paddingVertical: 13, alignItems: 'center', justifyContent: 'center', ...CARD_BORDER },
    editBtnText: { fontFamily: 'Matter-Medium', fontSize: 14, color: INK },
    secondaryPill: { alignSelf: 'center', paddingHorizontal: 20, paddingVertical: 11, borderRadius: 20, backgroundColor: CARD, ...CARD_BORDER },
    secondaryPillText: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: INK },
    voiceMeterCard: { padding: 14, gap: 8, backgroundColor: CARD, borderRadius: 14, ...CARD_BORDER },
    voiceMeterLabel: { fontFamily: 'Matter-SemiBold', fontSize: 12, color: MUTE, letterSpacing: 0.6, textTransform: 'uppercase' },
    voiceMeterSub: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: SUB },

    tagRow: { gap: 8, paddingBottom: 4 },
    tagChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: CARD, ...CARD_BORDER },
    tagChipOn: { backgroundColor: INK },
    tagChipText: { fontFamily: 'Matter-Medium', fontSize: 13, color: SUB },
    tagChipTextOn: { color: ON_INK },
    habitCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
    habitTitle: { fontFamily: 'Matter-SemiBold', fontSize: 15, color: INK },
    habitMeta: { fontFamily: 'Matter-Regular', fontSize: 12, color: MUTE, marginTop: 2 },
    habitQuestion: { fontFamily: 'Matter-Regular', fontSize: 11.5, color: SUB, marginTop: 4, fontStyle: 'italic' },
    phaseLead: { fontFamily: 'Matter-Regular', fontSize: 14, color: SUB, lineHeight: 20 },
    draftLoading: { alignItems: 'center', gap: 10, paddingVertical: 20 },
    searchRow: {
        flexDirection: 'row', alignItems: 'center', gap: 8,
        backgroundColor: CARD, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 10,
        ...CARD_BORDER,
    },
    searchInput: { flex: 1, fontFamily: 'Matter-Regular', fontSize: 14, color: INK, padding: 0 },
    testModeRow: { flexDirection: 'row', gap: 8 },
    testModeBtn: {
        flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
        paddingVertical: 10, borderRadius: 20, backgroundColor: CARD, ...CARD_BORDER,
    },
    testModeBtnOn: { backgroundColor: INK, borderColor: INK },
    testModeText: { fontFamily: 'Matter-Medium', fontSize: 12.5, color: INK },
    testModeTextOn: { color: ON_INK },
    removeHabitBtn: { alignItems: 'center', paddingVertical: 12, marginTop: 4 },
    removeHabitText: { fontFamily: 'Matter-Medium', fontSize: 14, color: DANGER },
    moreText: { fontFamily: 'Matter-Regular', fontSize: 13, color: MUTE, textAlign: 'center' },

    testActions: { flexDirection: 'row', gap: 10 },
    testActionInner: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 12 },
    testActionText: { fontFamily: 'Matter-Medium', fontSize: 13, color: INK },
    chatBox: { padding: 14, minHeight: 180 },
    chatEmpty: { fontFamily: 'Matter-Regular', fontSize: 14, color: MUTE, textAlign: 'center', paddingVertical: 40 },
    chatBubble: { padding: 11, borderRadius: 14, marginBottom: 8, maxWidth: '88%' },
    chatUser: { alignSelf: 'flex-end', backgroundColor: INK },
    chatMax: { alignSelf: 'flex-start', backgroundColor: CARD, ...CARD_BORDER },
    chatText: { fontFamily: 'Matter-Regular', fontSize: 14, color: INK, lineHeight: 20 },
    chatTextUser: { fontFamily: 'Matter-Regular', fontSize: 14, color: ON_INK, lineHeight: 20 },

    testStepLabel: { fontFamily: 'Matter-SemiBold', fontSize: 11, letterSpacing: 0.8, color: MUTE, textTransform: 'uppercase' },
    optionBtn: { backgroundColor: CARD, borderRadius: 14, paddingVertical: 14, paddingHorizontal: 16, ...CARD_BORDER },
    optionBtnText: { fontFamily: 'Matter-Medium', fontSize: 15, color: INK, lineHeight: 21 },
    scheduleDay: { backgroundColor: CARD, borderRadius: 14, padding: 14, gap: 6, ...CARD_BORDER },
    scheduleDayLabel: { fontFamily: 'Matter-Bold', fontSize: 15, color: INK },
    scheduleFocus: { fontFamily: 'Matter-Regular', fontSize: 13, color: SUB, marginBottom: 4 },
    scheduleTask: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingLeft: 4 },
    scheduleTaskText: { fontFamily: 'Matter-Regular', fontSize: 13, color: INK, flex: 1 },
    resetLink: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8 },
    resetLinkText: { fontFamily: 'Matter-Medium', fontSize: 13, color: SUB },

    presetWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    presetChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 16, backgroundColor: CARD, ...CARD_BORDER },
    presetChipOn: { backgroundColor: INK },
    presetChipText: { fontFamily: 'Matter-Medium', fontSize: 12.5, color: SUB },
    presetChipTextOn: { color: ON_INK },
    toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 8 },

    priceCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 18 },
    priceCardOn: { borderWidth: 1.5, borderColor: INK },
    priceLabel: { fontFamily: 'Matter-Bold', fontSize: 22, color: INK, letterSpacing: -0.4 },
    pricePer: { fontFamily: 'Matter-Regular', fontSize: 15, color: SUB },

    launchRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
    launchLine: { fontFamily: 'Matter-Regular', fontSize: 15, color: INK },

    modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end' },
    modalSheet: { backgroundColor: BG, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '78%' },
    modalBody: { padding: 24, paddingBottom: 40, gap: 10 },
    modalHandle: { width: 36, height: 4, borderRadius: 2, backgroundColor: TRACK, alignSelf: 'center', marginBottom: 8 },
    modalTitle: { fontFamily: 'Matter-Bold', fontSize: 22, color: INK, letterSpacing: -0.4 },
    modalLabel: { fontFamily: 'Matter-SemiBold', fontSize: 11, letterSpacing: 0.8, color: MUTE, textTransform: 'uppercase', marginTop: 12 },
    bulletRow: { flexDirection: 'row', gap: 8, paddingRight: 8 },
    bullet: { fontFamily: 'Matter-Regular', fontSize: 14, color: SUB },
    conditionLine: { flex: 1, fontFamily: 'Matter-Regular', fontSize: 14, color: INK, lineHeight: 21 },
});
