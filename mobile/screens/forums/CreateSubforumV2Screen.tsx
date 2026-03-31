import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { useForumV2CategoriesQuery } from '../../hooks/useAppQueries';
import { queryKeys } from '../../lib/queryClient';
import { colors, spacing, borderRadius, shadows } from '../../theme/dark';

type Category = { id: string; name: string; slug: string };

export default function CreateSubforumV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const catsQ = useForumV2CategoriesQuery();
    const categories: Category[] = useMemo(() => (catsQ.data ?? []) as Category[], [catsQ.data]);

    const allowed = categories.filter((c) => !['official', 'premium', 'influence'].includes((c.slug || '').toLowerCase()));
    const [categoryId, setCategoryId] = useState<string | null>(allowed[0]?.id ?? null);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!categoryId) return;
        const n = name.trim();
        if (n.length < 2) return;
        setSaving(true);
        try {
            await api.createForumV2Subforum({ category_id: categoryId, name: n, description: description.trim() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.forumV2Subforums(null) });
            navigation.goBack();
        } catch (e: any) {
            const msg = e?.response?.data?.detail || e?.message || 'failed';
            Alert.alert('couldn’t create board', String(msg));
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
                <Text style={styles.title}>Create board</Text>
                <View style={{ flex: 1 }} />
                <TouchableOpacity
                    onPress={() => void submit()}
                    disabled={saving || !categoryId || name.trim().length < 2}
                    style={[styles.saveBtn, (saving || !categoryId || name.trim().length < 2) && styles.saveBtnDisabled]}
                    activeOpacity={0.85}
                >
                    {saving ? <ActivityIndicator size="small" color={colors.background} /> : <Text style={styles.saveBtnText}>create</Text>}
                </TouchableOpacity>
            </View>

            <View style={styles.form}>
                <Text style={styles.label}>category</Text>
                {catsQ.isPending ? (
                    <ActivityIndicator size="small" color={colors.foreground} />
                ) : (
                    <View style={styles.pills}>
                        {allowed.map((c) => (
                            <TouchableOpacity
                                key={c.id}
                                style={[styles.pill, categoryId === c.id && styles.pillActive]}
                                onPress={() => setCategoryId(c.id)}
                                activeOpacity={0.85}
                            >
                                <Text style={[styles.pillText, categoryId === c.id && styles.pillTextActive]}>{c.name}</Text>
                            </TouchableOpacity>
                        ))}
                    </View>
                )}

                <Text style={[styles.label, { marginTop: spacing.lg }]}>name</Text>
                <TextInput
                    style={styles.input}
                    placeholder="e.g. hair product reviews"
                    placeholderTextColor={colors.textMuted}
                    value={name}
                    onChangeText={setName}
                    editable={!saving}
                />

                <Text style={[styles.label, { marginTop: spacing.lg }]}>description</Text>
                <TextInput
                    style={[styles.input, styles.desc]}
                    placeholder="what belongs in here?"
                    placeholderTextColor={colors.textMuted}
                    value={description}
                    onChangeText={setDescription}
                    editable={!saving}
                    multiline
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
    saveBtn: {
        height: 36,
        paddingHorizontal: 14,
        borderRadius: 18,
        backgroundColor: colors.foreground,
        alignItems: 'center',
        justifyContent: 'center',
    },
    saveBtnDisabled: { opacity: 0.45 },
    saveBtnText: { color: colors.background, fontSize: 12, fontWeight: '900' },
    form: { padding: spacing.lg },
    label: { color: colors.textSecondary, fontSize: 12, fontWeight: '800', marginBottom: 8 },
    pills: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    pill: {
        paddingHorizontal: 12,
        height: 32,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: colors.border,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.surfaceLight,
    },
    pillActive: { backgroundColor: colors.foreground, borderColor: colors.foreground },
    pillText: { color: colors.textSecondary, fontSize: 12, fontWeight: '800' },
    pillTextActive: { color: colors.background },
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
    desc: { minHeight: 90, textAlignVertical: 'top' as any },
});

