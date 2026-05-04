/**
 * Glass-aesthetic "coming soon" full-screen overlay.
 *
 * Looksmaxxing-coded styling:
 *   - oversized serif title (Playfair, the brand display face)
 *   - small uppercase tracked eyebrow ("soon")
 *   - thin lowercase subtitle, very brief — no fluff
 *   - heavy frosted-glass card with a 1px white inner highlight
 *   - three soft blurred orbs floating in the gradient backdrop
 *
 * Drop-in for any unfinished feature:
 *
 *   <ComingSoonOverlay
 *     title="forums"
 *     subtitle="we're cooking."
 *     iconName="people-outline"
 *   />
 */

import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, fonts } from '../theme/dark';

interface Props {
    /** Lowercase one-word title — rendered in the brand serif. */
    title?: string;
    /** Tiny uppercase tracked label above the title. */
    eyebrow?: string;
    /** Short subtitle. Keep it nonchalant. */
    subtitle?: string;
    iconName?: keyof typeof Ionicons.glyphMap;
    cta?: { label: string; onPress: () => void } | null;
    /** Single accent color used for the eyebrow + icon outline. */
    accent?: string;
    style?: ViewStyle;
}

export default function ComingSoonOverlay({
    title = 'coming soon',
    eyebrow = 'soon',
    subtitle = "we're cooking.",
    iconName = 'sparkles-outline',
    cta = null,
    accent = '#6366F1',
    style,
}: Props) {
    return (
        <View style={[styles.root, style]} pointerEvents="box-none">
            {/* Layer 1 — diagonal gradient backdrop */}
            <LinearGradient
                colors={['#f6f5fb', '#eceaf5', '#e6e4ee']}
                start={{ x: 0.05, y: 0.05 }}
                end={{ x: 0.95, y: 0.95 }}
                style={StyleSheet.absoluteFill}
            />

            {/* Layer 2 — three soft blurred orbs for depth */}
            <View pointerEvents="none" style={styles.orbsLayer}>
                <View style={[styles.orb, styles.orbA, { backgroundColor: accent }]} />
                <View style={[styles.orb, styles.orbB, { backgroundColor: '#a78bfa' }]} />
                <View style={[styles.orb, styles.orbC, { backgroundColor: '#7dd3fc' }]} />
            </View>

            {/* Layer 3 — the glass card */}
            <View style={styles.cardWrap}>
                <View style={styles.card}>
                    {/* Heavy backdrop blur. expo-blur on web → backdrop-filter; native → system blur. */}
                    <BlurView
                        intensity={Platform.OS === 'web' ? 90 : 55}
                        tint="light"
                        style={StyleSheet.absoluteFill}
                    />
                    {/* Translucent wash so text contrast is consistent regardless of bg. */}
                    <View style={styles.cardWash} pointerEvents="none" />
                    {/* Top inner highlight — gives the "frosted edge" look. */}
                    <View style={styles.cardEdge} pointerEvents="none" />

                    <View style={styles.iconWrap}>
                        <Ionicons name={iconName} size={22} color={accent} />
                    </View>

                    <Text style={[styles.eyebrow, { color: accent }]}>{eyebrow}</Text>
                    <Text style={styles.title} numberOfLines={1}>{title}</Text>
                    <View style={[styles.divider, { backgroundColor: accent }]} />
                    <Text style={styles.subtitle}>{subtitle}</Text>

                    {cta ? (
                        <Pressable
                            onPress={cta.onPress}
                            style={({ pressed }) => [
                                styles.cta,
                                { borderColor: accent },
                                pressed && styles.ctaPressed,
                            ]}
                            accessibilityRole="button"
                            accessibilityLabel={cta.label}
                        >
                            <Text style={[styles.ctaLabel, { color: accent }]}>{cta.label}</Text>
                        </Pressable>
                    ) : null}
                </View>
            </View>
        </View>
    );
}

const ORB_SIZE = 320;

const styles = StyleSheet.create({
    root: {
        flex: 1,
        position: 'relative',
        overflow: 'hidden',
    },
    orbsLayer: {
        ...StyleSheet.absoluteFillObject,
    },
    orb: {
        position: 'absolute',
        width: ORB_SIZE,
        height: ORB_SIZE,
        borderRadius: ORB_SIZE / 2,
        opacity: 0.32,
        ...(Platform.OS === 'web'
            ? ({ filter: 'blur(90px)' } as any)
            : { shadowColor: '#000', shadowOpacity: 0.0, shadowRadius: 80 }),
    },
    orbA: { top: -100,  left: -80 },
    orbB: { bottom: -40, right: -100 },
    orbC: { top: '38%',  left: '42%', opacity: 0.22 },

    cardWrap: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: spacing.xl,
    },
    card: {
        width: '100%',
        maxWidth: 340,
        borderRadius: 26,
        paddingTop: spacing.xxl + 4,
        paddingBottom: spacing.xxl,
        paddingHorizontal: spacing.xl,
        alignItems: 'center',
        overflow: 'hidden',
        borderWidth: Platform.OS === 'web' ? 1 : StyleSheet.hairlineWidth,
        borderColor: 'rgba(255,255,255,0.6)',
        ...(Platform.OS === 'web'
            ? ({
                boxShadow:
                    '0 28px 64px rgba(15,23,42,0.14), 0 6px 18px rgba(15,23,42,0.06), inset 0 1px 0 rgba(255,255,255,0.7)',
            } as any)
            : {
                shadowColor: '#0f172a',
                shadowOffset: { width: 0, height: 18 },
                shadowOpacity: 0.14,
                shadowRadius: 36,
                elevation: 10,
            }),
    },
    // Translucent wash on top of the BlurView so text stays legible.
    cardWash: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(255,255,255,0.42)',
    },
    // Thin top highlight for the frosted-edge look.
    cardEdge: {
        position: 'absolute',
        top: 0, left: 0, right: 0,
        height: 1,
        backgroundColor: 'rgba(255,255,255,0.85)',
    },

    iconWrap: {
        width: 44, height: 44,
        borderRadius: 22,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(255,255,255,0.55)',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: 'rgba(99,102,241,0.35)',
        marginBottom: spacing.lg,
    },
    eyebrow: {
        fontSize: 11,
        fontFamily: fonts.sansSemiBold,
        letterSpacing: 3.4,
        textTransform: 'uppercase',
        marginBottom: spacing.xs,
        opacity: 0.95,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 44,
        lineHeight: 50,
        color: colors.foreground,
        letterSpacing: -0.5,
        textAlign: 'center',
        marginBottom: spacing.md,
    },
    divider: {
        width: 28,
        height: 1.5,
        opacity: 0.55,
        marginBottom: spacing.md,
        borderRadius: 1,
    },
    subtitle: {
        fontFamily: fonts.sans,
        fontSize: 14,
        lineHeight: 20,
        color: colors.textSecondary ?? '#52525b',
        textAlign: 'center',
        letterSpacing: 0.1,
        opacity: 0.85,
    },
    cta: {
        marginTop: spacing.lg + 2,
        paddingVertical: 9,
        paddingHorizontal: 18,
        borderRadius: 999,
        borderWidth: 1.2,
        backgroundColor: 'rgba(255,255,255,0.55)',
    },
    ctaPressed: { opacity: 0.7 },
    ctaLabel: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13,
        letterSpacing: 0.6,
        textTransform: 'lowercase',
    },
});
