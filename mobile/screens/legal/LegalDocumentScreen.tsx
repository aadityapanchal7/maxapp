import React from 'react';
import {
    View,
    Text,
    StyleSheet,
    ScrollView,
    TouchableOpacity,
    Linking,
    Platform,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';
import type { LegalBlock } from './legalTypes';
import { getLegalBlocks, type LegalDocId } from './legalDocuments';
import { LEGAL_SUPPORT_EMAIL } from './legalConstants';

const TITLES: Record<LegalDocId, string> = {
    privacy: 'Privacy policy',
    terms: 'Terms of service',
    community: 'Community guidelines',
    cookies: 'Cookie notice',
};

const DOC_IDS: LegalDocId[] = ['privacy', 'terms', 'community', 'cookies'];

export default function LegalDocumentScreen() {
    const navigation = useNavigation();
    const route = useRoute<any>();
    const insets = useSafeAreaInsets();
    const raw = route.params?.document as string | undefined;
    const doc: LegalDocId = DOC_IDS.includes(raw as LegalDocId) ? (raw as LegalDocId) : 'privacy';
    const blocks = getLegalBlocks(doc);
    const title = TITLES[doc] ?? 'Legal';

    return (
        <View style={styles.container}>
            <View style={[styles.topBar, { paddingTop: Math.max(insets.top, 12) }]}>
                <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
                    <Ionicons name="arrow-back" size={22} color={colors.foreground} />
                </TouchableOpacity>
                <Text style={styles.title} numberOfLines={1}>
                    {title}
                </Text>
                <View style={{ width: 40 }} />
            </View>

            <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
                {blocks.map((block, i) => (
                    <BlockView key={i} block={block} />
                ))}
                <View style={{ height: Platform.OS === 'ios' ? 40 : 24 }} />
            </ScrollView>
        </View>
    );
}

function BlockView({ block }: { block: LegalBlock }) {
    switch (block.type) {
        case 'meta':
            return <Text style={styles.meta}>{block.text}</Text>;
        case 'h2':
            return <Text style={styles.h2}>{block.text}</Text>;
        case 'h3':
            return <Text style={styles.h3}>{block.text}</Text>;
        case 'p':
            return <Text style={styles.p}>{block.text}</Text>;
        case 'bullets':
            return (
                <View style={styles.bulletWrap}>
                    {block.items.map((line, j) => (
                        <View key={j} style={styles.bulletRow}>
                            <Text style={styles.bulletDot}>•</Text>
                            <Text style={styles.bulletText}>{line}</Text>
                        </View>
                    ))}
                </View>
            );
        case 'callout':
            return (
                <View style={styles.callout}>
                    {block.title ? (
                        <Text style={styles.calloutTitle}>{block.title}</Text>
                    ) : null}
                    <Text style={styles.calloutBody}>{block.text}</Text>
                </View>
            );
        case 'external':
            return (
                <TouchableOpacity
                    style={styles.externalRow}
                    onPress={() => Linking.openURL(block.url)}
                    activeOpacity={0.7}
                >
                    <Ionicons name="open-outline" size={18} color={colors.info} />
                    <Text style={styles.externalText}>{block.label}</Text>
                </TouchableOpacity>
            );
        case 'mailtoLine':
            return (
                <Text style={styles.p}>
                    {block.before}
                    <Text
                        style={styles.link}
                        onPress={() => Linking.openURL(`mailto:${LEGAL_SUPPORT_EMAIL}`)}
                    >
                        {LEGAL_SUPPORT_EMAIL}
                    </Text>
                    {block.after}
                </Text>
            );
        default:
            return null;
    }
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
    title: { ...typography.h3, color: colors.foreground, fontWeight: '700', flex: 1, textAlign: 'center', marginHorizontal: spacing.sm },
    scroll: { padding: spacing.lg, paddingBottom: spacing.xxl, maxWidth: 720, width: '100%', alignSelf: 'center' },
    meta: {
        fontSize: 12,
        color: colors.textMuted,
        lineHeight: 18,
        marginBottom: spacing.lg,
    },
    h2: {
        fontSize: 17,
        fontWeight: '700',
        color: colors.foreground,
        marginTop: spacing.lg,
        marginBottom: spacing.sm,
        letterSpacing: -0.2,
    },
    h3: {
        fontSize: 15,
        fontWeight: '600',
        color: colors.foreground,
        marginTop: spacing.md,
        marginBottom: spacing.xs,
    },
    p: {
        ...typography.body,
        color: colors.textSecondary,
        lineHeight: 22,
        marginBottom: spacing.md,
    },
    bulletWrap: { marginBottom: spacing.md, paddingLeft: spacing.xs },
    bulletRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: spacing.sm, gap: spacing.sm },
    bulletDot: { fontSize: 15, color: colors.textMuted, marginTop: 2, width: 14 },
    bulletText: { flex: 1, ...typography.body, color: colors.textSecondary, lineHeight: 22 },
    callout: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        padding: spacing.md,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    calloutTitle: {
        fontSize: 13,
        fontWeight: '700',
        color: colors.foreground,
        marginBottom: spacing.xs,
    },
    calloutBody: { fontSize: 14, color: colors.textSecondary, lineHeight: 21 },
    externalRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        marginBottom: spacing.md,
        paddingVertical: spacing.xs,
    },
    externalText: {
        flex: 1,
        fontSize: 14,
        color: colors.info,
        fontWeight: '500',
        textDecorationLine: 'underline',
    },
    link: {
        color: colors.info,
        fontWeight: '600',
        textDecorationLine: 'underline',
    },
});
