/**
 * CourseEditorScreen — the creator edits their DB-backed course lessons
 * (module → ordered lessons; title + body + optional video). Publishing bumps
 * the course version so subscribers refetch.
 *
 * Lessons are grouped by module (inline rename + reorder), the editor sheet
 * carries video/duration/free-preview/icon, saves are three-state
 * (Save keeps the current status / Publish / explicit Unpublish) so editing a
 * live lesson never silently unpublishes it, and an AI assist can draft a
 * lesson body or bootstrap a whole outline for an empty course.
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

const INK = '#111113';
const MUTE = '#6B6B6B';
const BG = '#F1F1EF';
const CREAM = '#F1F1EF';
const GOLD = '#B8860B';

const LESSON_ICONS = [
    'book-outline', 'barbell-outline', 'water-outline', 'sunny-outline',
    'film-outline', 'timer-outline', 'sparkles-outline', 'ribbon-outline',
] as const;

type Lesson = {
    id?: string;
    module_number: number;
    sort: number;
    title: string;
    subtitle: string;
    body_md: string;
    video_url?: string | null;
    poster_url?: string | null;
    icon?: string;
    status: string;
    is_free_preview?: boolean;
    duration_minutes?: number | null;
};

type ModuleMap = Record<string, { title?: string }>;

export default function CourseEditorScreen() {
    const nav = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const [lessons, setLessons] = useState<Lesson[]>([]);
    const [modules, setModules] = useState<ModuleMap>({});
    const [loading, setLoading] = useState(true);
    const [maxxId, setMaxxId] = useState<string | null>(null);

    // Editor sheet
    const [editing, setEditing] = useState<Lesson | null>(null);
    const [savingAction, setSavingAction] = useState<null | 'save' | 'publish' | 'unpublish'>(null);
    const [aiBusy, setAiBusy] = useState(false);
    const baselineRef = useRef<string>('');

    // Module rename sheet
    const [renameModule, setRenameModule] = useState<number | null>(null);
    const [renameDraft, setRenameDraft] = useState('');
    const [renameSaving, setRenameSaving] = useState(false);

    // AI outline sheet (empty-course bootstrap)
    const [outlineOpen, setOutlineOpen] = useState(false);
    const [outlineTopic, setOutlineTopic] = useState('');
    const [outlineBusy, setOutlineBusy] = useState(false);
    const [outlineProgress, setOutlineProgress] = useState('');

    const load = useCallback(async () => {
        try {
            const [res, me] = await Promise.all([
                api.getMyCreatorLessons(),
                api.getMyCreator().catch(() => null),
            ]);
            setLessons(res.lessons || []);
            setModules(res.course_modules || {});
            if (me?.maxx_id) setMaxxId(me.maxx_id);
        } catch { /* keep */ }
        finally { setLoading(false); }
    }, []);
    useFocusEffect(useCallback(() => { void load(); }, [load]));

    const publishedCount = lessons.filter((l) => l.status === 'published').length;
    const draftCount = lessons.length - publishedCount;
    const moduleNumbers = Array.from(new Set(lessons.map((l) => l.module_number))).sort((a, b) => a - b);

    // ── Editor open/close ────────────────────────────────────────────────
    const openEditor = (l: Lesson) => {
        const copy = { ...l };
        baselineRef.current = JSON.stringify(copy);
        setEditing(copy);
    };

    const openNew = () => {
        const maxModule = lessons.length ? Math.max(...lessons.map((l) => l.module_number)) : 1;
        const inModule = lessons.filter((l) => l.module_number === maxModule).length;
        openEditor({
            module_number: maxModule, sort: inModule, title: '', subtitle: '', body_md: '',
            video_url: '', icon: 'book-outline', status: 'draft', is_free_preview: false,
            duration_minutes: null,
        });
    };

    const isDirty = () => !!editing && JSON.stringify(editing) !== baselineRef.current;

    const requestCloseEditor = () => {
        if (isDirty()) {
            Alert.alert('Discard changes?', undefined, [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Discard', style: 'destructive', onPress: () => setEditing(null) },
            ]);
        } else {
            setEditing(null);
        }
    };

    // ── Save (three-state) ───────────────────────────────────────────────
    const saveLesson = async (mode: 'save' | 'publish' | 'unpublish') => {
        if (!editing) return;
        if (!editing.title.trim()) { Alert.alert('Add a title'); return; }
        if (mode === 'publish' && !editing.body_md.trim()) {
            Alert.alert('Add lesson content', 'Write something in the lesson body before publishing.');
            return;
        }
        // 'save' preserves the lesson's current status (new lessons are drafts).
        const status = mode === 'publish' ? 'published' : mode === 'unpublish' ? 'draft' : editing.status;
        setSavingAction(mode);
        try {
            const payload: Record<string, unknown> = {
                module_number: editing.module_number,
                sort: editing.sort,
                title: editing.title.trim(),
                subtitle: editing.subtitle,
                body_md: editing.body_md,
                video_url: (editing.video_url || '').trim() || null,
                icon: editing.icon || 'book-outline',
                is_free_preview: !!editing.is_free_preview,
                duration_minutes: editing.duration_minutes ?? null,
                status,
            };
            if (editing.id) payload.id = editing.id;
            await api.upsertCreatorLesson(payload);
            setEditing(null);
            await load();
        } catch (e: any) {
            Alert.alert('Could not save', e?.response?.data?.detail || 'Try again.');
        } finally { setSavingAction(null); }
    };

    const confirmUnpublish = () => Alert.alert('Hide this lesson from subscribers?', undefined, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Unpublish', style: 'destructive', onPress: () => { void saveLesson('unpublish'); } },
    ]);

    const del = (l: Lesson) => Alert.alert('Delete lesson?', undefined, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: async () => {
            if (!l.id) return;
            try { await api.deleteCreatorLesson(l.id); await load(); } catch { /* */ }
        } },
    ]);

    // ── Reorder within a module ──────────────────────────────────────────
    const move = (l: Lesson, dir: -1 | 1) => {
        const mod = lessons.filter((x) => x.module_number === l.module_number).sort((a, b) => a.sort - b.sort);
        const idx = mod.findIndex((x) => x.id === l.id);
        const j = idx + dir;
        if (idx < 0 || j < 0 || j >= mod.length) return;
        const arr = [...mod];
        [arr[idx], arr[j]] = [arr[j], arr[idx]];
        const resorted = arr.map((x, i) => ({ ...x, sort: i }));
        const changed = resorted.filter((x) => {
            const orig = mod.find((o) => o.id === x.id);
            return !!orig && orig.sort !== x.sort;
        });
        // Optimistic — the list renders sorted by `sort`, so swapping is instant.
        setLessons((prev) => prev.map((p) => resorted.find((r) => r.id === p.id) || p));
        const items = changed
            .filter((c): c is Lesson & { id: string } => !!c.id)
            .map((c) => ({ id: c.id, module_number: c.module_number, sort: c.sort }));
        if (!items.length) return;
        api.reorderCreatorLessons(items).catch(() => {
            Alert.alert('Could not reorder', 'Restoring the previous order.');
            void load();
        });
    };

    // ── Module rename ────────────────────────────────────────────────────
    const openRename = (n: number) => {
        setRenameDraft(modules[String(n)]?.title || '');
        setRenameModule(n);
    };
    const saveRename = async () => {
        if (renameModule == null) return;
        setRenameSaving(true);
        try {
            const res = await api.setCreatorModuleTitle(renameModule, renameDraft.trim());
            setModules(res.course_modules || {});
            setRenameModule(null);
        } catch (e: any) {
            Alert.alert('Could not rename', e?.response?.data?.detail || 'Try again.');
        } finally { setRenameSaving(false); }
    };

    // ── AI assist ────────────────────────────────────────────────────────
    const assistAlert = (e: any) => {
        const st = e?.response?.status;
        if (st === 503) Alert.alert('AI assist', 'Not available on this build.');
        else if (st === 502) Alert.alert('Try again', 'The draft came back malformed.');
        else Alert.alert('AI assist failed', e?.response?.data?.detail || 'Try again.');
    };

    const draftWithAI = () => {
        if (!editing || !editing.title.trim() || aiBusy) return;
        const title = editing.title.trim();
        const run = async () => {
            setAiBusy(true);
            try {
                const res = await api.creatorCourseAssist({ mode: 'lesson', lesson_title: title });
                setEditing((e) => e && {
                    ...e,
                    body_md: res?.body_md || e.body_md,
                    subtitle: e.subtitle.trim() ? e.subtitle : (res?.subtitle || e.subtitle),
                });
            } catch (e: any) {
                assistAlert(e);
            } finally { setAiBusy(false); }
        };
        if (editing.body_md.trim()) {
            Alert.alert('Replace lesson body?', 'The AI draft will overwrite what you’ve written.', [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Overwrite', style: 'destructive', onPress: () => { void run(); } },
            ]);
        } else { void run(); }
    };

    const generateOutline = async () => {
        if (outlineBusy) return;
        setOutlineBusy(true);
        setOutlineProgress('Designing your course…');
        try {
            const res = await api.creatorCourseAssist({ mode: 'outline', topic: outlineTopic.trim() });
            const mods: { title?: string; lessons?: { title: string; subtitle?: string }[] }[] = res?.modules || [];
            if (!mods.length) {
                Alert.alert('Try again', 'The draft came back malformed.');
                return;
            }
            const total = mods.reduce((n, m) => n + (m.lessons?.length || 0), 0);
            setOutlineProgress(`Creating ${total} draft lessons…`);
            for (let i = 0; i < mods.length; i++) {
                const m = mods[i];
                if (m.title) await api.setCreatorModuleTitle(i + 1, m.title);
                const ls = m.lessons || [];
                for (let j = 0; j < ls.length; j++) {
                    await api.upsertCreatorLesson({
                        module_number: i + 1, sort: j, title: ls[j].title,
                        subtitle: ls[j].subtitle || '', body_md: '', status: 'draft',
                    });
                }
            }
            setOutlineOpen(false);
            await load();
        } catch (e: any) {
            assistAlert(e);
            await load(); // keep whatever landed before the failure
        } finally {
            setOutlineBusy(false);
            setOutlineProgress('');
        }
    };

    // ── Render ───────────────────────────────────────────────────────────
    const publishBlocked = !editing?.title.trim() || !editing?.body_md.trim();

    return (
        <View style={[s.root, { paddingTop: insets.top }]}>
            <View style={s.topBar}>
                <TouchableOpacity onPress={() => nav.goBack()} hitSlop={12} style={s.back} accessibilityLabel="Back">
                    <Ionicons name="chevron-back" size={24} color={INK} />
                </TouchableOpacity>
                <View style={s.topCenter}>
                    <Text style={s.topTitle}>Course</Text>
                    <Text style={s.topMeta}>{publishedCount} live · {draftCount} draft</Text>
                </View>
                <View style={s.topRight}>
                    <TouchableOpacity
                        onPress={() => maxxId && nav.navigate('CreatorCourse', { maxxId })}
                        disabled={!maxxId}
                        hitSlop={8}
                        style={!maxxId && s.dim}
                        accessibilityLabel="Preview course"
                    >
                        <Ionicons name="eye-outline" size={21} color={INK} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={openNew} hitSlop={8} accessibilityLabel="Add lesson">
                        <Ionicons name="add" size={26} color={INK} />
                    </TouchableOpacity>
                </View>
            </View>

            {loading ? (
                <ActivityIndicator color={INK} style={{ marginTop: 40 }} />
            ) : (
                <ScrollView contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: insets.bottom + 40 }} showsVerticalScrollIndicator={false}>
                    {lessons.length === 0 ? (
                        <View style={s.emptyWrap}>
                            <Ionicons name="book-outline" size={26} color={MUTE} />
                            <Text style={s.emptyTitle}>Build your course</Text>
                            <Text style={s.empty}>No lessons yet. Start from an AI outline, or tap + to write your first.</Text>
                            <TouchableOpacity style={s.outlineCta} onPress={() => { setOutlineTopic(''); setOutlineOpen(true); }} activeOpacity={0.9}>
                                <Ionicons name="sparkles-outline" size={15} color="#FFFFFF" />
                                <Text style={s.outlineCtaText}>Generate outline with AI</Text>
                            </TouchableOpacity>
                        </View>
                    ) : moduleNumbers.map((n) => {
                        const modLessons = lessons.filter((l) => l.module_number === n).sort((a, b) => a.sort - b.sort);
                        const modTitle = modules[String(n)]?.title;
                        return (
                            <View key={n}>
                                <View style={s.modHeader}>
                                    <View style={{ flex: 1 }}>
                                        <Text style={s.modKicker}>MODULE {n}</Text>
                                        <Text style={[s.modTitle, !modTitle && s.modTitleEmpty]} numberOfLines={1}>
                                            {modTitle || 'Untitled module'}
                                        </Text>
                                    </View>
                                    <TouchableOpacity onPress={() => openRename(n)} hitSlop={10} accessibilityLabel={`Rename module ${n}`}>
                                        <Ionicons name="create-outline" size={18} color={MUTE} />
                                    </TouchableOpacity>
                                </View>
                                {modLessons.map((l, idx) => (
                                    <TouchableOpacity key={l.id} style={s.row} onPress={() => openEditor(l)} activeOpacity={0.7}>
                                        <View style={s.num}><Text style={s.numText}>{l.module_number}.{idx + 1}</Text></View>
                                        <View style={{ flex: 1 }}>
                                            <Text style={s.title} numberOfLines={1}>{l.title}</Text>
                                            {l.subtitle ? <Text style={s.subtitle} numberOfLines={1}>{l.subtitle}</Text> : null}
                                            {(l.duration_minutes || l.is_free_preview) ? (
                                                <View style={s.chipRow}>
                                                    {l.duration_minutes ? (
                                                        <View style={s.chip}><Text style={s.chipText}>{l.duration_minutes} min</Text></View>
                                                    ) : null}
                                                    {l.is_free_preview ? (
                                                        <View style={[s.chip, s.chipFree]}><Text style={[s.chipText, s.chipFreeText]}>FREE</Text></View>
                                                    ) : null}
                                                </View>
                                            ) : null}
                                        </View>
                                        <Text style={[s.status, l.status === 'published' && s.published]}>{l.status}</Text>
                                        <View style={s.reorderCol}>
                                            <TouchableOpacity hitSlop={6} disabled={idx === 0} onPress={() => move(l, -1)} style={idx === 0 && s.dim} accessibilityLabel="Move up">
                                                <Ionicons name="chevron-up" size={15} color={MUTE} />
                                            </TouchableOpacity>
                                            <TouchableOpacity hitSlop={6} disabled={idx === modLessons.length - 1} onPress={() => move(l, 1)} style={idx === modLessons.length - 1 && s.dim} accessibilityLabel="Move down">
                                                <Ionicons name="chevron-down" size={15} color={MUTE} />
                                            </TouchableOpacity>
                                        </View>
                                        <TouchableOpacity hitSlop={8} onPress={() => del(l)} accessibilityLabel="Delete"><Ionicons name="trash-outline" size={16} color={MUTE} /></TouchableOpacity>
                                    </TouchableOpacity>
                                ))}
                            </View>
                        );
                    })}
                </ScrollView>
            )}

            {/* ── Lesson editor sheet ── */}
            <Modal visible={!!editing} transparent animationType="slide" onRequestClose={requestCloseEditor}>
                <View style={s.backdrop}>
                    <Pressable style={StyleSheet.absoluteFill} onPress={requestCloseEditor} />
                    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
                        <View style={[s.sheet, { paddingBottom: insets.bottom + 12 }]}>
                            <View style={s.grabber} />
                            <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                                <TextInput style={s.fTitle} value={editing?.title} onChangeText={(t) => setEditing((e) => e && { ...e, title: t })} placeholder="Lesson title" placeholderTextColor={MUTE} maxLength={120} />
                                <TextInput style={s.fSub} value={editing?.subtitle} onChangeText={(t) => setEditing((e) => e && { ...e, subtitle: t })} placeholder="One-line summary" placeholderTextColor={MUTE} maxLength={200} />
                                {editing?.title.trim() ? (
                                    <TouchableOpacity style={s.aiPill} onPress={draftWithAI} disabled={aiBusy} activeOpacity={0.85}>
                                        {aiBusy
                                            ? <ActivityIndicator size="small" color={GOLD} />
                                            : <Ionicons name="sparkles-outline" size={14} color={GOLD} />}
                                        <Text style={s.aiPillText}>Draft with AI</Text>
                                    </TouchableOpacity>
                                ) : null}
                                <TextInput style={s.fBody} value={editing?.body_md} onChangeText={(t) => setEditing((e) => e && { ...e, body_md: t })} placeholder="Write the lesson… (markdown supported)" placeholderTextColor={MUTE} multiline maxLength={20000} />
                                <TextInput
                                    style={s.fSub}
                                    value={editing?.video_url || ''}
                                    onChangeText={(t) => setEditing((e) => e && { ...e, video_url: t })}
                                    placeholder="Video URL (optional)"
                                    placeholderTextColor={MUTE}
                                    autoCapitalize="none"
                                    autoCorrect={false}
                                    keyboardType="url"
                                    maxLength={500}
                                />
                                <View style={s.modRow}>
                                    <Text style={s.modLabel}>Module</Text>
                                    <TextInput style={s.modInput} value={String(editing?.module_number ?? 1)} onChangeText={(t) => setEditing((e) => e && { ...e, module_number: parseInt(t || '1', 10) || 1 })} keyboardType="number-pad" maxLength={2} />
                                    <Text style={[s.modLabel, { marginLeft: 14 }]}>Minutes</Text>
                                    <TextInput
                                        style={s.modInput}
                                        value={editing?.duration_minutes != null ? String(editing.duration_minutes) : ''}
                                        onChangeText={(t) => setEditing((e) => {
                                            if (!e) return e;
                                            const n = parseInt(t, 10);
                                            return { ...e, duration_minutes: Number.isFinite(n) && n > 0 ? n : null };
                                        })}
                                        keyboardType="number-pad"
                                        maxLength={3}
                                        placeholder="—"
                                        placeholderTextColor={MUTE}
                                    />
                                </View>
                                <View style={s.toggleRow}>
                                    <View style={{ flex: 1 }}>
                                        <Text style={s.toggleLabel}>Free preview</Text>
                                        <Text style={s.toggleSub}>Non-subscribers can read this lesson</Text>
                                    </View>
                                    <Switch
                                        value={!!editing?.is_free_preview}
                                        onValueChange={(v) => setEditing((e) => e && { ...e, is_free_preview: v })}
                                        trackColor={{ true: INK }}
                                    />
                                </View>
                                <Text style={s.fieldLabel}>ICON</Text>
                                <View style={s.iconRow}>
                                    {LESSON_ICONS.map((ic) => {
                                        const sel = (editing?.icon || 'book-outline') === ic;
                                        return (
                                            <TouchableOpacity key={ic} style={[s.iconDisc, sel && s.iconDiscSel]} onPress={() => setEditing((e) => e && { ...e, icon: ic })} activeOpacity={0.8} accessibilityLabel={ic}>
                                                <Ionicons name={ic} size={16} color={sel ? '#FFFFFF' : MUTE} />
                                            </TouchableOpacity>
                                        );
                                    })}
                                </View>
                            </ScrollView>
                            <View style={s.saveRow}>
                                <TouchableOpacity style={[s.saveBtn, s.draftBtn]} onPress={() => saveLesson('save')} disabled={!!savingAction} activeOpacity={0.85}>
                                    {savingAction === 'save' ? <ActivityIndicator size="small" color={INK} /> : <Text style={s.draftText}>Save</Text>}
                                </TouchableOpacity>
                                <TouchableOpacity
                                    style={[s.saveBtn, s.pubBtn, publishBlocked && s.pubBtnDisabled]}
                                    onPress={() => saveLesson('publish')}
                                    disabled={!!savingAction || publishBlocked}
                                    activeOpacity={0.85}
                                >
                                    {savingAction === 'publish' ? <ActivityIndicator color="#FFFFFF" size="small" /> : <Text style={s.pubText}>Publish</Text>}
                                </TouchableOpacity>
                            </View>
                            {publishBlocked ? (
                                <Text style={s.publishHint}>Add a title and write some lesson content before publishing.</Text>
                            ) : null}
                            {editing?.id && editing.status === 'published' ? (
                                <TouchableOpacity style={s.unpubBtn} onPress={confirmUnpublish} disabled={!!savingAction} hitSlop={8}>
                                    {savingAction === 'unpublish'
                                        ? <ActivityIndicator size="small" color={MUTE} />
                                        : <Text style={s.unpubText}>Unpublish</Text>}
                                </TouchableOpacity>
                            ) : null}
                        </View>
                    </KeyboardAvoidingView>
                </View>
            </Modal>

            {/* ── Module rename sheet ── */}
            <Modal visible={renameModule != null} transparent animationType="fade" onRequestClose={() => setRenameModule(null)}>
                <View style={s.centerBackdrop}>
                    <Pressable style={StyleSheet.absoluteFill} onPress={() => setRenameModule(null)} />
                    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.renameKav}>
                        <View style={s.renameCard}>
                            <Text style={s.renameKicker}>MODULE {renameModule}</Text>
                            <TextInput
                                style={s.renameInput}
                                value={renameDraft}
                                onChangeText={setRenameDraft}
                                placeholder="Module title"
                                placeholderTextColor={MUTE}
                                maxLength={60}
                                autoFocus
                            />
                            <TouchableOpacity style={s.renameSave} onPress={saveRename} disabled={renameSaving} activeOpacity={0.85}>
                                {renameSaving ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Text style={s.renameSaveText}>Save</Text>}
                            </TouchableOpacity>
                        </View>
                    </KeyboardAvoidingView>
                </View>
            </Modal>

            {/* ── AI outline sheet ── */}
            <Modal visible={outlineOpen} transparent animationType="slide" onRequestClose={() => !outlineBusy && setOutlineOpen(false)}>
                <View style={s.backdrop}>
                    <Pressable style={StyleSheet.absoluteFill} onPress={() => !outlineBusy && setOutlineOpen(false)} />
                    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
                        <View style={[s.sheet, { paddingBottom: insets.bottom + 16 }]}>
                            <View style={s.grabber} />
                            <Text style={s.outlineTitle}>Course outline</Text>
                            <Text style={s.outlineSub}>Tell the AI what your course teaches. It drafts modules and lesson titles — every lesson lands as a draft you can edit.</Text>
                            <TextInput
                                style={s.outlineInput}
                                value={outlineTopic}
                                onChangeText={setOutlineTopic}
                                placeholder="Topic — e.g. Clear skin in 30 days"
                                placeholderTextColor={MUTE}
                                maxLength={200}
                                editable={!outlineBusy}
                            />
                            <TouchableOpacity style={[s.saveBtn, s.pubBtn, { marginTop: 14 }]} onPress={generateOutline} disabled={outlineBusy} activeOpacity={0.85}>
                                {outlineBusy ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Text style={s.pubText}>Generate</Text>}
                            </TouchableOpacity>
                            {outlineBusy && outlineProgress ? <Text style={s.progressText}>{outlineProgress}</Text> : null}
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
    outlineCta: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: INK, borderRadius: 24, paddingHorizontal: 20, height: 46, marginTop: 20 },
    outlineCtaText: { fontFamily: fonts.sansSemiBold, fontSize: 14.5, color: '#FFFFFF' },

    modHeader: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, marginTop: 22, marginBottom: 10, paddingHorizontal: 2 },
    modKicker: { fontFamily: fonts.sansSemiBold, fontSize: 10, letterSpacing: 1.2, color: GOLD },
    modTitle: { fontFamily: fonts.serif, fontSize: 19, color: INK, marginTop: 3 },
    modTitleEmpty: { color: MUTE },

    row: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF', borderRadius: 14, padding: 12, marginBottom: 8, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.05)' },
    num: { width: 40, height: 32, borderRadius: 8, backgroundColor: '#F1F1EF', alignItems: 'center', justifyContent: 'center' },
    numText: { fontFamily: fonts.sansSemiBold, fontSize: 12, color: INK },
    title: { fontFamily: fonts.sansMedium, fontSize: 15, color: INK },
    subtitle: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, marginTop: 2 },
    chipRow: { flexDirection: 'row', gap: 6, marginTop: 5 },
    chip: { backgroundColor: '#F1F1EF', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
    chipText: { fontFamily: fonts.sansSemiBold, fontSize: 9.5, color: MUTE, letterSpacing: 0.3 },
    chipFree: { backgroundColor: 'rgba(184,134,11,0.12)' },
    chipFreeText: { color: GOLD },
    status: { fontFamily: fonts.sansSemiBold, fontSize: 10.5, color: MUTE, textTransform: 'uppercase', letterSpacing: 0.4 },
    published: { color: '#2F9E60' },
    reorderCol: { alignItems: 'center', justifyContent: 'center', gap: 2 },

    backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end' },
    sheet: { backgroundColor: CREAM, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: 18, paddingTop: 10, maxHeight: '90%' },
    grabber: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: 'rgba(0,0,0,0.18)', marginBottom: 12 },
    fTitle: { fontFamily: fonts.serif, fontSize: 22, color: INK, paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(0,0,0,0.1)' },
    fSub: { fontFamily: fonts.sans, fontSize: 15, color: INK, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(0,0,0,0.1)' },
    fBody: { fontFamily: fonts.sans, fontSize: 15, color: INK, minHeight: 140, paddingTop: 12, lineHeight: 22 },
    aiPill: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', backgroundColor: '#FFFFFF', borderRadius: 16, paddingHorizontal: 12, height: 32, marginTop: 10, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.1)' },
    aiPillText: { fontFamily: fonts.sansSemiBold, fontSize: 12.5, color: INK },
    modRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 12 },
    modLabel: { fontFamily: fonts.sansMedium, fontSize: 14, color: INK },
    modInput: { width: 56, backgroundColor: '#FFFFFF', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, fontFamily: fonts.sansMedium, fontSize: 15, color: INK, textAlign: 'center', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.1)' },
    toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 16 },
    toggleLabel: { fontFamily: fonts.sansMedium, fontSize: 14.5, color: INK },
    toggleSub: { fontFamily: fonts.sans, fontSize: 12, color: MUTE, marginTop: 2 },
    fieldLabel: { fontFamily: fonts.sansSemiBold, fontSize: 10.5, letterSpacing: 0.8, color: MUTE, marginTop: 18, marginBottom: 8 },
    iconRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
    iconDisc: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.12)' },
    iconDiscSel: { backgroundColor: INK, borderColor: INK },
    saveRow: { flexDirection: 'row', gap: 10, paddingTop: 12 },
    saveBtn: { flex: 1, height: 50, borderRadius: 25, alignItems: 'center', justifyContent: 'center' },
    draftBtn: { backgroundColor: '#FFFFFF', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.12)' },
    draftText: { fontFamily: fonts.sansSemiBold, fontSize: 15, color: INK },
    pubBtn: { backgroundColor: INK },
    pubBtnDisabled: { opacity: 0.35 },
    pubText: { fontFamily: fonts.sansSemiBold, fontSize: 15, color: '#FFFFFF' },
    publishHint: { fontFamily: fonts.sans, fontSize: 12, color: MUTE, textAlign: 'center', marginTop: 8 },
    unpubBtn: { alignSelf: 'center', paddingVertical: 10 },
    unpubText: { fontFamily: fonts.sansMedium, fontSize: 13, color: MUTE },

    centerBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', alignItems: 'center', justifyContent: 'center' },
    renameKav: { width: '100%', alignItems: 'center' },
    renameCard: { width: '86%', backgroundColor: CREAM, borderRadius: 20, padding: 18 },
    renameKicker: { fontFamily: fonts.sansSemiBold, fontSize: 10, letterSpacing: 1.2, color: GOLD },
    renameInput: { fontFamily: fonts.serif, fontSize: 19, color: INK, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(0,0,0,0.12)', marginTop: 6 },
    renameSave: { height: 44, borderRadius: 22, backgroundColor: INK, alignItems: 'center', justifyContent: 'center', marginTop: 16 },
    renameSaveText: { fontFamily: fonts.sansSemiBold, fontSize: 14.5, color: '#FFFFFF' },

    outlineTitle: { fontFamily: fonts.serif, fontSize: 22, color: INK },
    outlineSub: { fontFamily: fonts.sans, fontSize: 13.5, color: MUTE, marginTop: 6, lineHeight: 19 },
    outlineInput: { backgroundColor: '#FFFFFF', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontFamily: fonts.sans, fontSize: 15, color: INK, marginTop: 14, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(0,0,0,0.1)' },
    progressText: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, textAlign: 'center', marginTop: 10 },
});
