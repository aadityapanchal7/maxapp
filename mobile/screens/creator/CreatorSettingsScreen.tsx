/**
 * CreatorSettingsScreen — edit the public profile (avatar, display name,
 * tagline, bio, accent color, social handles), see the subscription price +
 * review status, and go live. Save is disabled until the profile has actually
 * loaded so a failed fetch can never PATCH empty strings over real data.
 */
import React, { useCallback, useRef, useState } from 'react';
import {
    ActivityIndicator, Alert, KeyboardAvoidingView, Platform, ScrollView,
    StyleSheet, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Image as ExpoImage } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import api from '../../services/api';
import { fonts } from '../../theme/dark';
import { hexA } from '../../utils/scheduleAggregation';

const INK = '#111113';
const MUTE = '#6B6B6B';
const BG = '#F1F1EF';
const GOLD = '#B8860B';

const ACCENTS = ['#BC7A3C', '#C29A4E', '#8E6FB8', '#4E7A8A', '#2F6B4E', '#B85C5C', '#5E7ACD', '#3D3D3D'];

/** "https://instagram.com/@foo/" → "foo" — we store bare handles. */
function cleanHandle(v: string): string {
    return v
        .trim()
        .replace(/^https?:\/\//i, '')
        .replace(/^(?:www\.)?(?:instagram\.com|tiktok\.com|youtube\.com|youtu\.be)\//i, '')
        .replace(/^@+/, '')
        .replace(/[/?#].*$/, '')
        .trim();
}

export default function CreatorSettingsScreen() {
    const nav = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const [creator, setCreator] = useState<any>(null);
    const [displayName, setDisplayName] = useState('');
    const [tagline, setTagline] = useState('');
    const [bio, setBio] = useState('');
    const [accent, setAccent] = useState('');
    const [instagram, setInstagram] = useState('');
    const [tiktok, setTiktok] = useState('');
    const [youtube, setYoutube] = useState('');
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [loaded, setLoaded] = useState(false); // only true after a successful fetch — guards Save
    const [avatarBusy, setAvatarBusy] = useState(false);

    // Dirty-check baseline — snapshot of the editable fields as last loaded/saved.
    const baselineRef = useRef<string>('');
    const snapshot = (v: {
        displayName: string; tagline: string; bio: string; accent: string;
        instagram: string; tiktok: string; youtube: string;
    }) => JSON.stringify(v);
    const isDirty = () => snapshot({ displayName, tagline, bio, accent, instagram, tiktok, youtube }) !== baselineRef.current;

    const load = useCallback(async () => {
        try {
            const c = await api.getMyCreator();
            setCreator(c);
            const next = {
                displayName: c.display_name || '',
                tagline: c.tagline || '',
                bio: c.bio || '',
                accent: c.accent_color || '',
                instagram: c.socials?.instagram || '',
                tiktok: c.socials?.tiktok || '',
                youtube: c.socials?.youtube || '',
            };
            setDisplayName(next.displayName);
            setTagline(next.tagline);
            setBio(next.bio);
            setAccent(next.accent);
            setInstagram(next.instagram);
            setTiktok(next.tiktok);
            setYoutube(next.youtube);
            baselineRef.current = JSON.stringify(next);
            setLoaded(true);
        } catch { /* keep — Save stays disabled until a load succeeds */ }
        finally { setLoading(false); }
    }, []);
    useFocusEffect(useCallback(() => { void load(); }, [load]));

    const save = async () => {
        if (!loaded) return; // never PATCH blanks over real data
        setSaving(true);
        try {
            const socials = {
                instagram: cleanHandle(instagram),
                tiktok: cleanHandle(tiktok),
                youtube: cleanHandle(youtube),
            };
            const patch: Record<string, unknown> = { display_name: displayName, tagline, bio, socials };
            if (accent) patch.accent_color = accent;
            const c = await api.updateMyCreator(patch);
            setCreator(c);
            setInstagram(socials.instagram);
            setTiktok(socials.tiktok);
            setYoutube(socials.youtube);
            baselineRef.current = snapshot({
                displayName, tagline, bio, accent,
                instagram: socials.instagram, tiktok: socials.tiktok, youtube: socials.youtube,
            });
            Alert.alert('Saved');
        } catch (e: any) {
            Alert.alert('Could not save', e?.response?.data?.detail || 'Try again.');
        } finally { setSaving(false); }
    };

    const changePhoto = async () => {
        try {
            const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
            if (!perm.granted) {
                Alert.alert('Permission needed', 'Enable photo access to choose a picture.');
                return;
            }
            const res = await ImagePicker.launchImageLibraryAsync({
                mediaTypes: ImagePicker.MediaTypeOptions.Images,
                allowsEditing: true,
                aspect: [1, 1],
                quality: 0.8,
            });
            if (res.canceled || !res.assets?.[0]) return;
            setAvatarBusy(true);
            const updated = await api.uploadCreatorAvatar(res.assets[0].uri);
            setCreator(updated);
        } catch (e: any) {
            Alert.alert('Could not upload', e?.response?.data?.detail || 'Try again.');
        } finally { setAvatarBusy(false); }
    };

    const requestGoBack = () => {
        if (isDirty()) {
            Alert.alert('Discard changes?', undefined, [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Discard', style: 'destructive', onPress: () => nav.goBack() },
            ]);
        } else {
            nav.goBack();
        }
    };

    const goLive = async () => {
        try {
            const c = await api.updateMyCreator({ go_live: true });
            setCreator(c);
            Alert.alert('You’re live', 'Your max is now listed.');
        } catch (e: any) {
            Alert.alert('Not yet', e?.response?.data?.detail || 'Try again.');
        }
    };

    if (loading) return <View style={[s.root, { alignItems: 'center', justifyContent: 'center' }]}><ActivityIndicator color={INK} /></View>;

    const avatarAccent = accent || GOLD;

    return (
        <View style={[s.root, { paddingTop: insets.top }]}>
            <View style={s.topBar}>
                <TouchableOpacity onPress={requestGoBack} hitSlop={12} style={s.back} accessibilityLabel="Back">
                    <Ionicons name="chevron-back" size={24} color={INK} />
                </TouchableOpacity>
                <Text style={s.topTitle}>Settings</Text>
                <TouchableOpacity onPress={save} hitSlop={12} disabled={saving || !loaded} accessibilityLabel="Save">
                    {saving
                        ? <ActivityIndicator size="small" color={INK} />
                        : <Text style={[s.saveBtn, !loaded && s.saveBtnDisabled]}>Save</Text>}
                </TouchableOpacity>
            </View>

            <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
                <ScrollView contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                    {/* Avatar */}
                    <View style={s.avatarWrap}>
                        <View style={s.avatarCircle}>
                            {creator?.avatar_url ? (
                                <ExpoImage source={{ uri: api.resolveAttachmentUrl(creator.avatar_url) }} style={s.avatarImg} contentFit="cover" />
                            ) : (
                                <View style={[s.avatarImg, { backgroundColor: hexA(avatarAccent, 0.16), alignItems: 'center', justifyContent: 'center' }]}>
                                    <Ionicons name={creator?.icon || 'person-outline'} size={30} color={avatarAccent} />
                                </View>
                            )}
                            {avatarBusy ? (
                                <View style={s.avatarBusy}><ActivityIndicator size="small" color="#FFFFFF" /></View>
                            ) : null}
                        </View>
                        <TouchableOpacity onPress={changePhoto} disabled={avatarBusy || !loaded} hitSlop={8}>
                            <Text style={[s.changePhoto, (avatarBusy || !loaded) && { opacity: 0.4 }]}>Change photo</Text>
                        </TouchableOpacity>
                    </View>

                    <Text style={s.label}>DISPLAY NAME</Text>
                    <TextInput style={s.input} value={displayName} onChangeText={setDisplayName} maxLength={60} placeholder="Your name" placeholderTextColor={MUTE} />
                    <Text style={s.label}>TAGLINE</Text>
                    <TextInput style={s.input} value={tagline} onChangeText={setTagline} maxLength={120} placeholder="What your max is about" placeholderTextColor={MUTE} />
                    <Text style={s.label}>BIO</Text>
                    <TextInput style={[s.input, s.bio]} value={bio} onChangeText={setBio} maxLength={600} multiline placeholder="Tell subscribers who you are" placeholderTextColor={MUTE} />

                    <Text style={s.label}>ACCENT</Text>
                    <View style={s.swatchRow}>
                        {ACCENTS.map((hex) => (
                            <TouchableOpacity
                                key={hex}
                                style={[s.swatchOuter, accent === hex && s.swatchOuterSel]}
                                onPress={() => setAccent(hex)}
                                activeOpacity={0.8}
                                accessibilityLabel={`Accent color ${hex}`}
                            >
                                <View style={[s.swatchInner, { backgroundColor: hex }]} />
                            </TouchableOpacity>
                        ))}
                    </View>

                    <Text style={s.label}>SOCIALS</Text>
                    <TextInput style={s.input} value={instagram} onChangeText={setInstagram} maxLength={80} placeholder="Instagram" placeholderTextColor={MUTE} autoCapitalize="none" autoCorrect={false} />
                    <TextInput style={[s.input, s.inputStack]} value={tiktok} onChangeText={setTiktok} maxLength={80} placeholder="TikTok" placeholderTextColor={MUTE} autoCapitalize="none" autoCorrect={false} />
                    <TextInput style={[s.input, s.inputStack]} value={youtube} onChangeText={setYoutube} maxLength={80} placeholder="YouTube" placeholderTextColor={MUTE} autoCapitalize="none" autoCorrect={false} />

                    <View style={s.infoCard}>
                        <View style={s.infoRow}>
                            <Text style={s.infoLabel}>Price</Text>
                            <Text style={s.infoValue}>${((creator?.price_cents || 0) / 100).toFixed(2)}/mo</Text>
                        </View>
                        <View style={s.divider} />
                        <View style={s.infoRow}>
                            <Text style={s.infoLabel}>Status</Text>
                            <Text style={[s.infoValue, creator?.status === 'live' && { color: '#2F9E60' }]}>{creator?.status}</Text>
                        </View>
                        <View style={s.divider} />
                        <View style={s.infoRow}>
                            <Text style={s.infoLabel}>Apple review</Text>
                            <Text style={s.infoValue}>{creator?.apple_review_status}</Text>
                        </View>
                    </View>

                    {creator?.status !== 'live' ? (
                        <TouchableOpacity style={s.liveBtn} onPress={goLive} activeOpacity={0.9}>
                            <Text style={s.liveText}>Go live</Text>
                        </TouchableOpacity>
                    ) : null}
                    <Text style={s.note}>Manage your subscription price with the Max team. Payouts are sent monthly.</Text>
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, height: 44 },
    back: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
    topTitle: { fontFamily: fonts.sansSemiBold, fontSize: 16, color: INK },
    saveBtn: { fontFamily: fonts.sansSemiBold, fontSize: 15.5, color: '#2C6BED' },
    saveBtnDisabled: { opacity: 0.35 },
    avatarWrap: { alignItems: 'center', marginTop: 14 },
    avatarCircle: { width: 84, height: 84, borderRadius: 42, overflow: 'hidden', backgroundColor: '#FFFFFF', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.08)' },
    avatarImg: { width: '100%', height: '100%', borderRadius: 42 },
    avatarBusy: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.35)', alignItems: 'center', justifyContent: 'center', borderRadius: 42 },
    changePhoto: { fontFamily: fonts.sansSemiBold, fontSize: 13.5, color: INK, marginTop: 10 },
    label: { fontFamily: fonts.sansSemiBold, fontSize: 11, letterSpacing: 0.8, color: MUTE, marginTop: 18, marginBottom: 8 },
    input: { backgroundColor: '#FFFFFF', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 13, fontFamily: fonts.sans, fontSize: 16, color: INK, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.08)' },
    inputStack: { marginTop: 8 },
    bio: { minHeight: 90, paddingTop: 13 },
    swatchRow: { flexDirection: 'row', justifyContent: 'space-between' },
    swatchOuter: { width: 36, height: 36, borderRadius: 18, padding: 3, borderWidth: 2, borderColor: 'transparent' },
    swatchOuterSel: { borderColor: INK },
    swatchInner: { flex: 1, borderRadius: 14 },
    infoCard: { backgroundColor: '#FFFFFF', borderRadius: 16, marginTop: 24, paddingHorizontal: 14, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.06)' },
    infoRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 14 },
    infoLabel: { fontFamily: fonts.sansMedium, fontSize: 14.5, color: INK },
    infoValue: { fontFamily: fonts.sansSemiBold, fontSize: 14.5, color: MUTE, textTransform: 'capitalize' },
    divider: { height: StyleSheet.hairlineWidth, backgroundColor: 'rgba(0,0,0,0.08)' },
    liveBtn: { height: 52, borderRadius: 26, backgroundColor: INK, alignItems: 'center', justifyContent: 'center', marginTop: 22 },
    liveText: { fontFamily: fonts.sansSemiBold, fontSize: 16, color: '#FFFFFF' },
    note: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, marginTop: 16, lineHeight: 18, textAlign: 'center' },
});
