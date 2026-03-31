import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { queryKeys } from '../../lib/queryClient';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

export default function NewThreadV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const route = useRoute<any>();
    const params = route.params ?? {};
    const subforumId = params.subforumId as string;
    const subforumName = (params.subforumName as string) ?? 'board';

    const [title, setTitle] = useState('');
    const [body, setBody] = useState('');
    const [tags, setTags] = useState('');
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        const t = title.trim();
        const b = body.trim();
        if (!t || !b) return;
        setSaving(true);
        try {
            const tagList = tags
                .split(',')
                .map((x) => x.trim())
                .filter(Boolean);
            const res = await api.createForumV2Thread({
                subforum_id: subforumId,
                title: t,
                body: b,
                tags: tagList,
            });
            const threadId = res?.thread_id || res?.threadId || res?.thread || res?.id || res?.thread_id;
            await queryClient.invalidateQueries({
                predicate: (query) => {
                    const key = query.queryKey;
                    return Array.isArray(key) && key[0] === 'forumV2' && key[1] === 'threads' && key[2] === subforumId;
                },
            });
            if (threadId) {
                navigation.replace('ThreadV2', { threadId, threadTitle: t });
            } else {
                navigation.goBack();
            }
        } catch (e: any) {
            const msg = e?.response?.data?.detail || e?.message || 'failed to post';
            Alert.alert('couldn’t post', String(msg));
        } finally {
            setSaving(false);
        }
    };

    return (
        <View style={styles.container}>
            <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.iconBtn} activeOpacity={0.8}>
                    <Ionicons name="arrow-back" size={20} color={colors.textSecondary} />
                </TouchableOpacity>
                <View style={{ flex: 1 }}>
                    <Text style={styles.title}>new thread</Text>
                    <Text style={styles.subtitle}>{subforumName}</Text>
                </View>
                <TouchableOpacity
                    onPress={submit}
                    disabled={saving || !title.trim() || !body.trim()}
                    style={[styles.postBtn, (saving || !title.trim() || !body.trim()) && styles.postBtnDisabled]}
                    activeOpacity={0.85}
                >
                    {saving ? <ActivityIndicator size="small" color={colors.background} /> : <Text style={styles.postBtnText}>post</Text>}
                </TouchableOpacity>
            </View>

            <View style={styles.form}>
                <Text style={styles.label}>title</Text>
                <TextInput
                    style={styles.input}
                    placeholder="make it specific..."
                    placeholderTextColor={colors.textMuted}
                    value={title}
                    onChangeText={setTitle}
                    editable={!saving}
                />

                <Text style={[styles.label, { marginTop: spacing.lg }]}>body</Text>
                <TextInput
                    style={[styles.input, styles.bodyInput]}
                    placeholder="drop the context. pics help."
                    placeholderTextColor={colors.textMuted}
                    value={body}
                    onChangeText={setBody}
                    editable={!saving}
                    multiline
                />

                <Text style={[styles.label, { marginTop: spacing.lg }]}>tags (comma separated)</Text>
                <TextInput
                    style={styles.input}
                    placeholder="jaw, skin, hair..."
                    placeholderTextColor={colors.textMuted}
                    value={tags}
                    onChangeText={setTags}
                    editable={!saving}
                />
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        backgroundColor: colors.card,
    },
    iconBtn: {
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
        borderWidth: 1,
        borderColor: colors.border,
    },
    title: { color: colors.foreground, fontSize: 18, fontWeight: '900' },
    subtitle: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
    postBtn: {
        height: 36,
        paddingHorizontal: 14,
        borderRadius: 18,
        backgroundColor: colors.foreground,
        alignItems: 'center',
        justifyContent: 'center',
    },
    postBtnDisabled: { opacity: 0.45 },
    postBtnText: { color: colors.background, fontSize: 12, fontWeight: '900' },
    form: { padding: spacing.lg },
    label: { color: colors.textSecondary, fontSize: 12, fontWeight: '800', marginBottom: 8 },
    input: {
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: borderRadius.lg,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        color: colors.foreground,
        ...shadows.sm,
    },
    bodyInput: { minHeight: 220, textAlignVertical: 'top' as any },
});

