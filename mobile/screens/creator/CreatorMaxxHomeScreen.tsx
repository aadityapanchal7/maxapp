/**
 * CreatorMaxxHomeScreen — the member home for a creator maxx (route
 * 'CreatorMaxxHome', params { maxxId, tab? }).
 *
 * Layout: compact art banner (~120pt) + overlapping avatar identity row →
 * PROGRAM STRIP (today's done/total from the active schedule, or an
 * "Add to your day" bootstrap when no schedule exists yet) → pill tabs
 * Updates | Course | Community. Updates/Course embed the shared
 * CreatorFeedList / CreatorCourseList; Community embeds ChannelList (the
 * creator's members channels → ChannelChat).
 *
 * Non-subscribers (and non-owners) get a lock card → CreatorPaywall.
 */
import React, { useMemo, useState } from 'react';
import {
    ActivityIndicator,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Image as ExpoImage } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { queryKeys } from '../../lib/queryClient';
import { fonts } from '../../theme/dark';
import { hexA, normalizeMaxxId } from '../../utils/scheduleAggregation';
import CreatorFeedList from '../../components/creator/CreatorFeedList';
import CreatorCourseList from '../../components/creator/CreatorCourseList';
import ChannelList from '../../components/creator/ChannelList';

const INK = '#111113';
const MUTE = '#6B6B6B';
const BG = '#F1F1EF';
const CARD = '#FFFFFF';
const HAIR = 'rgba(0,0,0,0.08)';

type HomeTab = 'updates' | 'course' | 'community';
const TABS: { key: HomeTab; label: string }[] = [
    { key: 'updates', label: 'Updates' },
    { key: 'course', label: 'Course' },
    { key: 'community', label: 'Community' },
];

export default function CreatorMaxxHomeScreen() {
    const nav = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const maxxId: string = route.params?.maxxId;
    const previewLocked: boolean = !!route.params?.previewLocked;
    const seedTab: HomeTab = (['updates', 'course', 'community'] as const).includes(route.params?.tab)
        ? route.params?.tab
        : 'updates';

    const [tab, setTab] = useState<HomeTab>(seedTab);
    const [bootstrapping, setBootstrapping] = useState(false);

    // Creator header data + subscribed/is_owner (same key MaxDetail uses).
    const creatorQ = useQuery({
        queryKey: ['creator', 'by-maxx', maxxId],
        queryFn: () => api.getCreatorByMaxx(maxxId),
        enabled: !!maxxId,
        staleTime: 60_000,
        retry: 1,
    });
    // Active schedules — the canonical key so celebrations/invalidations stay
    // in the one shared cache (queryKeys.schedulesActiveFull).
    const schedulesQ = useQuery({
        queryKey: queryKeys.schedulesActiveFull,
        queryFn: () => api.getActiveSchedulesFull(),
        staleTime: 60_000,
    });

    const creator: any = creatorQ.data;
    const accent = creator?.accent_color || '#BC7A3C';

    // Today's done/total for THIS maxx's schedule — mirrors the aggregation
    // Explore's "Active" tab uses (loadMine in MarketplaceScreen).
    const program = useMemo(() => {
        const full: any = schedulesQ.data;
        const target = normalizeMaxxId(maxxId);
        if (!target) return null;
        const sched = (full?.schedules || []).find(
            (sc: any) => normalizeMaxxId(sc?.maxx_id) === target,
        );
        if (!sched) return null;
        const today = full?.today_date;
        const days = sched?.days || [];
        const todayDay = today ? days.find((dd: any) => dd?.date === today) : days[0];
        const tasks = (todayDay?.tasks || []) as any[];
        const done = tasks.filter((t) => t?.status === 'completed').length;
        return { scheduleId: String(sched?.id || ''), total: tasks.length, done };
    }, [schedulesQ.data, maxxId]);

    // "Add to your day" — free/subscribed users get the schedule created
    // server-side by /marketplace/enter; paid non-subscribers bounce to the
    // creator paywall.
    const bootstrap = async () => {
        if (bootstrapping) return;
        setBootstrapping(true);
        try {
            const res = await api.enterMarketplaceItem(maxxId);
            if (res.entered) {
                await Promise.all([
                    queryClient.invalidateQueries({
                        queryKey: queryKeys.schedulesActiveFull,
                        refetchType: 'all',
                    }),
                    // `subscribed` on this query drives the lock card.
                    queryClient.invalidateQueries({
                        queryKey: ['creator', 'by-maxx', maxxId],
                        refetchType: 'all',
                    }),
                ]);
            } else if (res.requires === 'creator_subscription') {
                nav.navigate('CreatorPaywall', { maxxId });
            }
        } catch { /* best-effort — the strip stays on the bootstrap pill */ }
        finally { setBootstrapping(false); }
    };

    if (creatorQ.isLoading) {
        return (
            <View style={[s.root, s.center]}>
                <ActivityIndicator color={INK} />
            </View>
        );
    }

    if (creatorQ.isError || !creator) {
        return (
            <View style={[s.root, s.center, { paddingHorizontal: 32 }]}>
                <Text style={s.errorText}>Couldn't load this creator. Check your connection and retry.</Text>
                <TouchableOpacity
                    style={s.retryBtn}
                    onPress={() => { void creatorQ.refetch(); }}
                    activeOpacity={0.85}
                    accessibilityRole="button"
                    accessibilityLabel="Retry"
                >
                    <Text style={s.retryText}>Retry</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => nav.goBack()} hitSlop={12} style={[s.back, { position: 'absolute', top: insets.top + 6, left: 14 }]} accessibilityLabel="Back">
                    <Ionicons name="chevron-back" size={22} color={INK} />
                </TouchableOpacity>
            </View>
        );
    }

    // `previewLocked` forces the paywalled view even for the owner — the
    // "Preview as member (locked)" entry point from Studio.
    const locked = previewLocked || (!creator.subscribed && !creator.is_owner);
    const members = Number(creator.subscriber_count || 0);
    const art = creator.art_url ? api.resolveAttachmentUrl(creator.art_url) : undefined;
    const avatar = creator.avatar_url ? api.resolveAttachmentUrl(creator.avatar_url) : undefined;
    const pct = program && program.total > 0 ? Math.round((program.done / program.total) * 100) : 0;

    return (
        <View style={s.root}>
            {previewLocked ? (
                <TouchableOpacity
                    style={[s.previewBanner, { paddingTop: insets.top + 8 }]}
                    onPress={() => nav.goBack()}
                    activeOpacity={0.85}
                    accessibilityRole="button"
                    accessibilityLabel="Exit preview"
                >
                    <Ionicons name="eye-outline" size={14} color="#FFFFFF" />
                    <Text style={s.previewBannerText}>Previewing what non-subscribers see — tap to exit</Text>
                </TouchableOpacity>
            ) : null}
            {/* Banner — creator art with a soft fade, or an accent-tinted field. */}
            <View style={[s.banner, { backgroundColor: hexA(accent, 0.14) }]}>
                {art ? (
                    <>
                        <ExpoImage source={{ uri: art }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
                        <LinearGradient
                            colors={['rgba(241,241,239,0)', BG]}
                            locations={[0.45, 1]}
                            style={StyleSheet.absoluteFill}
                            pointerEvents="none"
                        />
                    </>
                ) : null}
                <TouchableOpacity
                    onPress={() => nav.goBack()}
                    hitSlop={12}
                    style={[s.back, { position: 'absolute', top: insets.top + 6, left: 14 }]}
                    accessibilityLabel="Back"
                >
                    <Ionicons name="chevron-back" size={22} color={INK} />
                </TouchableOpacity>
            </View>

            {/* Identity — avatar overlaps the banner. */}
            <View style={s.identity}>
                <View style={[s.avatarRing, { borderColor: accent }]}>
                    {avatar ? (
                        <ExpoImage source={{ uri: avatar }} style={s.avatar} contentFit="cover" transition={150} />
                    ) : (
                        <View style={[s.avatar, { backgroundColor: hexA(accent, 0.16), alignItems: 'center', justifyContent: 'center' }]}>
                            <Ionicons name={(creator.icon || 'star') as any} size={22} color={accent} />
                        </View>
                    )}
                </View>
                <View style={{ flex: 1 }}>
                    <View style={s.nameRow}>
                        <Text style={s.name} numberOfLines={1}>{creator.display_name}</Text>
                        {creator.verified ? <Ionicons name="checkmark-circle" size={16} color={accent} /> : null}
                    </View>
                    {members >= 10 ? <Text style={s.meta}>{members} members</Text> : null}
                </View>
                {creator.is_owner && !previewLocked ? (
                    <TouchableOpacity
                        style={s.ghostPill}
                        onPress={() => nav.navigate('CreatorStudio')}
                        activeOpacity={0.85}
                        accessibilityRole="button"
                        accessibilityLabel="Open Studio"
                    >
                        <Text style={s.ghostPillText}>Open Studio</Text>
                    </TouchableOpacity>
                ) : null}
            </View>

            {locked ? (
                /* Non-subscriber landed here — one clear path in. */
                <View style={s.lockWrap}>
                    <View style={s.lockCard}>
                        <View style={[s.lockDisc, { backgroundColor: hexA(accent, 0.14) }]}>
                            <Ionicons name="lock-closed" size={20} color={accent} />
                        </View>
                        <Text style={s.lockTitle}>Members only</Text>
                        <Text style={s.lockSub}>
                            Subscribe to unlock {creator.display_name}'s updates, course and daily program.
                        </Text>
                        <TouchableOpacity
                            style={[s.lockBtn, { backgroundColor: accent }]}
                            onPress={() => nav.navigate('CreatorPaywall', { maxxId })}
                            activeOpacity={0.9}
                            accessibilityRole="button"
                            accessibilityLabel="Subscribe"
                        >
                            <Text style={s.lockBtnText}>
                                Subscribe{creator.price_cents ? ` · $${((creator.price_cents || 0) / 100).toFixed(2)}/mo` : ''}
                            </Text>
                        </TouchableOpacity>
                    </View>
                </View>
            ) : (
                <>
                    {/* PROGRAM STRIP — today's progress, or the schedule bootstrap. */}
                    <View style={s.stripWrap}>
                        {program ? (
                            <TouchableOpacity
                                style={s.strip}
                                onPress={() => nav.navigate('MaxxDetail', { maxxId })}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityLabel={`Today, ${program.done} of ${program.total} done`}
                            >
                                <View style={{ flex: 1 }}>
                                    <Text style={s.stripTitle}>
                                        Today · {program.done} of {program.total} done
                                    </Text>
                                    <View style={s.stripTrack}>
                                        <View style={[s.stripFill, { backgroundColor: accent, width: `${pct}%` as any }]} />
                                    </View>
                                </View>
                                <Ionicons name="chevron-forward" size={16} color={MUTE} />
                            </TouchableOpacity>
                        ) : (
                            <TouchableOpacity
                                style={s.strip}
                                onPress={() => { void bootstrap(); }}
                                disabled={bootstrapping}
                                activeOpacity={0.85}
                                accessibilityRole="button"
                                accessibilityLabel="Add to your day"
                            >
                                <View style={[s.stripDisc, { backgroundColor: hexA(accent, 0.14) }]}>
                                    <Ionicons name="add" size={16} color={accent} />
                                </View>
                                <Text style={s.stripTitle}>{bootstrapping ? 'Adding to your day…' : 'Add to your day'}</Text>
                                <View style={{ flex: 1 }} />
                                {bootstrapping
                                    ? <ActivityIndicator size="small" color={INK} />
                                    : <Ionicons name="chevron-forward" size={16} color={MUTE} />}
                            </TouchableOpacity>
                        )}
                    </View>

                    {/* Pill tabs — Updates | Course | Community. */}
                    <View style={s.tabs}>
                        {TABS.map(({ key, label }) => {
                            const on = tab === key;
                            return (
                                <TouchableOpacity
                                    key={key}
                                    style={[s.tab, on && s.tabOn]}
                                    onPress={() => setTab(key)}
                                    activeOpacity={0.8}
                                    accessibilityRole="tab"
                                    accessibilityState={{ selected: on }}
                                >
                                    <Text style={[s.tabLabel, on && s.tabLabelOn]}>{label}</Text>
                                </TouchableOpacity>
                            );
                        })}
                    </View>

                    {/* Tab content — embedded lists own their scrolling. */}
                    <View style={{ flex: 1 }}>
                        {tab === 'updates' ? (
                            <CreatorFeedList maxxId={maxxId} embedded />
                        ) : tab === 'course' ? (
                            <CreatorCourseList maxxId={maxxId} embedded />
                        ) : (
                            <ChannelList maxxId={maxxId} accent={accent} />
                        )}
                    </View>
                </>
            )}
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    center: { alignItems: 'center', justifyContent: 'center' },

    back: {
        width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center',
        backgroundColor: 'rgba(255,255,255,0.86)',
    },

    errorText: { fontFamily: fonts.sans, fontSize: 14, color: MUTE, textAlign: 'center', lineHeight: 20 },
    retryBtn: {
        marginTop: 16, paddingHorizontal: 22, height: 42, borderRadius: 999,
        backgroundColor: CARD, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.12)',
        alignItems: 'center', justifyContent: 'center',
    },
    retryText: { fontFamily: fonts.sansSemiBold, fontSize: 14, color: INK },

    previewBanner: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7,
        backgroundColor: INK, paddingBottom: 9, paddingHorizontal: 16,
    },
    previewBannerText: { fontFamily: fonts.sansSemiBold, fontSize: 12, color: '#FFFFFF' },

    banner: { height: 120, overflow: 'hidden' },

    identity: {
        flexDirection: 'row', alignItems: 'center', gap: 12,
        paddingHorizontal: 18, marginTop: -28,
    },
    avatarRing: {
        width: 56, height: 56, borderRadius: 28, borderWidth: 2, padding: 2,
        backgroundColor: BG,
    },
    avatar: { width: '100%', height: '100%', borderRadius: 24, overflow: 'hidden' },
    nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 22 },
    name: { fontFamily: fonts.serif, fontSize: 24, color: INK, letterSpacing: -0.3, flexShrink: 1 },
    meta: { fontFamily: fonts.sansMedium, fontSize: 12.5, color: MUTE, marginTop: 3 },
    ghostPill: {
        marginTop: 22, paddingHorizontal: 14, height: 34, borderRadius: 999,
        backgroundColor: CARD, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.12)',
        alignItems: 'center', justifyContent: 'center',
    },
    ghostPillText: { fontFamily: fonts.sansSemiBold, fontSize: 12.5, color: INK },

    // Program strip
    stripWrap: { paddingHorizontal: 18, marginTop: 14 },
    strip: {
        flexDirection: 'row', alignItems: 'center', gap: 12,
        backgroundColor: CARD, borderRadius: 16, borderCurve: 'continuous', padding: 14,
        borderWidth: StyleSheet.hairlineWidth, borderColor: HAIR,
    },
    stripDisc: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
    stripTitle: { fontFamily: fonts.sansSemiBold, fontSize: 14, color: INK },
    stripTrack: {
        height: 4, borderRadius: 2, backgroundColor: 'rgba(0,0,0,0.07)',
        marginTop: 9, overflow: 'hidden',
    },
    stripFill: { height: '100%', borderRadius: 2 },

    // Pill tabs (Explore-tab styling)
    tabs: { flexDirection: 'row', gap: 8, paddingHorizontal: 18, marginTop: 16, marginBottom: 6 },
    tab: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 999, backgroundColor: 'transparent' },
    tabOn: { backgroundColor: INK },
    tabLabel: { fontFamily: fonts.sansMedium, fontSize: 14.5, color: MUTE, letterSpacing: 0.2 },
    tabLabelOn: { fontFamily: fonts.sansSemiBold, color: '#FFFFFF' },

    // Lock card (non-subscribers)
    lockWrap: { paddingHorizontal: 18, marginTop: 18 },
    lockCard: {
        alignItems: 'center', gap: 10, paddingVertical: 28, paddingHorizontal: 24,
        backgroundColor: CARD, borderRadius: 18, borderCurve: 'continuous',
        borderWidth: StyleSheet.hairlineWidth, borderColor: HAIR,
    },
    lockDisc: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
    lockTitle: { fontFamily: fonts.serif, fontSize: 20, color: INK, letterSpacing: -0.3 },
    lockSub: { fontFamily: fonts.sans, fontSize: 13.5, color: MUTE, textAlign: 'center', lineHeight: 20 },
    lockBtn: {
        marginTop: 8, paddingHorizontal: 24, height: 46, borderRadius: 999,
        alignItems: 'center', justifyContent: 'center',
    },
    lockBtnText: { fontFamily: fonts.sansSemiBold, fontSize: 14.5, color: '#FFFFFF' },
});
