import React, { useState, useRef } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    TextInput,
    ActivityIndicator,
    Alert,
    KeyboardAvoidingView,
    Platform,
    ScrollView,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import api from '../../services/api';
import { queryKeys } from '../../lib/queryClient';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';

export default function NewThreadV2Screen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const queryClient = useQueryClient();
    const route = useRoute<any>();
    const params = route.params ?? {};
    const subforumId = params.subforumId as string;
    const subforumName = (params.subforumName as string) ?? 'board';

    const scrollRef = useRef<ScrollView>(null);
    const titleInputRef = useRef<TextInput>(null);
    const bodyInputRef = useRef<TextInput>(null);

    const [title, setTitle] = useState('');
    const [body, setBody] = useState('');
    const [tags, setTags] = useState('');
    const [saving, setSaving] = useState(false);
    const [showErrors, setShowErrors] = useState(false);

    const titleErr = showErrors && !title.trim();
    const bodyErr = showErrors && !body.trim();

    const submit = async () => {
        const t = title.trim();
        const b = body.trim();
        if (!t || !b) {
            setShowErrors(true);
            if (!t) titleInputRef.current?.focus();
            else bodyInputRef.current?.focus();
            return;
        }
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

    const keyboardOffset = Platform.OS === 'ios' ? insets.top + 4 : 0;
    const postDisabled = saving || !title.trim() || !body.trim();

    return (
        <View style={styles.container}>
            <KeyboardAvoidingView
                style={styles.flex}
                behavior={Platform.OS === 'ios' ? 'padding' : undefined}
                keyboardVerticalOffset={keyboardOffset}
            >
                <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
                    <TouchableOpacity
                        onPress={() => navigation.goBack()}
                        style={styles.iconBtn}
                        activeOpacity={0.8}
                        accessibilityRole="button"
                        accessibilityLabel="Go back"
                    >
                        <Ionicons name="arrow-back" size={20} color={colors.textSecondary} />
                    </TouchableOpacity>
                    <View style={{ flex: 1 }}>
                        <Text style={styles.title}>New thread</Text>
                        <Text style={styles.subtitle} numberOfLines={1}>
                            {subforumName}
                        </Text>
                    </View>
                    <TouchableOpacity
                        onPress={() => void submit()}
                        disabled={saving}
                        style={[styles.postBtn, postDisabled && !saving && styles.postBtnDisabled]}
                        activeOpacity={0.85}
                        accessibilityRole="button"
                        accessibilityLabel="Publish thread"
                        accessibilityHint={postDisabled && !saving ? 'Title and body are required' : undefined}
                        accessibilityState={{ disabled: saving }}
                    >
                        {saving ? (
                            <ActivityIndicator size="small" color={colors.background} />
                        ) : (
                            <Text
                                style={[styles.postBtnText, postDisabled && styles.postBtnTextDisabled]}
                            >
                                Post
                            </Text>
                        )}
                    </TouchableOpacity>
                </View>

                <ScrollView
                    ref={scrollRef}
                    style={styles.flex}
                    contentContainerStyle={[styles.scrollContent, { paddingBottom: spacing.xxl + insets.bottom }]}
                    keyboardShouldPersistTaps="handled"
                    keyboardDismissMode="on-drag"
                    showsVerticalScrollIndicator={false}
                >
                    <View style={styles.card}>
                        <Text style={styles.groupLabel}>Thread</Text>
                        <Text style={styles.label}>Title</Text>
                        <TextInput
                            ref={titleInputRef}
                            style={[styles.input, titleErr && styles.inputError]}
                            placeholder="Make it specific…"
                            placeholderTextColor={colors.textMuted}
                            value={title}
                            onChangeText={(v) => {
                                setTitle(v);
                                if (showErrors && v.trim() && body.trim()) setShowErrors(false);
                            }}
                            editable={!saving}
                            maxLength={200}
                            returnKeyType="next"
                            onSubmitEditing={() => bodyInputRef.current?.focus()}
                        />
                        {titleErr ? <Text style={styles.errorText}>Add a short, descriptive title.</Text> : null}

                        <Text style={[styles.label, { marginTop: spacing.lg }]}>Body</Text>
                        <TextInput
                            ref={bodyInputRef}
                            style={[styles.input, styles.bodyInput, bodyErr && styles.inputError]}
                            placeholder="Context, questions, or details help others reply."
                            placeholderTextColor={colors.textMuted}
                            value={body}
                            onChangeText={(v) => {
                                setBody(v);
                                if (showErrors && v.trim() && title.trim()) setShowErrors(false);
                            }}
                            editable={!saving}
                            multiline
                            textAlignVertical="top"
                            onFocus={() => setTimeout(() => scrollRef.current?.scrollTo({ y: 120, animated: true }), 100)}
                        />
                        {bodyErr ? <Text style={styles.errorText}>Write the main post before publishing.</Text> : null}
                    </View>

                    <View style={[styles.card, styles.cardSecond]}>
                        <Text style={styles.groupLabel}>Optional</Text>
                        <Text style={styles.label}>Tags</Text>
                        <Text style={styles.hint}>Comma-separated — helps people find your thread.</Text>
                        <TextInput
                            style={styles.input}
                            placeholder="jaw, skin, hair…"
                            placeholderTextColor={colors.textMuted}
                            value={tags}
                            onChangeText={setTags}
                            editable={!saving}
                            autoCapitalize="none"
                        />
                    </View>
                </ScrollView>
            </KeyboardAvoidingView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background, overflow: 'hidden' },
    flex: { flex: 1 },
    header: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.md,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
        backgroundColor: colors.background,
        zIndex: 1,
    },
    iconBtn: {
        width: 40,
        height: 40,
        alignItems: 'center',
        justifyContent: 'center',
    },
    title: { fontFamily: fonts.serif, color: colors.foreground, fontSize: 20, fontWeight: '400' },
    subtitle: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
    postBtn: {
        minHeight: 34,
        paddingHorizontal: 16,
        borderRadius: borderRadius.full,
        backgroundColor: colors.foreground,
        alignItems: 'center',
        justifyContent: 'center',
    },
    postBtnDisabled: { backgroundColor: colors.border },
    postBtnText: { color: colors.background, fontSize: 13, fontWeight: '800' },
    postBtnTextDisabled: { color: colors.textMuted },
    scrollContent: { padding: spacing.lg },
    card: {
        padding: spacing.lg,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
    },
    cardSecond: { marginTop: spacing.lg },
    groupLabel: {
        ...typography.label,
        marginBottom: spacing.md,
        color: colors.textSecondary,
    },
    label: { color: colors.textSecondary, fontSize: 12, fontWeight: '800', marginBottom: spacing.sm },
    hint: { ...typography.bodySmall, marginBottom: spacing.sm, marginTop: -4 },
    input: {
        backgroundColor: colors.surface,
        borderWidth: 1,
        borderColor: colors.borderLight,
        borderRadius: borderRadius.lg,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.md,
        color: colors.foreground,
        fontSize: 15,
    },
    inputError: { borderColor: colors.error },
    bodyInput: { minHeight: 200, lineHeight: 22 },
    errorText: { color: colors.error, fontSize: 12, fontWeight: '600', marginTop: spacing.sm },
});
