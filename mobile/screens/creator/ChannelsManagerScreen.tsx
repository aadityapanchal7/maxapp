/**
 * ChannelsManagerScreen — the creator manages their community channels
 * (create / edit / reorder / archive, cap 8). Create + edit share a centered
 * card sheet (CourseEditor's rename-card pattern) with an "Announcements only"
 * switch. Archiving keeps messages server-side.
 */
import React, { useCallback, useRef, useState } from 'react';
import {
    ActivityIndicator, Alert, KeyboardAvoidingView, Modal, Platform, Pressable,
    ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { fonts } from '../../theme/dark';
import { hexA } from '../../utils/scheduleAggregation';

const INK = '#111113';
const MUTE = '#6B6B6B';
const BG = '#F1F1EF';
const CREAM = '#F1F1EF';
const GOLD = '#B8860B';

const MAX_CHANNELS = 8;

type Channel = {
    id: string;
    name: string;
    description?: string | null;
    icon?: string | null;
    who_can_post?: 'creator' | 'members';
    allow_replies?: boolean;
    message_count?: number;
};

export default function ChannelsManagerScreen() {
    const nav = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const [channels, setChannels] = useState<Channel[]>([]);
    const [creator, setCreator] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    // Card sheet — null = closed; editing = the channel being edited (null for create).
    const [sheetOpen, setSheetOpen] = useState(false);
    const [editingChannel, setEditingChannel] = useState<Channel | null>(null);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [announcementsOnly, setAnnouncementsOnly] = useState(false);
    const [saving, setSaving] = useState(false);
    const [archiving, setArchiving] = useState(false);
    // Dirty-check baseline — snapshot of the sheet's fields as opened.
    const baselineRef = useRef<string>('');
    const isDirty = () => JSON.stringify({ name, description, announcementsOnly }) !== baselineRef.current;

    const load = useCallback(async () => {
        try {
            const [res, me] = await Promise.all([
                api.getMyCreatorChannels(),
                api.getMyCreator().catch(() => null),
            ]);
            setChannels(res.channels || []);
            if (me) setCreator(me);
        } catch { /* keep */ }
        finally { setLoading(false); }
    }, []);
    useFocusEffect(useCallback(() => { void load(); }, [load]));

    const accent = creator?.accent_color || GOLD;

    const openCreate = () => {
        if (channels.length >= MAX_CHANNELS) return;
        setEditingChannel(null);
        setName('');
        setDescription('');
        setAnnouncementsOnly(false);
        baselineRef.current = JSON.stringify({ name: '', description: '', announcementsOnly: false });
        setSheetOpen(true);
    };

    const openEdit = (c: Channel) => {
        setEditingChannel(c);
        setName(c.name || '');
        setDescription(c.description || '');
        setAnnouncementsOnly(c.who_can_post === 'creator');
        baselineRef.current = JSON.stringify({
            name: c.name || '', description: c.description || '', announcementsOnly: c.who_can_post === 'creator',
        });
        setSheetOpen(true);
    };

    const requestCloseSheet = () => {
        if (isDirty()) {
            Alert.alert('Discard changes?', undefined, [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Discard', style: 'destructive', onPress: () => setSheetOpen(false) },
            ]);
        } else {
            setSheetOpen(false);
        }
    };

    const save = async () => {
        if (saving) return;
        if (!name.trim()) { Alert.alert('Add a name'); return; }
        setSaving(true);
        try {
            const body = {
                name: name.trim(),
                description: description.trim(),
                who_can_post: (announcementsOnly ? 'creator' : 'members') as 'creator' | 'members',
            };
            if (editingChannel) await api.updateCreatorChannel(editingChannel.id, body);
            else await api.createCreatorChannel(body);
            setSheetOpen(false);
            await load();
        } catch (e: any) {
            if (e?.response?.status === 409) {
                Alert.alert('Could not save', 'You already have a channel with that name.');
            } else {
                Alert.alert('Could not save', e?.response?.data?.detail || 'Try again.');
            }
        } finally { setSaving(false); }
    };

    const archive = () => {
        if (!editingChannel || archiving) return;
        const target = editingChannel;
        Alert.alert('Archive channel?', 'Messages are kept.', [
            { text: 'Cancel', style: 'cancel' },
            {
                text: 'Archive', style: 'destructive',
                onPress: async () => {
                    setArchiving(true);
                    try {
                        await api.archiveCreatorChannel(target.id);
                        setSheetOpen(false);
                        await load();
                    } catch (e: any) {
                        Alert.alert('Could not archive', e?.response?.data?.detail || 'Try again.');
                    } finally { setArchiving(false); }
                },
            },
        ]);
    };

    // Optimistic reorder — POST the full id order; reload on failure.
    const move = (idx: number, dir: -1 | 1) => {
        const j = idx + dir;
        if (j < 0 || j >= channels.length) return;
        const next = [...channels];
        [next[idx], next[j]] = [next[j], next[idx]];
        setChannels(next);
        api.reorderCreatorChannels(next.map((c) => c.id)).catch(() => {
            Alert.alert('Could not reorder', 'Restoring the previous order.');
            void load();
        });
    };

    const openChat = (c: Channel) => {
        nav.navigate('ChannelChat', {
            channelId: c.id,
            channelName: c.name,
            isAdminOnly: c.who_can_post === 'creator',
            accent,
            maxxId: creator?.maxx_id,
        });
    };

    return (
        <View style={[s.root, { paddingTop: insets.top }]}>
            <View style={s.topBar}>
                <TouchableOpacity onPress={() => nav.goBack()} hitSlop={12} style={s.back} accessibilityLabel="Back">
                    <Ionicons name="chevron-back" size={24} color={INK} />
                </TouchableOpacity>
                <View style={s.topCenter}>
                    <Text style={s.topTitle}>Channels</Text>
                    <Text style={s.topMeta}>{channels.length} of {MAX_CHANNELS}</Text>
                </View>
                <View style={s.topRight}>
                    <TouchableOpacity
                        onPress={openCreate}
                        hitSlop={8}
                        disabled={channels.length >= MAX_CHANNELS}
                        style={channels.length >= MAX_CHANNELS && s.dim}
                        accessibilityLabel="New channel"
                    >
                        <Ionicons name="add" size={26} color={INK} />
                    </TouchableOpacity>
                </View>
            </View>

            {loading ? (
                <ActivityIndicator color={INK} style={{ marginTop: 40 }} />
            ) : (
                <ScrollView
                    contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: insets.bottom + 40 }}
                    showsVerticalScrollIndicator={false}
                >
                    {channels.length === 0 ? (
                        <View style={s.emptyWrap}>
                            <Ionicons name="chatbubbles-outline" size={26} color={MUTE} />
                            <Text style={s.emptyTitle}>Open your community</Text>
                            <Text style={s.empty}>Channels are where members talk. Tap + to create the first one.</Text>
                        </View>
                    ) : channels.map((c, idx) => {
                        const announceOnly = c.who_can_post === 'creator';
                        return (
                            <TouchableOpacity key={c.id} style={s.row} onPress={() => openChat(c)} activeOpacity={0.7}>
                                <View style={[s.disc, { backgroundColor: hexA(accent, 0.14) }]}>
                                    <Ionicons
                                        name={announceOnly ? 'megaphone-outline' : 'chatbubbles-outline'}
                                        size={16}
                                        color={accent}
                                    />
                                </View>
                                <View style={{ flex: 1, minWidth: 0 }}>
                                    <Text style={s.name} numberOfLines={1}>{c.name}</Text>
                                    <Text style={s.desc} numberOfLines={1}>
                                        {c.description || (announceOnly ? 'Announcements only' : 'Open chat')}
                                    </Text>
                                </View>
                                {typeof c.message_count === 'number' && c.message_count > 0 ? (
                                    <Text style={s.count}>{c.message_count}</Text>
                                ) : null}
                                <View style={s.reorderCol}>
                                    <TouchableOpacity hitSlop={6} disabled={idx === 0} onPress={() => move(idx, -1)} style={idx === 0 && s.dim} accessibilityLabel="Move up">
                                        <Ionicons name="chevron-up" size={15} color={MUTE} />
                                    </TouchableOpacity>
                                    <TouchableOpacity hitSlop={6} disabled={idx === channels.length - 1} onPress={() => move(idx, 1)} style={idx === channels.length - 1 && s.dim} accessibilityLabel="Move down">
                                        <Ionicons name="chevron-down" size={15} color={MUTE} />
                                    </TouchableOpacity>
                                </View>
                                <TouchableOpacity hitSlop={8} onPress={() => openEdit(c)} accessibilityLabel={`Edit ${c.name}`}>
                                    <Ionicons name="create-outline" size={17} color={MUTE} />
                                </TouchableOpacity>
                            </TouchableOpacity>
                        );
                    })}
                </ScrollView>
            )}

            {/* ── Create/edit card sheet (rename-card pattern) ── */}
            <Modal visible={sheetOpen} transparent animationType="fade" onRequestClose={requestCloseSheet}>
                <View style={s.centerBackdrop}>
                    <Pressable style={StyleSheet.absoluteFill} onPress={requestCloseSheet} />
                    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.cardKav}>
                        <View style={s.card}>
                            <Text style={s.cardKicker}>{editingChannel ? 'EDIT CHANNEL' : 'NEW CHANNEL'}</Text>
                            <TextInput
                                style={s.cardName}
                                value={name}
                                onChangeText={setName}
                                placeholder="Channel name"
                                placeholderTextColor={MUTE}
                                maxLength={40}
                                autoFocus={!editingChannel}
                            />
                            <TextInput
                                style={s.cardDesc}
                                value={description}
                                onChangeText={setDescription}
                                placeholder="What it's for (optional)"
                                placeholderTextColor={MUTE}
                                maxLength={200}
                            />
                            <View style={s.toggleRow}>
                                <View style={{ flex: 1 }}>
                                    <Text style={s.toggleLabel}>Announcements only</Text>
                                    <Text style={s.toggleSub}>Only you can post; members reply</Text>
                                </View>
                                <Switch
                                    value={announcementsOnly}
                                    onValueChange={setAnnouncementsOnly}
                                    trackColor={{ true: INK }}
                                />
                            </View>
                            <TouchableOpacity style={s.cardSave} onPress={() => { void save(); }} disabled={saving} activeOpacity={0.85}>
                                {saving
                                    ? <ActivityIndicator size="small" color="#FFFFFF" />
                                    : <Text style={s.cardSaveText}>{editingChannel ? 'Save' : 'Create channel'}</Text>}
                            </TouchableOpacity>
                            {editingChannel ? (
                                <TouchableOpacity style={s.archiveBtn} onPress={archive} disabled={archiving} hitSlop={8}>
                                    {archiving
                                        ? <ActivityIndicator size="small" color={MUTE} />
                                        : <Text style={s.archiveText}>Archive channel</Text>}
                                </TouchableOpacity>
                            ) : null}
                        </View>
                    </KeyboardAvoidingView>
                </View>
            </Modal>
        </View>
    );
}

const s = StyleSheet.create({
    root: { flex: 1, backgroundColor: BG },
    topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, height: 48 },
    back: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
    topCenter: { alignItems: 'center' },
    topTitle: { fontFamily: fonts.sansSemiBold, fontSize: 16, color: INK },
    topMeta: { fontFamily: fonts.sans, fontSize: 10.5, color: MUTE, marginTop: 1 },
    topRight: { flexDirection: 'row', alignItems: 'center', gap: 16 },
    dim: { opacity: 0.3 },

    emptyWrap: { alignItems: 'center', marginTop: 56, paddingHorizontal: 12 },
    emptyTitle: { fontFamily: fonts.serif, fontSize: 22, color: INK, marginTop: 12 },
    empty: { fontFamily: fonts.sans, fontSize: 14, color: MUTE, textAlign: 'center', marginTop: 8, lineHeight: 20 },

    row: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF', borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.05)' },
    disc: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
    name: { fontFamily: fonts.sansSemiBold, fontSize: 15, color: INK },
    desc: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, marginTop: 2 },
    count: { fontFamily: fonts.sansMedium, fontSize: 11.5, color: MUTE },
    reorderCol: { alignItems: 'center', justifyContent: 'center', gap: 2 },

    centerBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', alignItems: 'center', justifyContent: 'center' },
    cardKav: { width: '100%', alignItems: 'center' },
    card: { width: '86%', backgroundColor: CREAM, borderRadius: 20, padding: 18 },
    cardKicker: { fontFamily: fonts.sansSemiBold, fontSize: 10, letterSpacing: 1.2, color: GOLD },
    cardName: { fontFamily: fonts.serif, fontSize: 19, color: INK, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(0,0,0,0.12)', marginTop: 6 },
    cardDesc: { fontFamily: fonts.sans, fontSize: 14, color: INK, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(0,0,0,0.12)' },
    toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 16 },
    toggleLabel: { fontFamily: fonts.sansMedium, fontSize: 14.5, color: INK },
    toggleSub: { fontFamily: fonts.sans, fontSize: 12, color: MUTE, marginTop: 2 },
    cardSave: { height: 44, borderRadius: 22, backgroundColor: INK, alignItems: 'center', justifyContent: 'center', marginTop: 18 },
    cardSaveText: { fontFamily: fonts.sansSemiBold, fontSize: 14.5, color: '#FFFFFF' },
    archiveBtn: { alignSelf: 'center', paddingVertical: 10, marginTop: 4 },
    archiveText: { fontFamily: fonts.sansMedium, fontSize: 13, color: '#B3402A' },
});
