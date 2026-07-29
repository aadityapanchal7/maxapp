/**
 * StudioHomeScreen — the creator's dashboard. Subscriber count + estimated
 * monthly earnings + engagement, a server-computed go-live checklist, a
 * 30-day new-subscriber sparkline, a prominent "New update" CTA, quick links
 * to the course editor + settings, and the recent-posts list (tap → manage
 * comments). This is the creator tab's landing screen.
 */
import React, { useCallback, useState } from 'react';
import {
    ActivityIndicator, Alert, RefreshControl, ScrollView, StyleSheet, Text,
    TouchableOpacity, View,
} from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Polyline } from 'react-native-svg';
import api from '../../services/api';
import { fonts } from '../../theme/dark';

const INK = '#111113';
const MUTE = '#6B6B6B';
const BG = '#F1F1EF';
const GOLD = '#B8860B';

function money(cents: number): string {
    return `$${(Math.round(cents) / 100).toFixed(2)}`;
}

const SPARK_H = 36;

function sparkGeometry(data: { count?: number }[], w: number) {
    const PADX = 4;
    const PADY = 4;
    const usable = Math.max(w - PADX * 2, 1);
    const max = Math.max(...data.map((d) => d.count || 0), 1);
    const step = data.length > 1 ? usable / (data.length - 1) : 0;
    const coords = data.map((d, i) => ({
        x: PADX + i * step,
        y: SPARK_H - PADY - ((d.count || 0) / max) * (SPARK_H - PADY * 2),
    }));
    return {
        points: coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' '),
        last: coords[coords.length - 1],
    };
}

type ChecklistItem = { key: string; label: string; done: boolean; required: boolean };
type Checklist = {
    items: ChecklistItem[]; can_go_live: boolean;
    done_count: number; total_count: number; is_live: boolean;
};

export default function StudioHomeScreen() {
    const nav = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const [creator, setCreator] = useState<any>(null);
    const [stats, setStats] = useState<any>(null);
    const [posts, setPosts] = useState<any[]>([]);
    const [checklist, setChecklist] = useState<Checklist | null>(null);
    const [habitsCount, setHabitsCount] = useState<number | null>(null);
    const [channelsCount, setChannelsCount] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [sparkW, setSparkW] = useState(0);

    const load = useCallback(async () => {
        try {
            const [c, st, pr, cl, hb, ch] = await Promise.all([
                api.getMyCreator(),
                api.getMyCreatorStats(),
                api.getMyCreatorPosts(),
                api.getCreatorChecklist().catch(() => null),
                api.getMyCreatorHabits().catch(() => null),
                api.getMyCreatorChannels().catch(() => null),
            ]);
            setCreator(c); setStats(st); setPosts(pr.posts || []); setChecklist(cl);
            setHabitsCount(hb ? (hb.habits || []).length : null);
            setChannelsCount(ch ? (ch.channels || []).length : null);
        } catch { /* keep */ }
        finally { setLoading(false); setRefreshing(false); }
    }, []);

    useFocusEffect(useCallback(() => { void load(); }, [load]));

    useFocusEffect(useCallback(() => {
        if (creator && creator.status === 'onboarding' && !creator.onboarding_complete) {
            nav.replace('CreatorOnboarding');
        }
    }, [creator, nav]));

    const accent = creator?.accent_color || GOLD;

    if (loading) {
        return <View style={[s.root, s.center]}><ActivityIndicator color={INK} /></View>;
    }

    const statusBanner = creator && creator.status !== 'live' ? (
        <View style={s.banner}>
            <Ionicons name="information-circle-outline" size={16} color={GOLD} />
            <Text style={s.bannerText}>
                {creator.status === 'onboarding'
                    ? 'Post your first update, then go live from Settings.'
                    : creator.apple_review_status === 'pending'
                        ? 'Your subscription is in Apple review.'
                        : 'Your max is paused.'}
            </Text>
        </View>
    ) : null;

    const onChecklistTap = (key: string) => {
        if (key === 'profile' || key === 'avatar') nav.navigate('CreatorSettings');
        else if (key === 'lesson') nav.navigate('CreatorCourseEditor');
        else if (key === 'habits') nav.navigate('CreatorHabitsEditor');
        else if (key === 'post') nav.navigate('CreatorComposer');
        else if (key === 'apple') Alert.alert('Apple review', 'Your subscription product is reviewed by Apple before it can be sold.');
    };

    const showChecklist = !!checklist && !(checklist.is_live && checklist.done_count === checklist.total_count);

    const sparkData: { date?: string; count?: number }[] | null =
        Array.isArray(stats?.subscribers_30d) && stats.subscribers_30d.some((d: any) => (d?.count || 0) > 0)
            ? stats.subscribers_30d
            : null;

    return (
        <View style={[s.root, { paddingTop: insets.top + 10 }]}>
            <ScrollView
                contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: insets.bottom + 40 }}
                showsVerticalScrollIndicator={false}
                refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={INK} />}
            >
                <Text style={s.kicker}>CREATOR STUDIO</Text>
                <Text style={s.title}>{creator?.display_name || 'Your studio'}</Text>

                {statusBanner}

                {/* Go-live checklist */}
                {showChecklist && checklist ? (
                    <View style={s.checkCard}>
                        <View style={s.checkHeader}>
                            <Text style={s.checkTitle}>Go-live checklist</Text>
                            <Text style={s.checkCount}>{checklist.done_count}/{checklist.total_count}</Text>
                        </View>
                        {checklist.items.map((it) => (
                            <TouchableOpacity key={it.key} style={s.checkRow} onPress={() => onChecklistTap(it.key)} activeOpacity={0.7}>
                                <Ionicons
                                    name={it.done ? 'checkmark-circle' : 'ellipse-outline'}
                                    size={18}
                                    color={it.done ? '#2F9E60' : MUTE}
                                />
                                <Text style={[s.checkLabel, it.done && s.checkLabelDone]} numberOfLines={1}>{it.label}</Text>
                                <Ionicons name="chevron-forward" size={14} color={MUTE} />
                            </TouchableOpacity>
                        ))}
                        {checklist.can_go_live && !checklist.is_live ? (
                            <TouchableOpacity style={s.checkReady} onPress={() => nav.navigate('CreatorSettings')} activeOpacity={0.8}>
                                <Text style={s.checkReadyText}>Ready — go live in Settings</Text>
                                <Ionicons name="arrow-forward" size={15} color={GOLD} />
                            </TouchableOpacity>
                        ) : null}
                    </View>
                ) : null}

                {/* Stats */}
                <View style={s.statsRow}>
                    <View style={s.statCell}>
                        <Text style={s.statValue}>{stats?.subscriber_count ?? 0}</Text>
                        <Text style={s.statLabel}>SUBSCRIBERS</Text>
                    </View>
                    <View style={s.statDivider} />
                    <View style={s.statCell}>
                        <Text style={s.statValue}>{money(stats?.est_monthly_cents ?? 0)}</Text>
                        <Text style={s.statLabel}>EST. / MONTH</Text>
                    </View>
                    <View style={s.statDivider} />
                    <View style={s.statCell}>
                        <Text style={s.statValue}>{stats?.total_likes ?? 0}</Text>
                        <Text style={s.statLabel}>LIKES</Text>
                    </View>
                </View>

                {/* New-subscriber sparkline (30d) */}
                {sparkData ? (
                    <View style={s.sparkCard}>
                        <Text style={s.sparkLabel}>NEW SUBSCRIBERS · 30D</Text>
                        <View style={{ height: SPARK_H }} onLayout={(e) => setSparkW(e.nativeEvent.layout.width)}>
                            {sparkW > 0 ? (() => {
                                const g = sparkGeometry(sparkData, sparkW);
                                return (
                                    <Svg width={sparkW} height={SPARK_H}>
                                        <Polyline points={g.points} fill="none" stroke={INK} strokeWidth={1.5} />
                                        <Circle cx={g.last.x} cy={g.last.y} r={3} fill={GOLD} />
                                    </Svg>
                                );
                            })() : null}
                        </View>
                    </View>
                ) : null}

                {/* New update CTA */}
                <TouchableOpacity style={[s.newBtn, { backgroundColor: INK }]} onPress={() => nav.navigate('CreatorComposer')} activeOpacity={0.9}>
                    <Ionicons name="add" size={22} color="#FFFFFF" />
                    <Text style={s.newBtnText}>New update</Text>
                </TouchableOpacity>

                {/* Quick links — 2×2 grid: Course / Habits / Channels / Settings. */}
                <View style={s.linkGrid}>
                    <TouchableOpacity style={s.gridCard} onPress={() => nav.navigate('CreatorCourseEditor')} activeOpacity={0.85}>
                        <Ionicons name="book-outline" size={20} color={accent} />
                        <Text style={s.linkText}>Course</Text>
                        <Text style={s.linkCount}>{`${stats?.published_lessons ?? 0} live · ${stats?.draft_lessons ?? 0} draft`}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={s.gridCard} onPress={() => nav.navigate('CreatorHabitsEditor')} activeOpacity={0.85}>
                        <Ionicons name="repeat-outline" size={20} color={accent} />
                        <Text style={s.linkText}>Habits</Text>
                        {habitsCount != null ? <Text style={s.linkCount}>{`${habitsCount} habit${habitsCount === 1 ? '' : 's'}`}</Text> : null}
                    </TouchableOpacity>
                    <TouchableOpacity style={s.gridCard} onPress={() => nav.navigate('CreatorChannelsManager')} activeOpacity={0.85}>
                        <Ionicons name="chatbubbles-outline" size={20} color={accent} />
                        <Text style={s.linkText}>Channels</Text>
                        {channelsCount != null ? <Text style={s.linkCount}>{`${channelsCount} channel${channelsCount === 1 ? '' : 's'}`}</Text> : null}
                    </TouchableOpacity>
                    <TouchableOpacity style={s.gridCard} onPress={() => nav.navigate('CreatorSettings')} activeOpacity={0.85}>
                        <Ionicons name="settings-outline" size={20} color={accent} />
                        <Text style={s.linkText}>Settings</Text>
                    </TouchableOpacity>
                </View>

                {/* Preview — the member view of this maxx (Updates | Course | Community).
                    Two entry points: the locked view real non-subscribers see, and the
                    normal owner view (always unlocked). */}
                <TouchableOpacity
                    style={[s.previewRow, !creator?.maxx_id && { opacity: 0.4 }]}
                    disabled={!creator?.maxx_id}
                    onPress={() => creator?.maxx_id && nav.navigate('CreatorMaxxHome', { maxxId: creator.maxx_id, previewLocked: true })}
                    activeOpacity={0.85}
                >
                    <Ionicons name="lock-closed-outline" size={18} color={accent} />
                    <Text style={s.previewText}>Preview as member (locked)</Text>
                    <View style={{ flex: 1 }} />
                    <Ionicons name="chevron-forward" size={15} color={MUTE} />
                </TouchableOpacity>
                <TouchableOpacity
                    style={[s.previewRowSecondary, !creator?.maxx_id && { opacity: 0.4 }]}
                    disabled={!creator?.maxx_id}
                    onPress={() => creator?.maxx_id && nav.navigate('CreatorMaxxHome', { maxxId: creator.maxx_id })}
                    activeOpacity={0.85}
                >
                    <Ionicons name="eye-outline" size={15} color={MUTE} />
                    <Text style={s.previewSecondaryText}>View my page</Text>
                </TouchableOpacity>

                {/* Recent posts */}
                <Text style={s.section}>Recent updates</Text>
                {posts.length === 0 ? (
                    <Text style={s.empty}>No updates yet. Post your first one.</Text>
                ) : posts.map((p) => (
                    <TouchableOpacity key={p.id} style={s.postRow} onPress={() => nav.navigate('CreatorPostComments', { postId: p.id })} activeOpacity={0.7}>
                        <View style={[s.postIcon, { backgroundColor: '#F1F1EF' }]}>
                            <Ionicons name={p.type === 'video' ? 'videocam' : 'text'} size={16} color={INK} />
                        </View>
                        <View style={{ flex: 1 }}>
                            <Text style={s.postBody} numberOfLines={1}>{p.body || (p.type === 'video' ? 'Video update' : 'Update')}</Text>
                            <Text style={s.postMeta}>{p.like_count || 0} likes · {p.comment_count || 0} comments{p.pinned ? ' · pinned' : ''}</Text>
                        </View>
                        <Ionicons name="chevron-forward" size={16} color={MUTE} />
                    </TouchableOpacity>
                ))}
            </ScrollView>
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    center: { alignItems: 'center', justifyContent: 'center' },
    kicker: { fontFamily: fonts.sansSemiBold, fontSize: 11, letterSpacing: 1.5, color: GOLD },
    title: { fontFamily: fonts.serif, fontSize: 30, color: INK, marginTop: 6 },
    banner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#FBF3E2', borderRadius: 12, padding: 12, marginTop: 16 },
    bannerText: { flex: 1, fontFamily: fonts.sansMedium, fontSize: 13, color: '#7A5B12' },
    checkCard: { backgroundColor: '#FFFFFF', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 6, marginTop: 16, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.06)' },
    checkHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10 },
    checkTitle: { fontFamily: fonts.sansSemiBold, fontSize: 14, color: INK },
    checkCount: { fontFamily: fonts.sansSemiBold, fontSize: 12.5, color: MUTE },
    checkRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: 'rgba(0,0,0,0.06)' },
    checkLabel: { flex: 1, fontFamily: fonts.sansMedium, fontSize: 13.5, color: INK },
    checkLabelDone: { color: MUTE },
    checkReady: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingVertical: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: 'rgba(0,0,0,0.06)' },
    checkReadyText: { fontFamily: fonts.sansSemiBold, fontSize: 13.5, color: GOLD },
    statsRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderRadius: 18, paddingVertical: 18, marginTop: 18, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.06)' },
    statCell: { flex: 1, alignItems: 'center' },
    statDivider: { width: StyleSheet.hairlineWidth, height: 34, backgroundColor: 'rgba(0,0,0,0.08)' },
    statValue: { fontFamily: fonts.sansBold, fontSize: 22, color: INK },
    statLabel: { fontFamily: fonts.sansSemiBold, fontSize: 9.5, letterSpacing: 0.8, color: MUTE, marginTop: 5 },
    sparkCard: { backgroundColor: '#FFFFFF', borderRadius: 18, paddingHorizontal: 16, paddingVertical: 14, marginTop: 10, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.06)' },
    sparkLabel: { fontFamily: fonts.sansSemiBold, fontSize: 9.5, letterSpacing: 0.8, color: MUTE, marginBottom: 10 },
    newBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 54, borderRadius: 27, marginTop: 18 },
    newBtnText: { fontFamily: fonts.sansSemiBold, fontSize: 16.5, color: '#FFFFFF' },
    linkGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 },
    gridCard: { flexBasis: '47%', flexGrow: 1, backgroundColor: '#FFFFFF', borderRadius: 16, alignItems: 'center', paddingVertical: 16, gap: 7, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.06)' },
    linkText: { fontFamily: fonts.sansMedium, fontSize: 13, color: INK },
    linkCount: { fontFamily: fonts.sans, fontSize: 10, color: MUTE, marginTop: -3 },
    previewRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF', borderRadius: 14, paddingHorizontal: 14, paddingVertical: 13, marginTop: 10, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.06)' },
    previewText: { fontFamily: fonts.sansMedium, fontSize: 13.5, color: INK },
    previewRowSecondary: { flexDirection: 'row', alignItems: 'center', gap: 8, justifyContent: 'center', paddingVertical: 10, marginTop: 4 },
    previewSecondaryText: { fontFamily: fonts.sansMedium, fontSize: 12.5, color: MUTE },
    section: { fontFamily: fonts.sansSemiBold, fontSize: 13, color: INK, marginTop: 26, marginBottom: 10, letterSpacing: 0.2 },
    empty: { fontFamily: fonts.sans, fontSize: 14, color: MUTE, marginTop: 4 },
    postRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#FFFFFF', borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.05)' },
    postIcon: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
    postBody: { fontFamily: fonts.sansMedium, fontSize: 14.5, color: INK },
    postMeta: { fontFamily: fonts.sans, fontSize: 12, color: MUTE, marginTop: 3 },
});
