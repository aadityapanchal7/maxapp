/**
 * CreatorApplyScreen — multi-page "host your own max" application.
 *
 * Mirrors OnboardingV2Screen's flow: a thin top progress bar + back chevron, one
 * question per page with a staggered head/body transition, and a single bottom
 * "Continue" pill. Steps: intro → name → the max (with first-come availability
 * check) → what-it-is/why-you → sign in to Instagram/TikTok (OAuth) → review →
 * submit. Success shows a confirmation page ("we'll get back to you in 1–2 weeks")
 * whose Done returns to the Creator tab.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TextInput,
    TouchableOpacity,
    ScrollView,
    ActivityIndicator,
    Platform,
    KeyboardAvoidingView,
    AppState,
} from 'react-native';
import Animated, {
    Easing, Extrapolation, interpolate, useAnimatedStyle,
    useReducedMotion, useSharedValue, withTiming,
} from 'react-native-reanimated';
import { Image as ExpoImage } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import * as Haptics from 'expo-haptics';
import * as WebBrowser from 'expo-web-browser';
import { api, type CreatorSocialConnection, type SocialProfile } from '../../services/api';
import * as DocumentPicker from 'expo-document-picker';
import { openCreatorSocialAuth } from '../../lib/creatorSocialConnect';

WebBrowser.maybeCompleteAuthSession();

// Onboarding "Stoic" palette (kept identical so the flow feels native to it).
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
const VERIFIED = '#3B82F6';

/** Flip to true when Instagram/TikTok OAuth is configured — restores mandatory social step. */
const CREATOR_SOCIAL_REQUIRED = true;

const SOFT = {
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 }, elevation: 2,
};

function fmtFollowers(n: number | null): string | null {
    if (n == null) return null;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}K`;
    return String(n);
}

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

function PrimaryButton({ label, onPress, loading, disabled }: {
    label: string; onPress?: () => void; loading?: boolean; disabled?: boolean;
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
        >
            {loading ? <ActivityIndicator color={ON_INK} /> : <Text style={[styles.ctaText, dim && styles.ctaTextDisabled]}>{label}</Text>}
        </TouchableOpacity>
    );
}

/** A bare hairline-underline text field (editorial, not boxy). */
function Field({ value, onChangeText, placeholder, multiline, autoCapitalize, autoFocus, maxLength }: {
    value: string; onChangeText: (t: string) => void; placeholder: string;
    multiline?: boolean; autoCapitalize?: 'none' | 'sentences' | 'words'; autoFocus?: boolean; maxLength?: number;
}) {
    return (
        <View style={styles.fieldLine}>
            <TextInput
                style={[styles.input, multiline && styles.inputMulti]}
                value={value}
                onChangeText={onChangeText}
                placeholder={placeholder}
                placeholderTextColor={MUTE}
                multiline={multiline}
                autoCapitalize={autoCapitalize ?? 'sentences'}
                autoCorrect={autoCapitalize !== 'none'}
                autoFocus={autoFocus}
                maxLength={maxLength}
            />
        </View>
    );
}

/** Subtle "N/max" counter — only appears once the field is getting close to its limit. */
function CharCounter({ length, max }: { length: number; max: number }) {
    if (length < max - 300) return null;
    return (
        <Text style={[styles.charCounter, length >= max && styles.charCounterAtLimit]}>
            {length}/{max}
        </Text>
    );
}

function connectionToProfile(conn: CreatorSocialConnection): SocialProfile {
    return {
        platform: conn.platform,
        handle: conn.handle || '',
        url: conn.platform === 'instagram'
            ? `https://instagram.com/${conn.handle}`
            : `https://www.tiktok.com/@${conn.handle}`,
        followers: conn.followers,
        avatar_url: conn.avatar_url,
        full_name: conn.full_name,
        verified: conn.verified,
        found: true,
        oauth_verified: true,
    };
}

/** Link row — tap Link to open real Instagram/TikTok OAuth in browser. */
function SocialLinker({
    platform,
    profile,
    onClear,
    onLinked,
}: {
    platform: 'instagram' | 'tiktok';
    profile: SocialProfile | null;
    onClear: () => void;
    onLinked: () => void;
}) {
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState<string | null>(null);
    const meta = platform === 'instagram'
        ? { label: 'Instagram', icon: 'logo-instagram' as const }
        : { label: 'TikTok', icon: 'logo-tiktok' as const };

    const link = async () => {
        setLoading(true); setErr(null);
        Haptics.selectionAsync().catch(() => {});
        try {
            await openCreatorSocialAuth(platform);
            onLinked();
        } catch {
            setErr(`Couldn't open ${meta.label}. Check that OAuth is configured on the server.`);
        } finally {
            setLoading(false);
        }
    };

    const disconnect = async () => {
        Haptics.selectionAsync().catch(() => {});
        try { await api.disconnectCreatorSocial(platform); } catch { /* best-effort */ }
        onClear();
    };

    if (profile) {
        const followers = fmtFollowers(profile.followers);
        return (
            <View style={styles.linkedCard}>
                <View style={styles.linkedAvatarWrap}>
                    {profile.avatar_url ? (
                        <ExpoImage source={{ uri: profile.avatar_url }} style={styles.linkedAvatar} contentFit="cover" />
                    ) : (
                        <Ionicons name={meta.icon} size={22} color={INK} />
                    )}
                </View>
                <View style={{ flex: 1 }}>
                    <View style={styles.linkedNameRow}>
                        <Text style={styles.linkedName} numberOfLines={1}>
                            {profile.full_name || `@${profile.handle}`}
                        </Text>
                        <View style={styles.oauthBadge}><Text style={styles.oauthBadgeText}>Linked</Text></View>
                    </View>
                    <Text style={styles.linkedMeta} numberOfLines={1}>
                        @{profile.handle}{followers ? ` · ${followers} followers` : ''}
                    </Text>
                </View>
                <TouchableOpacity onPress={disconnect} hitSlop={10}>
                    <Ionicons name="close-circle" size={22} color={MUTE} />
                </TouchableOpacity>
            </View>
        );
    }

    return (
        <View style={styles.linkerBlock}>
            <View style={styles.linkerRow}>
                <Ionicons name={meta.icon} size={20} color={SUB} style={{ marginRight: 10 }} />
                <Text style={styles.linkerLabel}>Link {meta.label}</Text>
                <TouchableOpacity
                    style={[styles.linkBtn, loading && styles.linkBtnOff]}
                    onPress={link}
                    disabled={loading}
                    activeOpacity={0.85}
                >
                    {loading ? <ActivityIndicator size="small" color={INK} /> : <Text style={styles.linkBtnText}>Link</Text>}
                </TouchableOpacity>
            </View>
            {err ? <Text style={styles.linkErr}>{err}</Text> : null}
        </View>
    );
}

type CourseDoc = { filename: string; url: string; source?: string; size_bytes?: number };

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

function driveLinkDoc(url: string): CourseDoc {
    const source = /drive\.google|docs\.google/i.test(url) ? 'gdrive' : 'link';
    return { filename: 'Google Drive link', url, source };
}

function DocUploader({ docs, onChange }: {
    docs: CourseDoc[];
    onChange: React.Dispatch<React.SetStateAction<CourseDoc[]>>;
}) {
    const [driveUrl, setDriveUrl] = useState('');
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState<string | null>(null);

    const pickLocal = async () => {
        setBusy(true); setErr(null);
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
                            const data = await api.uploadCreatorDoc(file);
                            onChange((prev) => [...prev, data]);
                        } catch (e) {
                            setErr(apiDetail(e) || 'Could not upload that file.');
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
            const picked = await DocumentPicker.getDocumentAsync({
                copyToCacheDirectory: true,
                multiple: false,
            });
            if (picked.canceled || !picked.assets?.[0]) return;
            const asset = picked.assets[0];
            const data = await api.uploadCreatorDoc({
                uri: asset.uri,
                name: asset.name || 'document',
                type: asset.mimeType || 'application/octet-stream',
            });
            onChange((prev) => [...prev, data]);
        } catch (e) {
            setErr(apiDetail(e) || 'Could not upload that file.');
        } finally {
            setBusy(false);
        }
    };

    const addDrive = () => {
        const url = normalizeDocUrl(driveUrl);
        if (!url) return;
        setErr(null);
        onChange((prev) => [...prev, driveLinkDoc(url)]);
        setDriveUrl('');
    };

    return (
        <View style={{ gap: 12 }}>
            <Text style={styles.docHint}>
                Pasted links are reference-only for our review — Max doesn't read them. Upload a .txt, .md, or
                PDF file for content Max actually learns from. Max reads ~the first 4,000 characters, so lead
                with your core protocols.
            </Text>
            {docs.map((d, i) => (
                <View key={`${d.url}-${i}`} style={styles.docRow}>
                    <Ionicons
                        name={d.source === 'gdrive' ? 'logo-google' : 'document-text-outline'}
                        size={18}
                        color={INK}
                    />
                    <View style={{ flex: 1 }}>
                        <Text style={styles.docName} numberOfLines={1}>{d.filename}</Text>
                        <Text style={styles.docSub} numberOfLines={1}>
                            {d.source === 'gdrive' ? 'Google Drive' : d.source === 'local' ? 'Uploaded file' : 'Link'}
                        </Text>
                    </View>
                    <TouchableOpacity onPress={() => onChange((prev) => prev.filter((_, j) => j !== i))}>
                        <Ionicons name="trash-outline" size={18} color={DANGER} />
                    </TouchableOpacity>
                </View>
            ))}
            <TouchableOpacity style={styles.docBtn} onPress={pickLocal} disabled={busy}>
                <Ionicons name="folder-open-outline" size={18} color={INK} />
                <Text style={styles.docBtnText}>Add from device</Text>
            </TouchableOpacity>
            <View style={styles.driveRow}>
                <TextInput
                    style={styles.driveInput}
                    value={driveUrl}
                    onChangeText={setDriveUrl}
                    placeholder="Paste Google Drive link"
                    placeholderTextColor={MUTE}
                    autoCapitalize="none"
                    keyboardType="url"
                    onSubmitEditing={() => void addDrive()}
                />
                <TouchableOpacity style={styles.linkBtn} onPress={addDrive} disabled={busy || !driveUrl.trim()}>
                    <Text style={styles.linkBtnText}>Add</Text>
                </TouchableOpacity>
            </View>
            {err ? <Text style={styles.linkErr}>{err}</Text> : null}
        </View>
    );
}

export default function CreatorApplyScreen() {
    const insets = useSafeAreaInsets();
    const navigation = useNavigation<any>();

    const [step, setStep] = useState(0);
    const [dir, setDir] = useState(1);

    const [name, setName] = useState('');
    const [maxName, setMaxName] = useState('');
    const [desc, setDesc] = useState('');
    const [differentiator, setDifferentiator] = useState('');
    const [brandFit, setBrandFit] = useState('');
    const [courseDocs, setCourseDocs] = useState<CourseDoc[]>([]);
    const [igProfile, setIgProfile] = useState<SocialProfile | null>(null);
    const [ttProfile, setTtProfile] = useState<SocialProfile | null>(null);

    const refreshSocialStatus = useCallback(async (): Promise<boolean> => {
        try {
            const status = await api.getCreatorSocialStatus();
            const igConn = status.connections.instagram;
            const ttConn = status.connections.tiktok;
            if (igConn?.handle) setIgProfile(connectionToProfile(igConn));
            if (ttConn?.handle) setTtProfile(connectionToProfile(ttConn));
            return Boolean(igConn?.handle || ttConn?.handle);
        } catch {
            /* status fetch is best-effort */
            return false;
        }
    }, []);

    // After the OAuth sheet closes we poll: Post for Me registers the linked
    // account a beat later (no redirect back to the app on Quickstart projects),
    // so a single fetch can miss it. Backend /status pulls from Post for Me by
    // external_id on each call, so we just re-hit it a few times.
    const pollSocialStatus = useCallback(async () => {
        for (let i = 0; i < 6; i++) {
            if (await refreshSocialStatus()) return;
            await new Promise((r) => setTimeout(r, 1500));
        }
    }, [refreshSocialStatus]);

    useEffect(() => {
        if (!CREATOR_SOCIAL_REQUIRED) return;
        void refreshSocialStatus();
    }, [refreshSocialStatus]);

    // Re-fetch after OAuth sheet closes (native) or app returns to foreground (web popup).
    useEffect(() => {
        if (!CREATOR_SOCIAL_REQUIRED) return;
        const sub = AppState.addEventListener('change', (state) => {
            if (state === 'active') void refreshSocialStatus();
        });
        return () => sub.remove();
    }, [refreshSocialStatus]);

    const [checkingMax, setCheckingMax] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [done, setDone] = useState(false);

    const hasSocial = igProfile != null || ttProfile != null;

    const steps = useMemo(() => {
        const all = [
        {
            key: 'intro',
            title: 'Own your\nmax',
            sub: 'A max is a creator-led routine. If you’re known for something, or it’s your niche, claim it and bring your audience the real thing.',
            canNext: true,
            body: (
                <View style={styles.introWrap}>
                    {[
                        ['ribbon-outline', 'For people known for their craft', 'Your reputation is the pitch, not a CV.'],
                        ['flash-outline', 'First come, first served', 'Once someone claims a niche, it’s gone.'],
                        ['time-outline', 'Hand-reviewed', 'We read each one and reply in 1-2 weeks.'],
                    ].map(([icon, t, s]) => (
                        <View key={t} style={styles.introRow}>
                            <View style={styles.introIcon}><Ionicons name={icon as any} size={18} color={INK} /></View>
                            <View style={{ flex: 1 }}>
                                <Text style={styles.introT}>{t}</Text>
                                <Text style={styles.introS}>{s}</Text>
                            </View>
                        </View>
                    ))}
                </View>
            ),
        },
        {
            key: 'name',
            title: 'What’s your\nname?',
            sub: 'However your audience knows you.',
            canNext: name.trim().length > 0,
            body: <Field value={name} onChangeText={setName} placeholder="Your name" autoCapitalize="words" autoFocus maxLength={120} />,
        },
        {
            key: 'max',
            title: 'Which max\nwould you own?',
            sub: 'Name the niche you’d lead. One creator per max, so claim yours first.',
            canNext: maxName.trim().length > 0,
            body: (
                <View>
                    <Field value={maxName} onChangeText={(t) => { setMaxName(t); if (error) setError(null); }} placeholder="e.g. Chessmax, Voicemax, Stylemax" autoCapitalize="words" autoFocus maxLength={80} />
                </View>
            ),
        },
        {
            key: 'desc',
            title: 'What is\nyour max?',
            sub: 'What does it teach? Who is it for?',
            canNext: desc.trim().length > 0,
            body: (
                <View>
                    <Field value={desc} onChangeText={setDesc} placeholder="The routine, the promise…" multiline autoFocus maxLength={1500} />
                    <CharCounter length={desc.length} max={1500} />
                </View>
            ),
        },
        {
            key: 'different',
            title: 'What makes it\ndifferent?',
            sub: 'Why yours stands out from everything else out there.',
            canNext: differentiator.trim().length > 0,
            body: (
                <View>
                    <Field value={differentiator} onChangeText={setDifferentiator} placeholder="Your edge, your method…" multiline autoFocus maxLength={1500} />
                    <CharCounter length={differentiator.length} max={1500} />
                </View>
            ),
        },
        {
            key: 'brand',
            title: 'Why it fits\nyour brand',
            sub: 'How this max connects to what your audience already knows you for.',
            canNext: brandFit.trim().length > 0,
            body: (
                <View>
                    <Field value={brandFit} onChangeText={setBrandFit} placeholder="Your brand, your audience, your lane…" multiline autoFocus maxLength={1500} />
                    <CharCounter length={brandFit.length} max={1500} />
                </View>
            ),
        },
        {
            key: 'social',
            title: 'Link your\naccounts',
            sub: 'Connect at least one so we can verify it\'s you.',
            canNext: hasSocial,
            body: (
                <View style={{ gap: 14 }}>
                    <SocialLinker platform="instagram" profile={igProfile} onClear={() => setIgProfile(null)} onLinked={pollSocialStatus} />
                    <SocialLinker platform="tiktok" profile={ttProfile} onClear={() => setTtProfile(null)} onLinked={pollSocialStatus} />
                </View>
            ),
        },
        {
            key: 'docs',
            title: 'Course\nmaterials',
            sub: 'Upload docs, PDFs, or paste Google Drive links for your max.',
            canNext: true,
            body: <DocUploader docs={courseDocs} onChange={setCourseDocs} />,
        },
        {
            key: 'review',
            title: 'Look\nright?',
            sub: 'Submit and we’ll take it from here.',
            canNext: true,
            body: (
                <View style={styles.reviewCard}>
                    <ReviewRow label="Name" value={name.trim()} />
                    <View style={styles.reviewHair} />
                    <ReviewRow label="The max" value={maxName.trim()} />
                    <View style={styles.reviewHair} />
                    <ReviewRow label="About" value={desc.trim()} />
                    <View style={styles.reviewHair} />
                    <ReviewRow label="Different" value={differentiator.trim()} />
                    <View style={styles.reviewHair} />
                    <ReviewRow label="Brand fit" value={brandFit.trim()} />
                    {igProfile ? (
                        <>
                            <View style={styles.reviewHair} />
                            <ReviewRow label="Instagram" value={`@${igProfile.handle}`} />
                        </>
                    ) : null}
                    {ttProfile ? (
                        <>
                            <View style={styles.reviewHair} />
                            <ReviewRow label="TikTok" value={`@${ttProfile.handle}`} />
                        </>
                    ) : null}
                    {courseDocs.length ? (
                        <>
                            <View style={styles.reviewHair} />
                            <ReviewRow label="Docs" value={`${courseDocs.length} file(s)`} />
                        </>
                    ) : null}
                </View>
            ),
        },
    ];
        return CREATOR_SOCIAL_REQUIRED ? all : all.filter((s) => s.key !== 'social');
    }, [name, maxName, desc, differentiator, brandFit, courseDocs, igProfile, ttProfile, hasSocial, error, pollSocialStatus]);

    const safeStep = Math.min(step, steps.length - 1);
    const current = steps[safeStep];
    const isLast = safeStep === steps.length - 1;

    // Tracks which step goNext launched from, so its async availability check
    // never forces a late-resolving result onto a step the applicant already left.
    const stepRef = useRef(safeStep);
    useEffect(() => { stepRef.current = safeStep; }, [safeStep]);

    const goBack = () => {
        if (submitting || checkingMax) return; // don't let the applicant navigate away from an in-flight request
        if (safeStep === 0) { navigation.goBack(); return; }
        Haptics.selectionAsync().catch(() => {});
        setDir(-1); setStep(safeStep - 1); setError(null);
    };

    const submit = async () => {
        setSubmitting(true); setError(null);
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
        try {
            await api.submitCreatorApplication({
                applicant_name: name.trim(),
                max_name: maxName.trim(),
                max_description: desc.trim(),
                max_differentiator: differentiator.trim(),
                brand_fit: brandFit.trim(),
                course_docs: courseDocs,
            });
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
            setDone(true);
        } catch (e: any) {
            const status = e?.response?.status;
            const detail = e?.response?.data?.detail;
            if (status === 409) {
                // The max got claimed — bounce back to the max step to pick another.
                setError(detail || "Someone's already in line for this max. Try a different niche.");
                setDir(-1);
                setStep(2);
            } else {
                setError(detail || 'Could not submit right now. Please try again in a moment.');
            }
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
        } finally {
            setSubmitting(false);
        }
    };

    const goNext = async () => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        const fromStep = safeStep;
        // First-come-first-served pre-check on the max step.
        if (current.key === 'max') {
            setCheckingMax(true); setError(null);
            try {
                const res = await api.checkMaxAvailability(maxName.trim());
                if (stepRef.current !== fromStep) return; // applicant moved off this step while we were checking
                if (!res.available) {
                    setError("That max is taken. It's first come, first served — try another niche.");
                    setCheckingMax(false);
                    return;
                }
            } catch {
                // availability check is best-effort; don't block on a network blip
            } finally {
                setCheckingMax(false);
            }
        }
        if (stepRef.current !== fromStep) return;
        if (isLast) { void submit(); return; }
        setDir(1); setStep(safeStep + 1); setError(null);
    };

    // Staggered page transition (head leads, body follows) — same as onboarding.
    const reduced = useReducedMotion();
    const t = useSharedValue(1);
    useEffect(() => {
        if (reduced) { t.value = 1; return; }
        t.value = 0;
        t.value = withTiming(1, { duration: 460, easing: Easing.out(Easing.cubic) });
    }, [safeStep, reduced, t]);
    const headStyle = useAnimatedStyle(() => ({
        opacity: interpolate(t.value, [0, 0.6], [0, 1], Extrapolation.CLAMP),
        transform: [{ translateX: interpolate(t.value, [0, 1], [dir * 34, 0], Extrapolation.CLAMP) }],
    }));
    const bodyStyle = useAnimatedStyle(() => ({
        opacity: interpolate(t.value, [0.18, 0.9], [0, 1], Extrapolation.CLAMP),
        transform: [{ translateY: interpolate(t.value, [0.18, 1], [16, 0], Extrapolation.CLAMP) }],
    }));

    if (done) return <Confirmation onDone={() => navigation.goBack()} insets={insets} />;

    return (
        <View style={styles.root}>
            <View style={[styles.frame, { paddingTop: insets.top + 14 }]}>
                <View style={styles.topRow}>
                    <TouchableOpacity onPress={goBack} style={styles.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }} accessibilityLabel="Back">
                        <Ionicons name="chevron-back" size={22} color={INK} />
                    </TouchableOpacity>
                    <ProgressBar index={safeStep} total={steps.length} />
                </View>

                <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={8} style={{ flex: 1 }}>
                    <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scrollBody} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
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
                        <PrimaryButton
                            label={isLast ? 'Submit application' : 'Continue'}
                            loading={submitting || checkingMax}
                            disabled={!current.canNext}
                            onPress={goNext}
                        />
                    </View>
                </KeyboardAvoidingView>
            </View>
        </View>
    );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
    return (
        <View style={styles.reviewRow}>
            <Text style={styles.reviewLabel}>{label}</Text>
            <Text style={styles.reviewValue}>{value}</Text>
        </View>
    );
}

function Confirmation({ onDone, insets }: { onDone: () => void; insets: { top: number; bottom: number } }) {
    return (
        <View style={[styles.root, { paddingTop: insets.top, paddingBottom: insets.bottom + 16 }]}>
            <View style={styles.confirmWrap}>
                <View style={styles.confirmCheck}><Ionicons name="checkmark" size={36} color={INK} /></View>
                <Text style={styles.confirmTitle}>You&apos;re in the queue</Text>
                <Text style={styles.confirmBody}>
                    Application received. We&apos;ll review your work and your socials, and get back to you in{' '}
                    <Text style={styles.confirmStrong}>1–2 weeks</Text>.
                </Text>
            </View>
            <View style={{ paddingHorizontal: 24 }}>
                <PrimaryButton label="Done" onPress={onDone} />
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    frame: { flex: 1, width: '100%', maxWidth: 460, alignSelf: 'center', paddingHorizontal: 24 },

    topRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
    backBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: BACK_BG, alignItems: 'center', justifyContent: 'center', ...SOFT },
    progressTrack: { flex: 1, height: 6, borderRadius: 3, backgroundColor: TRACK, overflow: 'hidden' },
    progressFill: { height: '100%', borderRadius: 3, backgroundColor: INK },

    scrollBody: { flexGrow: 1, justifyContent: 'center', paddingVertical: 16 },
    headBlock: { width: '100%', alignItems: 'center' },
    bodyBlock: { width: '100%', marginTop: 26 },
    title: { fontFamily: 'Matter-Bold', fontSize: 30, color: INK, letterSpacing: -0.6, lineHeight: 36, textAlign: 'center' },
    sub: { fontFamily: 'Matter-Regular', fontSize: 15, color: SUB, marginTop: 12, lineHeight: 21, textAlign: 'center', maxWidth: 286, alignSelf: 'center' },
    helpNote: { fontFamily: 'Matter-Regular', fontSize: 13, color: MUTE, marginTop: 14, lineHeight: 18, textAlign: 'center' },
    error: { fontFamily: 'Matter-Medium', fontSize: 13.5, color: DANGER, marginTop: 18, lineHeight: 19, textAlign: 'center' },

    // intro
    introWrap: { gap: 18, paddingHorizontal: 4 },
    introRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 14 },
    introIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: CARD, alignItems: 'center', justifyContent: 'center', ...SOFT },
    introT: { fontFamily: 'Matter-SemiBold', fontSize: 15.5, color: INK },
    introS: { fontFamily: 'Matter-Regular', fontSize: 13.5, color: SUB, marginTop: 3, lineHeight: 19 },

    // hairline-underline field
    fieldLine: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: HAIR, paddingBottom: 10 },
    input: { fontFamily: 'Matter-Medium', fontSize: 22, color: INK, padding: 0, textAlign: 'center', lineHeight: 28 },
    inputMulti: { minHeight: 96, textAlignVertical: 'top', textAlign: 'left', fontSize: 18, lineHeight: 26, fontFamily: 'Matter-Regular' },
    charCounter: { fontFamily: 'Matter-Regular', fontSize: 12, color: MUTE, textAlign: 'right', marginTop: 6 },
    charCounterAtLimit: { color: DANGER },

    // social linker
    linkerBlock: { gap: 12 },
    linkerRow: {
        flexDirection: 'row', alignItems: 'center',
        backgroundColor: CARD, borderRadius: 16, paddingHorizontal: 14, height: 56, ...SOFT,
    },
    linkerAt: { fontFamily: 'Matter-Medium', fontSize: 16, color: SUB, marginRight: 2, marginLeft: 4 },
    linkerLabel: { flex: 1, fontFamily: 'Matter-Medium', fontSize: 16, color: INK },
    linkerInput: { flex: 1, fontFamily: 'Matter-Medium', fontSize: 16, color: INK, padding: 0, marginRight: 4 },
    linkBtn: { paddingHorizontal: 16, height: 36, borderRadius: 18, backgroundColor: BG, alignItems: 'center', justifyContent: 'center' },
    linkBtnOff: { opacity: 0.5 },
    linkBtnText: { fontFamily: 'Matter-SemiBold', fontSize: 13.5, color: INK },
    linkErr: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: DANGER, marginTop: 8, marginLeft: 4 },

    oauthBadge: { backgroundColor: '#DCFCE7', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
    oauthBadgeText: { fontFamily: 'Matter-SemiBold', fontSize: 10, color: '#166534' },
    docRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: CARD, borderRadius: 12, padding: 12, ...SOFT },
    docName: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: INK },
    docSub: { fontFamily: 'Matter-Regular', fontSize: 11.5, color: MUTE, marginTop: 2 },
    docHint: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: SUB, lineHeight: 18 },
    docBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: CARD, borderRadius: 14, paddingVertical: 14, ...SOFT },
    docBtnText: { fontFamily: 'Matter-SemiBold', fontSize: 14, color: INK },
    driveRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    driveInput: { flex: 1, fontFamily: 'Matter-Regular', fontSize: 14, color: INK, backgroundColor: CARD, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, ...SOFT },

    linkedCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: CARD, borderRadius: 16, padding: 12, ...SOFT },
    linkedAvatarWrap: { width: 46, height: 46, borderRadius: 23, backgroundColor: BG, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
    linkedAvatar: { width: '100%', height: '100%' },
    linkedNameRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
    linkedName: { fontFamily: 'Matter-SemiBold', fontSize: 15.5, color: INK, flexShrink: 1 },
    linkedMeta: { fontFamily: 'Matter-Regular', fontSize: 12.5, color: SUB, marginTop: 2 },

    // review
    reviewCard: { backgroundColor: CARD, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 4, ...SOFT },
    reviewRow: { paddingVertical: 14 },
    reviewLabel: { fontFamily: 'Matter-SemiBold', fontSize: 11, letterSpacing: 1, color: MUTE, marginBottom: 4 },
    reviewValue: { fontFamily: 'Matter-Regular', fontSize: 15, color: INK, lineHeight: 21 },
    reviewHair: { height: StyleSheet.hairlineWidth, backgroundColor: HAIR },

    // confirmation
    confirmWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32 },
    confirmCheck: { width: 80, height: 80, borderRadius: 40, alignItems: 'center', justifyContent: 'center', backgroundColor: CARD, borderWidth: 1.5, borderColor: INK, marginBottom: 24, ...SOFT },
    confirmTitle: { fontFamily: 'Matter-Bold', fontSize: 30, color: INK, letterSpacing: -0.6, textAlign: 'center' },
    confirmBody: { fontFamily: 'Matter-Regular', fontSize: 15, color: SUB, lineHeight: 23, textAlign: 'center', marginTop: 14, maxWidth: 320 },
    confirmStrong: { fontFamily: 'Matter-SemiBold', color: INK },

    // CTA
    cta: { height: 54, borderRadius: 27, backgroundColor: INK, alignItems: 'center', justifyContent: 'center' },
    ctaDisabled: { backgroundColor: DISABLED },
    ctaText: { fontFamily: 'Matter-SemiBold', fontSize: 16, color: ON_INK, letterSpacing: 0.2 },
    ctaTextDisabled: { color: DISABLED_TXT },
});
