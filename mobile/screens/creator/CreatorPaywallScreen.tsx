/**
 * CreatorPaywallScreen — subscribe to one creator (monthly, on top of Chad).
 * Real purchase uses Apple IAP against the creator's own SKU (each creator has
 * its own subscription group). In dev builds a "Start subscription" tap
 * dev-activates so the full loop is testable on the simulator without Apple.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
    ActivityIndicator, Alert, Linking, Platform, ScrollView, StyleSheet, Text,
    TouchableOpacity, View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Image as ExpoImage } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useCreatorPurchase } from '../../hooks/useCreatorPurchase';
import { queryClient, queryKeys } from '../../lib/queryClient';
import { fonts } from '../../theme/dark';
import { hexA } from '../../utils/scheduleAggregation';

const INK = '#111113';
const MUTE = '#6B6B6B';
const BG = '#F1F1EF';
const SHOW_DEV = __DEV__;

const BENEFITS = [
    { icon: 'videocam-outline', text: 'Video & text updates, direct from the creator' },
    { icon: 'book-outline', text: 'Their full course, kept up to date' },
    { icon: 'chatbubbles-outline', text: 'Comment and get replies' },
    { icon: 'notifications-outline', text: 'Get pinged the moment they post' },
];

export default function CreatorPaywallScreen() {
    const nav = useNavigation<any>();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const { user, isPaid, refreshUser } = useAuth();
    const { purchaseCreatorSubscription } = useCreatorPurchase();
    const maxxId: string = route.params?.maxxId;

    const [creator, setCreator] = useState<any>(null);
    const [course, setCourse] = useState<any>(null);
    const [busy, setBusy] = useState(false);
    const [restoring, setRestoring] = useState(false);

    const load = useCallback(async () => {
        try { setCreator(await api.getCreatorByMaxx(maxxId)); } catch { /* ignore */ }
        // Course outline for "What's inside" — the locked (redacted) shape is fine.
        try { setCourse(await api.getCreatorCourse(maxxId)); } catch { /* optional */ }
    }, [maxxId]);
    useEffect(() => { void load(); }, [load]);

    const accent = creator?.accent_color || '#BC7A3C';
    const price = creator ? `$${((creator.price_cents || 0) / 100).toFixed(2)}` : '';

    // "{n} lessons · {n} updates · {n} members" — zero parts drop out; the
    // member count only shows once it's social proof (>= 10), not embarrassment.
    const metaParts: string[] = [];
    if (creator) {
        const lessons = Number(creator.published_lesson_count || 0);
        const posts = Number(creator.post_count || 0);
        const subs = Number(creator.subscriber_count || 0);
        if (lessons > 0) metaParts.push(`${lessons} lesson${lessons === 1 ? '' : 's'}`);
        if (posts > 0) metaParts.push(`${posts} update${posts === 1 ? '' : 's'}`);
        if (subs >= 10) metaParts.push(`${subs} members`);
    }

    // "What's inside" outline: up to 2 modules × up to 4 lessons each.
    const insideModules: { module_number: number; title: string; lessons: any[] }[] =
        (course?.modules || []).slice(0, 2).map((m: any) => ({ ...m, lessons: (m.lessons || []).slice(0, 4) }));
    const shownCount = insideModules.reduce((n, m) => n + m.lessons.length, 0);
    const moreCount = Math.max(0, Number(course?.lesson_count || 0) - shownCount);

    /**
     * Restore (Apple 3.1.2). Looks for THIS creator's SKU among the Apple ID's
     * purchases and re-verifies with the backend; if nothing is found (or
     * off-iOS/dev), falls through to Apple's own subscription manager. Kept as
     * its own one-off dynamic import of react-native-iap (rather than reusing
     * useCreatorPurchase's listeners) since restoring is a pull, not something
     * StoreKit reports back through onPurchaseSuccess/onPurchaseError.
     */
    const restore = async () => {
        if (restoring) return;
        setRestoring(true);
        try {
            if (Platform.OS === 'ios' && !SHOW_DEV && creator?.apple_product_id) {
                const iap: any = await import('react-native-iap');
                const purchases: any[] = (await iap.getAvailablePurchases()) ?? [];
                const match = purchases.find((p: any) => (p?.productId ?? p?.id) === creator.apple_product_id);
                const tid = match ? String(match.transactionId ?? match.id ?? '').trim() : '';
                if (tid) {
                    await api.verifyCreatorSubscription(maxxId, tid, creator.apple_product_id);
                    await refreshUser();
                    // Verify also creates the 14-day schedule server-side.
                    await queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull, refetchType: 'all' });
                    Alert.alert('Purchases restored', 'Your subscription to this creator is active.');
                    return;
                }
            }
            await Linking.openURL('https://apps.apple.com/account/subscriptions');
        } catch (e: any) {
            Alert.alert('Restore failed', e?.response?.data?.detail || e?.message || 'Try again.');
        } finally {
            setRestoring(false);
        }
    };

    const subscribe = async () => {
        if (busy || !creator) return;
        // Chad base sub is required underneath.
        if (!isPaid) {
            Alert.alert('Chad required', 'Creator subscriptions are an add-on to Chad. Start Chad first.', [
                { text: 'Not now', style: 'cancel' },
                { text: 'Get Chad', onPress: () => nav.navigate('Payment') },
            ]);
            return;
        }
        setBusy(true);
        try {
            let res: any;
            if (SHOW_DEV) {
                res = await api.devActivateCreatorSubscription(maxxId);
            } else {
                // Production: run the real IAP purchase against creator.apple_product_id;
                // useCreatorPurchase verifies with the backend internally once
                // StoreKit reports the REAL outcome (never the requestPurchase()
                // return value — v14 resolves that before the user has paid).
                // The per-creator SKU must exist in App Store Connect.
                res = await purchaseCreatorSubscription(maxxId, creator.apple_product_id, user?.id ?? '');
            }
            await refreshUser();
            // dev-activate / IAP verify create the schedule server-side too —
            // refetch active schedules AND the by-maxx profile (its `subscribed`
            // drives the member home's lock card) so landing there is unlocked.
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: queryKeys.schedulesActiveFull, refetchType: 'all' }),
                queryClient.invalidateQueries({ queryKey: ['creator', 'by-maxx', maxxId], refetchType: 'all' }),
            ]);
            nav.replace('CreatorMaxxHome', { maxxId });
            // Billed-but-blocked MUST be surfaced: at the 5-program cap the sub
            // is active but the habits can't land until a slot frees up. The
            // member home's "Add to your day" pill retries once one does.
            if (res?.schedule_blocked === 'active_limit') {
                Alert.alert(
                    'Your schedule is full',
                    "You're subscribed, but you already have 5 active programs. Pause or cancel one, then tap “Add to your day” on this max.",
                );
            }
        } catch (e: any) {
            Alert.alert('Could not subscribe', e?.response?.data?.detail || e?.message || 'Try again.');
        } finally {
            setBusy(false);
        }
    };

    return (
        <View style={[s.root, { paddingTop: insets.top + 6 }]}>
            <TouchableOpacity onPress={() => nav.goBack()} hitSlop={12} style={s.close} accessibilityLabel="Close">
                <Ionicons name="close" size={22} color={INK} />
            </TouchableOpacity>
            <ScrollView contentContainerStyle={{ paddingHorizontal: 24, paddingBottom: insets.bottom + 30, alignItems: 'center' }} showsVerticalScrollIndicator={false}>
                <View style={{ height: 20 }} />
                <View style={[s.avatarRing, { borderColor: accent }]}>
                    {creator?.avatar_url ? (
                        <ExpoImage source={{ uri: api.resolveAttachmentUrl(creator.avatar_url) }} style={s.avatar} contentFit="cover" />
                    ) : (
                        <View style={[s.avatar, { backgroundColor: hexA(accent, 0.16), alignItems: 'center', justifyContent: 'center' }]}>
                            <Ionicons name={creator?.icon || 'star'} size={30} color={accent} />
                        </View>
                    )}
                </View>
                <Text style={s.title}>{creator?.display_name || 'Creator'}</Text>
                {creator?.tagline ? <Text style={s.tagline}>{creator.tagline}</Text> : null}
                {metaParts.length > 0 ? <Text style={s.metaLine}>{metaParts.join(' · ')}</Text> : null}

                <View style={s.benefits}>
                    {BENEFITS.map((b) => (
                        <View key={b.text} style={s.benefitRow}>
                            <View style={[s.benefitIcon, { backgroundColor: hexA(accent, 0.14) }]}>
                                <Ionicons name={b.icon as any} size={17} color={accent} />
                            </View>
                            <Text style={s.benefitText}>{b.text}</Text>
                        </View>
                    ))}
                </View>

                {shownCount > 0 ? (
                    <View style={s.insideWrap}>
                        <Text style={s.insideKicker}>WHAT&apos;S INSIDE</Text>
                        <View style={s.insideCard}>
                            {insideModules.map((m, mi) => (
                                <View key={m.module_number}>
                                    {mi > 0 ? <View style={s.insideSep} /> : null}
                                    {m.lessons.map((l: any) => (
                                        <View key={l.id} style={s.insideRow}>
                                            <View style={[s.insideDisc, { backgroundColor: hexA(accent, 0.14) }]}>
                                                <Ionicons name={(l.icon || 'document-text-outline') as any} size={14} color={accent} />
                                            </View>
                                            <Text style={s.insideTitle} numberOfLines={1}>{l.title}</Text>
                                            {l.is_free_preview ? (
                                                <View style={s.freeChip}><Text style={s.freeChipText}>FREE</Text></View>
                                            ) : (
                                                <Ionicons name="lock-closed" size={14} color={MUTE} />
                                            )}
                                        </View>
                                    ))}
                                </View>
                            ))}
                            {moreCount > 0 ? <Text style={s.insideMore}>+{moreCount} more lessons</Text> : null}
                            {Number(course?.free_preview_count || 0) > 0 ? (
                                <TouchableOpacity
                                    style={s.tryRow}
                                    onPress={() => nav.navigate('CreatorCourse', { maxxId })}
                                    activeOpacity={0.8}
                                    accessibilityRole="button"
                                    accessibilityLabel="Try a free lesson"
                                >
                                    <Text style={[s.tryText, { color: accent }]}>Try a free lesson</Text>
                                    <Ionicons name="arrow-forward" size={15} color={accent} />
                                </TouchableOpacity>
                            ) : null}
                        </View>
                    </View>
                ) : null}

                <View style={s.priceCard}>
                    <Text style={s.priceValue}>{price}<Text style={s.pricePer}>/month</Text></Text>
                    <Text style={s.priceNote}>Cancel anytime · billed on top of Chad</Text>
                </View>

                <TouchableOpacity style={[s.cta, { backgroundColor: accent }, (busy || !creator) && { opacity: 0.5 }]} onPress={subscribe} disabled={busy || !creator} activeOpacity={0.9}>
                    {busy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={s.ctaText}>Start subscription</Text>}
                </TouchableOpacity>
                {SHOW_DEV ? <Text style={s.devNote}>DEV: activates instantly (no Apple)</Text> : null}

                {/* Apple 3.1.2 — subscription terms + Terms / Privacy / Restore. */}
                {creator ? (
                    <View style={s.legalWrap}>
                        <Text style={s.legalText}>
                            {price}/month · auto-renews until canceled · cancel anytime in Settings
                        </Text>
                        <View style={s.legalLinks}>
                            <TouchableOpacity onPress={() => nav.navigate('LegalDocument', { document: 'terms' })} hitSlop={8} activeOpacity={0.7}>
                                <Text style={s.legalLink}>Terms</Text>
                            </TouchableOpacity>
                            <Text style={s.legalDot}>·</Text>
                            <TouchableOpacity onPress={() => nav.navigate('LegalDocument', { document: 'privacy' })} hitSlop={8} activeOpacity={0.7}>
                                <Text style={s.legalLink}>Privacy</Text>
                            </TouchableOpacity>
                            <Text style={s.legalDot}>·</Text>
                            <TouchableOpacity onPress={restore} disabled={restoring} hitSlop={8} activeOpacity={0.7}>
                                <Text style={s.legalLink}>{restoring ? 'Restoring…' : 'Restore'}</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                ) : null}
            </ScrollView>
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    close: { position: 'absolute', right: 20, top: 0, zIndex: 10, width: 36, height: 36, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
    avatarRing: { width: 92, height: 92, borderRadius: 46, borderWidth: 2, padding: 3 },
    avatar: { width: '100%', height: '100%', borderRadius: 40 },
    title: { fontFamily: fonts.serif, fontSize: 28, color: INK, marginTop: 14 },
    tagline: { fontFamily: fonts.sans, fontSize: 15, color: MUTE, marginTop: 8, textAlign: 'center' },
    metaLine: { fontFamily: fonts.sansMedium, fontSize: 12.5, color: MUTE, marginTop: 8, textAlign: 'center' },
    benefits: { alignSelf: 'stretch', gap: 14, marginTop: 26 },
    benefitRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
    benefitIcon: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
    benefitText: { flex: 1, fontFamily: fonts.sansMedium, fontSize: 15, color: INK },
    priceCard: { alignSelf: 'stretch', backgroundColor: '#FFFFFF', borderRadius: 18, borderCurve: 'continuous', alignItems: 'center', paddingVertical: 18, marginTop: 26, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.07)' },
    priceValue: { fontFamily: fonts.sansBold, fontSize: 30, color: INK },
    pricePer: { fontFamily: fonts.sansMedium, fontSize: 15, color: MUTE },
    priceNote: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, marginTop: 6 },
    cta: { alignSelf: 'stretch', height: 54, borderRadius: 27, alignItems: 'center', justifyContent: 'center', marginTop: 22,
        ...(Platform.OS === 'ios' ? { shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 14, shadowOffset: { width: 0, height: 6 } } : { elevation: 5 }) },
    ctaText: { fontFamily: fonts.sansSemiBold, fontSize: 16.5, color: '#FFFFFF' },
    devNote: { fontFamily: fonts.sans, fontSize: 11.5, color: MUTE, marginTop: 10 },

    // "What's inside" course outline
    insideWrap: { alignSelf: 'stretch', marginTop: 26 },
    insideKicker: { fontFamily: fonts.sansSemiBold, fontSize: 11, letterSpacing: 1.2, color: MUTE, marginBottom: 10 },
    insideCard: {
        backgroundColor: '#FFFFFF', borderRadius: 18, borderCurve: 'continuous',
        paddingHorizontal: 14, paddingVertical: 6,
        borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.07)',
    },
    insideRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9 },
    insideDisc: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
    insideTitle: { flex: 1, fontFamily: fonts.sansMedium, fontSize: 14, color: INK },
    insideSep: { height: StyleSheet.hairlineWidth, backgroundColor: 'rgba(0,0,0,0.06)', marginVertical: 4 },
    insideMore: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, paddingVertical: 9, paddingLeft: 38 },
    tryRow: {
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12,
        borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: 'rgba(0,0,0,0.06)',
    },
    tryText: { fontFamily: fonts.sansSemiBold, fontSize: 13.5 },
    freeChip: { backgroundColor: hexA('#B8860B', 0.14), borderRadius: 999, paddingHorizontal: 7, paddingVertical: 2 },
    freeChipText: { fontFamily: fonts.sansSemiBold, fontSize: 10.5, color: '#8A6D2E', letterSpacing: 0.4 },

    // Apple 3.1.2 footer
    legalWrap: { alignItems: 'center', marginTop: 18, alignSelf: 'stretch', paddingHorizontal: 8 },
    legalText: { fontFamily: fonts.sans, fontSize: 11.5, color: MUTE, textAlign: 'center', lineHeight: 17 },
    legalLinks: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
    legalLink: { fontFamily: fonts.sansMedium, fontSize: 11.5, color: MUTE, textDecorationLine: 'underline' },
    legalDot: { fontFamily: fonts.sans, fontSize: 11.5, color: MUTE },
});
