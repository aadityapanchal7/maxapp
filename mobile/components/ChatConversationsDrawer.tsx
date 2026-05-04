/**
 * Chat sidebar — refined black aesthetic.
 *
 * Layout:
 *   ┌──────────────────────┐
 *   │ Max            ✕ │   ← Playfair serif title
 *   ├──────────────────────┤
 *   │ + New chat           │
 *   │ ─ Recent ─           │
 *   │ chat 1               │   ← scrolls (fills available space)
 *   │ chat 2               │
 *   │ ...                  │
 *   ├──────────────────────┤
 *   │ Tone                 │   ← stacked at bottom, fixed
 *   │ [softcore][med][hard]│
 *   │ Length               │
 *   │ • Concise            │
 *   │ • Medium             │
 *   │ • Detailed           │
 *   └──────────────────────┘
 *
 * Color palette is pure-black with quietly-tuned greys + 1 accent of off-
 * white for active chips. No saturated color anywhere. Hairline borders,
 * minimal padding, generous letter-spacing on labels.
 */

import React, { useCallback, useMemo, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    Modal,
    Platform,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQueryClient } from '@tanstack/react-query';

import api from '../services/api';
import { queryKeys } from '../lib/queryClient';
import { useChatConversationsQuery } from '../hooks/useAppQueries';
import { useAuth } from '../context/AuthContext';
import { fonts, spacing } from '../theme/dark';

/* ── Refined black palette (drawer-local) ───────────────────────────── */
const C = {
    bg:          '#0A0A0B',
    bgRaised:    '#141416',
    bgActive:    '#1E1E22',
    border:      'rgba(255,255,255,0.06)',
    borderStrong:'rgba(255,255,255,0.12)',
    ink:         '#F5F5F4',         // primary text, near-white
    inkMuted:    'rgba(245,245,244,0.55)',
    inkDim:      'rgba(245,245,244,0.32)',
    accent:      '#F5F5F4',         // active chip bg
    accentInk:   '#0A0A0B',         // text on active chip
    danger:      '#E66A55',
};

type Conversation = {
    id: string;
    title: string;
    channel: string;
    is_archived: boolean;
    last_message_at: string | null;
    created_at: string | null;
    updated_at: string | null;
};

export type ChatConversationsDrawerProps = {
    visible: boolean;
    activeConversationId: string | null;
    onClose: () => void;
    onSelect: (conversationId: string) => void;
    onCreated: (conversationId: string) => void;
};

/* ── Preference vocabularies ────────────────────────────────────────── */
type ToneId = 'softcore' | 'mediumcore' | 'hardcore';
type ToneBackend = 'gentle' | 'default' | 'hardcore';

const TONE_OPTIONS: { id: ToneId; backend: ToneBackend; label: string }[] = [
    { id: 'softcore',   backend: 'gentle',   label: 'Softcore'   },
    { id: 'mediumcore', backend: 'default',  label: 'Mediumcore' },
    { id: 'hardcore',   backend: 'hardcore', label: 'Hardcore'   },
];
const TONE_BY_BACKEND: Record<string, ToneId> = {
    gentle: 'softcore',
    default: 'mediumcore',
    hardcore: 'hardcore',
    influencer: 'mediumcore',
};

type LengthId = 'concise' | 'medium' | 'detailed';
const LENGTH_OPTIONS: { id: LengthId; label: string; hint: string }[] = [
    { id: 'concise',  label: 'Concise',  hint: 'one short sentence' },
    { id: 'medium',   label: 'Medium',   hint: 'two or three sentences' },
    { id: 'detailed', label: 'Detailed', hint: 'long, specific, numbered' },
];

/* ── Helpers ────────────────────────────────────────────────────────── */
function formatWhen(iso: string | null): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const today = new Date();
    const sameDay =
        d.getFullYear() === today.getFullYear() &&
        d.getMonth() === today.getMonth() &&
        d.getDate() === today.getDate();
    if (sameDay) {
        return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/* ── Component ──────────────────────────────────────────────────────── */
export default function ChatConversationsDrawer({
    visible,
    activeConversationId,
    onClose,
    onSelect,
    onCreated,
}: ChatConversationsDrawerProps) {
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const convQuery = useChatConversationsQuery();
    const { user, refreshUser } = useAuth();

    const [creating, setCreating] = useState(false);
    const [renamingId, setRenamingId] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState('');

    /* Preferences */
    const initialTone: ToneId =
        TONE_BY_BACKEND[user?.coaching_tone || 'default'] || 'mediumcore';
    const initialLength: LengthId =
        (user?.onboarding?.response_length as LengthId) || 'medium';

    const [tone, setTone] = useState<ToneId>(initialTone);
    const [length, setLength] = useState<LengthId>(initialLength);
    const [savingTone, setSavingTone] = useState<ToneId | null>(null);
    const [savingLength, setSavingLength] = useState<LengthId | null>(null);

    React.useEffect(() => {
        if (!user) return;
        setTone(TONE_BY_BACKEND[user.coaching_tone || 'default'] || 'mediumcore');
        setLength((user?.onboarding?.response_length as LengthId) || 'medium');
    }, [user]);

    const conversations: Conversation[] = useMemo(
        () => (convQuery.data ?? []) as Conversation[],
        [convQuery.data]
    );

    const invalidate = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.chatConversations });
    }, [queryClient]);

    const handleNewChat = useCallback(async () => {
        if (creating) return;
        setCreating(true);
        try {
            const { conversation } = await api.createChatConversation();
            invalidate();
            onCreated(conversation.id);
            onClose();
        } catch (e: any) {
            Alert.alert('Could not start a new chat', e?.message || 'Please try again.');
        } finally {
            setCreating(false);
        }
    }, [creating, invalidate, onClose, onCreated]);

    const handleSelect = useCallback(
        (id: string) => { onSelect(id); onClose(); },
        [onClose, onSelect]
    );

    const startRename = useCallback((conv: Conversation) => {
        setRenamingId(conv.id);
        setRenameValue(conv.title);
    }, []);

    const commitRename = useCallback(async () => {
        if (!renamingId) return;
        const title = renameValue.trim();
        if (!title) { setRenamingId(null); return; }
        try {
            await api.renameChatConversation(renamingId, title);
            invalidate();
        } catch (e: any) {
            Alert.alert('Rename failed', e?.message || 'Please try again.');
        } finally {
            setRenamingId(null);
            setRenameValue('');
        }
    }, [invalidate, renameValue, renamingId]);

    const confirmDelete = useCallback(
        (conv: Conversation) => {
            Alert.alert(
                'Delete chat?',
                `"${conv.title}" will be permanently removed.`,
                [
                    { text: 'Cancel', style: 'cancel' },
                    {
                        text: 'Delete',
                        style: 'destructive',
                        onPress: async () => {
                            try {
                                await api.deleteChatConversation(conv.id);
                                invalidate();
                                if (conv.id === activeConversationId) onSelect('');
                            } catch (e: any) {
                                Alert.alert('Delete failed', e?.message || 'Please try again.');
                            }
                        },
                    },
                ]
            );
        },
        [activeConversationId, invalidate, onSelect]
    );

    const applyTone = useCallback(
        async (next: ToneId) => {
            if (next === tone || savingTone) return;
            const target = TONE_OPTIONS.find((t) => t.id === next);
            if (!target) return;
            const previous = tone;
            setTone(next);
            setSavingTone(next);
            try {
                await api.patchCoachingTone(target.backend);
                await refreshUser().catch(() => undefined);
            } catch (e: any) {
                setTone(previous);
                Alert.alert('Could not update tone', e?.message || 'Please try again.');
            } finally {
                setSavingTone(null);
            }
        },
        [refreshUser, savingTone, tone]
    );

    const applyLength = useCallback(
        async (next: LengthId) => {
            if (next === length || savingLength) return;
            const previous = length;
            setLength(next);
            setSavingLength(next);
            try {
                await api.patchResponseLength(next);
                await refreshUser().catch(() => undefined);
            } catch (e: any) {
                setLength(previous);
                Alert.alert('Could not update response length', e?.message || 'Please try again.');
            } finally {
                setSavingLength(null);
            }
        },
        [length, refreshUser, savingLength]
    );

    /* ── Render ──────────────────────────────────────────────────────── */
    return (
        <Modal animationType="fade" transparent visible={visible} onRequestClose={onClose}>
            <Pressable style={s.backdrop} onPress={onClose} accessibilityLabel="Close" />
            <View
                style={[
                    s.drawer,
                    {
                        paddingTop: Math.max(insets.top + spacing.md, 44),
                        paddingBottom: Math.max(insets.bottom + spacing.sm, spacing.md),
                    },
                ]}
            >
                {/* ── Header ─────────────────────────────────────────── */}
                <View style={s.header}>
                    <Text style={s.title}>Max</Text>
                    <TouchableOpacity
                        onPress={onClose}
                        style={s.closeBtn}
                        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                        accessibilityLabel="Close"
                    >
                        <Ionicons name="close" size={18} color={C.inkMuted} />
                    </TouchableOpacity>
                </View>

                {/* ── New chat ──────────────────────────────────────── */}
                <TouchableOpacity
                    style={s.newChatBtn}
                    onPress={handleNewChat}
                    activeOpacity={0.85}
                    disabled={creating}
                >
                    {creating ? (
                        <ActivityIndicator size="small" color={C.ink} />
                    ) : (
                        <>
                            <Ionicons name="add" size={15} color={C.ink} style={{ marginRight: 6 }} />
                            <Text style={s.newChatText}>New chat</Text>
                        </>
                    )}
                </TouchableOpacity>

                {/* ── Recent chats — fills available vertical space ── */}
                <View style={s.chatsWrap}>
                    <Text style={s.label}>Recent</Text>
                    <ScrollView
                        showsVerticalScrollIndicator={false}
                        contentContainerStyle={{ paddingBottom: 12 }}
                    >
                        {convQuery.isPending && conversations.length === 0 && (
                            <ActivityIndicator size="small" color={C.inkDim} style={{ marginTop: 12 }} />
                        )}
                        {!convQuery.isPending && conversations.length === 0 && (
                            <Text style={s.empty}>no chats yet</Text>
                        )}
                        {conversations.map((conv) => {
                            const isActive = conv.id === activeConversationId;
                            const isRenaming = renamingId === conv.id;
                            return (
                                <View key={conv.id} style={[s.row, isActive && s.rowActive]}>
                                    {isRenaming ? (
                                        <TextInput
                                            style={s.renameInput}
                                            value={renameValue}
                                            onChangeText={setRenameValue}
                                            autoFocus
                                            onBlur={commitRename}
                                            onSubmitEditing={commitRename}
                                            returnKeyType="done"
                                            placeholder="title"
                                            placeholderTextColor={C.inkDim}
                                            maxLength={60}
                                        />
                                    ) : (
                                        <TouchableOpacity
                                            style={s.rowMain}
                                            onPress={() => handleSelect(conv.id)}
                                            onLongPress={() => startRename(conv)}
                                            activeOpacity={0.6}
                                        >
                                            <Text style={s.rowTitle} numberOfLines={1}>
                                                {conv.title || 'new chat'}
                                            </Text>
                                            <Text style={s.rowMeta}>
                                                {formatWhen(conv.last_message_at || conv.created_at)}
                                            </Text>
                                        </TouchableOpacity>
                                    )}
                                    <TouchableOpacity
                                        style={s.rowDel}
                                        onPress={() => confirmDelete(conv)}
                                        accessibilityLabel="Delete chat"
                                        hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                                    >
                                        <Ionicons name="trash-outline" size={14} color={C.inkDim} />
                                    </TouchableOpacity>
                                </View>
                            );
                        })}
                    </ScrollView>
                </View>

                {/* ── Settings (stacked at bottom) ──────────────────── */}
                <View style={s.settings}>
                    <View style={s.divider} />

                    <Text style={s.label}>Tone</Text>
                    <View style={s.toneRow}>
                        {TONE_OPTIONS.map((opt) => {
                            const active = opt.id === tone;
                            const busy = savingTone === opt.id;
                            return (
                                <TouchableOpacity
                                    key={opt.id}
                                    style={[s.toneChip, active && s.toneChipActive]}
                                    onPress={() => applyTone(opt.id)}
                                    activeOpacity={0.85}
                                    disabled={!!savingTone}
                                >
                                    {busy ? (
                                        <ActivityIndicator
                                            size="small"
                                            color={active ? C.accentInk : C.ink}
                                        />
                                    ) : (
                                        <Text style={[s.toneChipText, active && s.toneChipTextActive]}>
                                            {opt.label}
                                        </Text>
                                    )}
                                </TouchableOpacity>
                            );
                        })}
                    </View>

                    <Text style={[s.label, { marginTop: 14 }]}>Length</Text>
                    <View style={{ gap: 4 }}>
                        {LENGTH_OPTIONS.map((opt) => {
                            const active = opt.id === length;
                            const busy = savingLength === opt.id;
                            return (
                                <TouchableOpacity
                                    key={opt.id}
                                    style={s.lenRow}
                                    onPress={() => applyLength(opt.id)}
                                    activeOpacity={0.7}
                                    disabled={!!savingLength}
                                >
                                    <View style={[s.lenDot, active && s.lenDotActive]} />
                                    <View style={{ flex: 1 }}>
                                        <Text style={[s.lenLabel, active && s.lenLabelActive]}>
                                            {opt.label}
                                        </Text>
                                        <Text style={s.lenHint}>{opt.hint}</Text>
                                    </View>
                                    {busy && <ActivityIndicator size="small" color={C.inkMuted} />}
                                </TouchableOpacity>
                            );
                        })}
                    </View>
                </View>
            </View>
        </Modal>
    );
}

/* ── Styles ─────────────────────────────────────────────────────────── */
const DRAWER_WIDTH = Platform.select({ default: 320, web: 360 }) ?? 320;

const s = StyleSheet.create({
    backdrop: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(0,0,0,0.55)',
    },
    drawer: {
        position: 'absolute',
        top: 0,
        bottom: 0,
        left: 0,
        width: DRAWER_WIDTH,
        backgroundColor: C.bg,
        paddingHorizontal: spacing.md,
    },
    /* header */
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 14,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 26,
        fontWeight: '400',
        letterSpacing: -0.4,
        color: C.ink,
    },
    closeBtn: {
        width: 28,
        height: 28,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 14,
        backgroundColor: C.bgRaised,
    },
    /* new chat */
    newChatBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        height: 38,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: C.borderStrong,
        backgroundColor: C.bgRaised,
        marginBottom: 14,
    },
    newChatText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        color: C.ink,
        letterSpacing: 0.1,
    },
    /* labels */
    label: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 10,
        letterSpacing: 1.4,
        textTransform: 'uppercase',
        color: C.inkMuted,
        marginBottom: 8,
    },
    empty: {
        fontFamily: fonts.sans,
        fontSize: 12,
        color: C.inkDim,
        marginTop: 8,
        letterSpacing: 0.2,
    },
    /* chats area */
    chatsWrap: {
        flex: 1,
        minHeight: 0,
    },
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 9,
        paddingHorizontal: 10,
        borderRadius: 8,
        marginBottom: 2,
    },
    rowActive: {
        backgroundColor: C.bgActive,
    },
    rowMain: { flex: 1 },
    rowTitle: {
        fontFamily: fonts.sansMedium,
        fontSize: 13,
        color: C.ink,
        letterSpacing: 0.1,
    },
    rowMeta: {
        fontFamily: fonts.sans,
        fontSize: 11,
        color: C.inkDim,
        marginTop: 1,
    },
    rowDel: {
        paddingHorizontal: 6,
        paddingVertical: 4,
    },
    renameInput: {
        flex: 1,
        fontFamily: fonts.sans,
        fontSize: 13,
        color: C.ink,
        paddingVertical: 4,
        paddingHorizontal: 6,
        borderRadius: 6,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: C.borderStrong,
        backgroundColor: C.bgRaised,
    },
    /* settings (stacked bottom) */
    settings: {
        paddingTop: 4,
    },
    divider: {
        height: StyleSheet.hairlineWidth,
        backgroundColor: C.border,
        marginBottom: 14,
    },
    /* tone chips */
    toneRow: {
        flexDirection: 'row',
        gap: 4,
    },
    toneChip: {
        flexGrow: 1,
        flexBasis: 0,
        paddingVertical: 8,
        borderRadius: 8,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 1,
        borderColor: C.border,
        backgroundColor: 'transparent',
    },
    toneChipActive: {
        backgroundColor: C.accent,
        borderColor: C.accent,
    },
    toneChipText: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        color: C.ink,
        letterSpacing: 0.1,
    },
    toneChipTextActive: {
        color: C.accentInk,
        fontFamily: fonts.sansSemiBold,
    },
    /* length rows */
    lenRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 8,
        paddingHorizontal: 10,
        borderRadius: 8,
        backgroundColor: 'transparent',
    },
    lenDot: {
        width: 8,
        height: 8,
        borderRadius: 4,
        borderWidth: 1,
        borderColor: C.borderStrong,
        marginRight: 12,
    },
    lenDotActive: {
        backgroundColor: C.accent,
        borderColor: C.accent,
    },
    lenLabel: {
        fontFamily: fonts.sansMedium,
        fontSize: 13,
        color: C.inkMuted,
        letterSpacing: 0.1,
    },
    lenLabelActive: {
        color: C.ink,
    },
    lenHint: {
        fontFamily: fonts.sans,
        fontSize: 10.5,
        color: C.inkDim,
        marginTop: 1,
        letterSpacing: 0.1,
    },
});
