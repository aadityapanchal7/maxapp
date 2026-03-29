import React, { type ComponentProps } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Pressable, Platform } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography, shadows } from '../../theme/dark';
import type { LegalDocId } from '../legal/legalDocuments';

const POLICY_ROWS: { id: LegalDocId; title: string; icon: ComponentProps<typeof Ionicons>['name'] }[] = [
    { id: 'privacy', title: 'Privacy policy', icon: 'document-text-outline' },
    { id: 'terms', title: 'Terms of service', icon: 'reader-outline' },
    { id: 'community', title: 'Community guidelines', icon: 'people-outline' },
    { id: 'cookies', title: 'Cookie notice', icon: 'information-circle-outline' },
];

export default function SettingsScreen() {
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();

    const openDoc = (document: LegalDocId) => {
        navigation.navigate('LegalDocument', { document });
    };

    return (
        <View style={styles.container}>
            <View style={[styles.topBar, { paddingTop: Math.max(insets.top, 12) }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.title}>Settings</Text>
                <View style={{ width: 40 }} />
            </View>

            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                {POLICY_ROWS.map((row) => (
                    <Pressable
                        key={row.id}
                        onPress={() => openDoc(row.id)}
                        style={({ pressed }) => [styles.docPress, pressed && styles.docPressPressed]}
                        accessibilityRole="link"
                    >
                        <Ionicons name={row.icon} size={16} color={colors.textMuted} style={styles.docIcon} />
                        <Text style={styles.docLink}>{row.title}</Text>
                    </Pressable>
                ))}

                <View style={{ height: Platform.OS === 'ios' ? 48 : 32 }} />
            </ScrollView>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.background },
    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.md,
        paddingBottom: spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        ...shadows.sm,
    },
    backBtn: { padding: spacing.xs },
    title: { ...typography.h3, color: colors.foreground, fontWeight: '700' },
    scroll: { padding: spacing.lg, paddingBottom: spacing.xxl, maxWidth: 720, width: '100%', alignSelf: 'center' },
    docPress: {
        flexDirection: 'row',
        alignItems: 'center',
        alignSelf: 'flex-start',
        paddingVertical: spacing.sm,
        paddingRight: spacing.md,
        gap: spacing.sm,
    },
    docPressPressed: { opacity: 0.55 },
    docIcon: { marginTop: 1 },
    docLink: {
        fontSize: 13,
        color: colors.textMuted,
        lineHeight: 20,
        textDecorationLine: 'underline',
        textDecorationColor: colors.textMuted,
    },
});
