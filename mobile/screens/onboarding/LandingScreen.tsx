/**
 * LandingScreen — pre-auth animated intro carousel.
 *
 * Replaces the prior 2-slide intro (hero + coaching) with a 7-slide
 * conversion-optimized arc. Slide 1 keeps the original "max" hero
 * branding; the rest walks the user through the value prop:
 *
 *    01 hero       — "max" / your AI looksmaxxing coach (kept as-is)
 *    02 the gap    — most men plateau at average; the 1% have a system
 *    03 chatbot    — typing dots → real protocol answer (capability)
 *    04 depth      — counters: 5 modules / 67 chapters / 290 lessons
 *    05 personal   — orbiting accent dots around a person glyph
 *    06 reminders  — push notification card sliding in
 *    07 ascend     — bobbing arrow + sign-in / sign-up
 *
 * Each slide has its own accent color; the backdrop cross-fades a soft
 * accent veil between slides. Copy stagger-enters per slide (fade +
 * 12px translateY, out-cubic, 420ms). Final slide swaps the "Next"
 * button for Sign In / Create Account (and a web-only "Try it first").
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    Animated,
    Dimensions,
    Easing,
    FlatList,
    Platform,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
    type LayoutChangeEvent,
    type NativeScrollEvent,
    type NativeSyntheticEvent,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';

import { borderRadius, colors, fonts, spacing } from '../../theme/dark';
import { useAuth } from '../../context/AuthContext';

const isWeb = Platform.OS === 'web';
const { width: SCREEN_WIDTH } = Dimensions.get('window');

/* ── Slides ───────────────────────────────────────────────────────────── */

type Slide = {
    id: string;
    accent: string;
    /** When omitted, the standard eyebrow/title/subtitle layout is used. */
    custom?: 'hero';
    eyebrow?: string;
    title?: string;
    subtitle?: string;
    visual?: React.ComponentType<{ accent: string }>;
};

const SLIDES: Slide[] = [
    // Slide 1 — kept intact: the "max" hero
    {
        id: 'hero',
        accent: '#8B5CF6',
        custom: 'hero',
    },
    {
        id: 'pain',
        accent: '#F59E0B',
        eyebrow: 'THE GAP',
        title: 'Most men plateau at average.',
        subtitle: 'The 1% don\'t have better genes. They have a system. You\'re about to.',
        visual: PainVisual,
    },
    {
        id: 'chat',
        accent: '#3B82F6',
        eyebrow: 'CHATBOT',
        title: 'Ask anything. Get protocols.',
        subtitle: 'Specific doses, exact timing, real product links. No generic advice.',
        visual: ChatVisual,
    },
    {
        id: 'depth',
        accent: '#10B981',
        eyebrow: 'COURSE LIBRARY',
        title: 'The whole playbook.',
        subtitle: '5 modules. 67 chapters. 290 lessons. The protocols the 1% actually use.',
        visual: StatsVisual,
    },
    {
        id: 'personal',
        accent: '#EC4899',
        eyebrow: 'PERSONALIZED',
        title: 'Built around your face.',
        subtitle: 'Your scan, your priorities, your body — every recommendation filters through them.',
        visual: PersonalVisual,
    },
    {
        id: 'loop',
        accent: '#6366F1',
        eyebrow: 'DAILY REMINDERS',
        title: 'Right move at the right time.',
        subtitle: 'Consistency does the work. We just keep you on the schedule.',
        visual: LoopVisual,
    },
    {
        id: 'cta',
        accent: '#8B5CF6',
        eyebrow: 'READY?',
        title: 'Ascend.',
        subtitle: 'Sign in or create an account. Your scan + plan come next.',
        visual: AscendVisual,
    },
];

/* ── Component ────────────────────────────────────────────────────────── */

export default function LandingScreen() {
    const navigation = useNavigation<any>();
    const { fauxSignup, fauxSkipSignup } = useAuth();
    const [active, setActive] = useState(0);
    const [containerWidth, setContainerWidth] = useState(SCREEN_WIDTH);
    const [demoLoading, setDemoLoading] = useState(false);
    const [skipLoading, setSkipLoading] = useState(false);

    const flatRef = useRef<FlatList<Slide>>(null);

    const onLayout = useCallback((e: LayoutChangeEvent) => {
        setContainerWidth(e.nativeEvent.layout.width);
    }, []);

    const onMomentumScrollEnd = useCallback(
        (e: NativeSyntheticEvent<NativeScrollEvent>) => {
            if (!containerWidth) return;
            const i = Math.round(e.nativeEvent.contentOffset.x / containerWidth);
            if (i !== active) setActive(i);
        },
        [active, containerWidth]
    );

    const goNext = useCallback(() => {
        if (active >= SLIDES.length - 1) return;
        flatRef.current?.scrollToIndex({ index: active + 1, animated: true });
        setActive(active + 1);
    }, [active]);

    const handleTryNow = async () => {
        if (demoLoading) return;
        setDemoLoading(true);
        try {
            await fauxSignup();
        } catch (e: any) {
            const msg = e?.response?.data?.detail ?? e?.message ?? 'Something went wrong';
            if (Platform.OS === 'web') window.alert(msg);
            else Alert.alert('Error', msg);
        } finally {
            setDemoLoading(false);
        }
    };

    const handleSkip = async () => {
        if (skipLoading) return;
        setSkipLoading(true);
        try {
            await fauxSkipSignup();
            if (Platform.OS === 'web') {
                window.setTimeout(() => {
                    if (
                        typeof window !== 'undefined' &&
                        window.location?.pathname &&
                        !/\/(home|main)/i.test(window.location.pathname || '')
                    ) {
                        window.location.replace('/');
                    }
                }, 1500);
            }
        } catch (e: any) {
            const msg = e?.response?.data?.detail ?? e?.message ?? 'Something went wrong';
            if (Platform.OS === 'web') window.alert(`Skip failed: ${msg}`);
            else Alert.alert('Error', msg);
        } finally {
            setSkipLoading(false);
        }
    };

    const accentNow = SLIDES[active]?.accent ?? colors.foreground;

    const renderItem = useCallback(
        ({ item, index }: { item: Slide; index: number }) => (
            <SlidePane slide={item} isActive={index === active} width={containerWidth} />
        ),
        [active, containerWidth]
    );

    const isLast = active === SLIDES.length - 1;

    return (
        <View style={styles.root} onLayout={onLayout}>
            <View pointerEvents="none" style={StyleSheet.absoluteFill}>
                <BackdropGradient accent={accentNow} />
            </View>

            {/* Top bar — dots + (web) skip */}
            <View style={styles.topBar}>
                <View style={styles.dotsRow}>
                    {SLIDES.map((_, i) => (
                        <View
                            key={i}
                            style={[
                                styles.dot,
                                i === active && styles.dotActive,
                                i < active && styles.dotComplete,
                            ]}
                        />
                    ))}
                </View>
                {isWeb ? (
                    <TouchableOpacity
                        style={styles.skipPill}
                        activeOpacity={0.7}
                        onPress={handleSkip}
                        disabled={skipLoading}
                    >
                        {skipLoading ? (
                            <ActivityIndicator size="small" color={colors.textPrimary} />
                        ) : (
                            <>
                                <Text style={styles.skipPillText}>Skip</Text>
                                <Ionicons name="chevron-forward" size={13} color={colors.textPrimary} />
                            </>
                        )}
                    </TouchableOpacity>
                ) : (
                    <View style={{ width: 32 }} />
                )}
            </View>

            {/* Pager */}
            <FlatList
                ref={flatRef}
                horizontal
                pagingEnabled
                showsHorizontalScrollIndicator={false}
                data={SLIDES}
                keyExtractor={(s) => s.id}
                renderItem={renderItem}
                onMomentumScrollEnd={onMomentumScrollEnd}
                getItemLayout={(_, i) => ({
                    length: containerWidth,
                    offset: containerWidth * i,
                    index: i,
                })}
            />

            {/* Footer: Next / auth CTAs */}
            <View style={styles.footer}>
                {isLast ? (
                    <View style={{ gap: spacing.sm }}>
                        <TouchableOpacity
                            style={[styles.cta, styles.ctaPrimary]}
                            activeOpacity={0.85}
                            onPress={() => navigation.navigate('Signup')}
                        >
                            <Text style={styles.ctaPrimaryText}>Create account</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={[styles.cta, styles.ctaSecondary]}
                            activeOpacity={0.85}
                            onPress={() => navigation.navigate('Login')}
                        >
                            <Text style={styles.ctaSecondaryText}>Sign in</Text>
                        </TouchableOpacity>
                        {isWeb ? (
                            <TouchableOpacity
                                style={styles.demoButton}
                                activeOpacity={0.7}
                                onPress={handleTryNow}
                                disabled={demoLoading}
                            >
                                {demoLoading ? (
                                    <ActivityIndicator size="small" color={colors.textMuted} />
                                ) : (
                                    <Text style={styles.demoText}>Try it first — no account needed</Text>
                                )}
                            </TouchableOpacity>
                        ) : null}
                    </View>
                ) : (
                    <TouchableOpacity
                        style={[styles.cta, styles.ctaPrimary]}
                        activeOpacity={0.85}
                        onPress={goNext}
                    >
                        <Text style={styles.ctaPrimaryText}>Next</Text>
                        <Ionicons name="arrow-forward" size={15} color={colors.buttonText} />
                    </TouchableOpacity>
                )}
            </View>
        </View>
    );
}

/* ── Slide pane ───────────────────────────────────────────────────────── */

function SlidePane({
    slide, isActive, width,
}: {
    slide: Slide;
    isActive: boolean;
    width: number;
}) {
    const fade = useRef(new Animated.Value(0)).current;
    const tY = useRef(new Animated.Value(12)).current;

    useEffect(() => {
        if (isActive) {
            fade.setValue(0);
            tY.setValue(12);
            Animated.parallel([
                Animated.timing(fade, {
                    toValue: 1, duration: 420, delay: 120, useNativeDriver: true,
                    easing: Easing.out(Easing.cubic),
                }),
                Animated.timing(tY, {
                    toValue: 0, duration: 460, delay: 120, useNativeDriver: true,
                    easing: Easing.out(Easing.cubic),
                }),
            ]).start();
        } else {
            fade.setValue(0);
        }
    }, [isActive, fade, tY]);

    if (slide.custom === 'hero') {
        return (
            <View style={[paneStyles.pane, { width }]}>
                <Animated.View
                    style={[
                        paneStyles.heroWrap,
                        { opacity: fade, transform: [{ translateY: tY }] },
                    ]}
                >
                    <Text style={paneStyles.heroLogo}>max</Text>
                    <Text style={paneStyles.heroLine1}>Your AI looksmaxxing coach.</Text>
                    <Text style={paneStyles.heroLine2}>Personalized advice, every day.</Text>
                </Animated.View>
            </View>
        );
    }

    const Visual = slide.visual;

    return (
        <View style={[paneStyles.pane, { width }]}>
            <View style={paneStyles.visualWrap}>{Visual ? <Visual accent={slide.accent} /> : null}</View>
            <Animated.View
                style={[
                    paneStyles.copy,
                    { opacity: fade, transform: [{ translateY: tY }] },
                ]}
            >
                {slide.eyebrow ? (
                    <Text style={[paneStyles.eyebrow, { color: slide.accent }]}>{slide.eyebrow}</Text>
                ) : null}
                {slide.title ? <Text style={paneStyles.title}>{slide.title}</Text> : null}
                {slide.subtitle ? <Text style={paneStyles.subtitle}>{slide.subtitle}</Text> : null}
            </Animated.View>
        </View>
    );
}

/* ── Backdrop gradient (smooth accent transition) ─────────────────────── */

function BackdropGradient({ accent }: { accent: string }) {
    const prevAccent = useRef(accent);
    const fade = useRef(new Animated.Value(1)).current;
    useEffect(() => {
        if (prevAccent.current === accent) return;
        fade.setValue(0);
        Animated.timing(fade, {
            toValue: 1, duration: 420, useNativeDriver: true, easing: Easing.out(Easing.cubic),
        }).start();
        prevAccent.current = accent;
    }, [accent, fade]);
    return (
        <View style={StyleSheet.absoluteFill}>
            <View style={[StyleSheet.absoluteFill, { backgroundColor: colors.background }]} />
            <Animated.View style={[StyleSheet.absoluteFill, { opacity: fade }]}>
                <LinearGradient
                    colors={[
                        hexToRgba(accent, 0.18),
                        hexToRgba(accent, 0.08),
                        hexToRgba(accent, 0.0),
                    ]}
                    locations={[0, 0.5, 1]}
                    style={StyleSheet.absoluteFill}
                />
            </Animated.View>
        </View>
    );
}

function hexToRgba(hex: string, alpha: number): string {
    const h = (hex || '#888888').replace('#', '');
    const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const r = parseInt(full.slice(0, 2), 16);
    const g = parseInt(full.slice(2, 4), 16);
    const b = parseInt(full.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Per-slide visuals                                                      */
/* ─────────────────────────────────────────────────────────────────────── */

function PainVisual({ accent }: { accent: string }) {
    const fillAvg = useRef(new Animated.Value(0)).current;
    const fillTop = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        Animated.parallel([
            Animated.timing(fillAvg, { toValue: 0.4, duration: 900, delay: 400, useNativeDriver: false, easing: Easing.out(Easing.cubic) }),
            Animated.timing(fillTop, { toValue: 1, duration: 1100, delay: 600, useNativeDriver: false, easing: Easing.out(Easing.cubic) }),
        ]).start();
    }, [fillAvg, fillTop]);
    const widthAvg = fillAvg.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] });
    const widthTop = fillTop.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] });
    return (
        <View style={{ width: 220, gap: 18 }}>
            <View>
                <Text style={visuals.barLabel}>AVG MAN</Text>
                <View style={visuals.barTrack}>
                    <Animated.View style={[visuals.barFill, { width: widthAvg, backgroundColor: colors.textMuted }]} />
                </View>
            </View>
            <View>
                <Text style={[visuals.barLabel, { color: accent }]}>TOP 1%</Text>
                <View style={visuals.barTrack}>
                    <Animated.View style={[visuals.barFill, { width: widthTop, backgroundColor: accent }]} />
                </View>
            </View>
        </View>
    );
}

function ChatVisual({ accent }: { accent: string }) {
    const showAns = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        Animated.timing(showAns, {
            toValue: 1, duration: 400, delay: 1100, useNativeDriver: true, easing: Easing.out(Easing.cubic),
        }).start();
    }, [showAns]);
    return (
        <View style={{ width: 240, gap: 8 }}>
            <View style={[visuals.bubble, { alignSelf: 'flex-end', backgroundColor: colors.foreground }]}>
                <Text style={[visuals.bubbleText, { color: colors.buttonText }]}>
                    what should i use for hairline?
                </Text>
            </View>
            <Animated.View
                style={[
                    visuals.bubble,
                    {
                        alignSelf: 'flex-start',
                        backgroundColor: hexToRgba(accent, 0.14),
                        borderColor: hexToRgba(accent, 0.3),
                        opacity: showAns,
                    },
                ]}
            >
                <Text style={[visuals.bubbleText, { color: colors.foreground }]}>
                    minoxidil 5% foam · twice daily · pair with finasteride if you're committed.
                </Text>
            </Animated.View>
            <TypingDots accent={accent} hide={showAns} />
        </View>
    );
}

function TypingDots({ accent, hide }: { accent: string; hide: Animated.Value }) {
    const a = useRef(new Animated.Value(0.3)).current;
    const b = useRef(new Animated.Value(0.3)).current;
    const c = useRef(new Animated.Value(0.3)).current;
    useEffect(() => {
        const pulse = (v: Animated.Value, delay: number) =>
            Animated.loop(
                Animated.sequence([
                    Animated.timing(v, { toValue: 1, duration: 380, delay, useNativeDriver: true, easing: Easing.out(Easing.quad) }),
                    Animated.timing(v, { toValue: 0.3, duration: 380, useNativeDriver: true, easing: Easing.in(Easing.quad) }),
                ])
            ).start();
        pulse(a, 0); pulse(b, 120); pulse(c, 240);
    }, [a, b, c]);
    const opacity = hide.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });
    return (
        <Animated.View
            style={[
                visuals.bubble,
                {
                    alignSelf: 'flex-start',
                    flexDirection: 'row',
                    backgroundColor: hexToRgba(accent, 0.14),
                    borderColor: hexToRgba(accent, 0.3),
                    paddingVertical: 10,
                    gap: 5,
                    opacity,
                    position: 'absolute',
                    top: 56,
                },
            ]}
        >
            {[a, b, c].map((v, i) => (
                <Animated.View
                    key={i}
                    style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: accent, opacity: v }}
                />
            ))}
        </Animated.View>
    );
}

function StatsVisual({ accent }: { accent: string }) {
    const a = useCounter(5, 800, 200);
    const b = useCounter(67, 1100, 300);
    const c = useCounter(290, 1400, 400);
    return (
        <View style={visuals.statsRow}>
            <Stat value={a} label="MODULES" accent={accent} />
            <View style={[visuals.statDivider, { backgroundColor: hexToRgba(accent, 0.25) }]} />
            <Stat value={b} label="CHAPTERS" accent={accent} />
            <View style={[visuals.statDivider, { backgroundColor: hexToRgba(accent, 0.25) }]} />
            <Stat value={c} label="LESSONS" accent={accent} />
        </View>
    );
}

function useCounter(target: number, duration = 1000, delay = 0) {
    const [val, setVal] = useState(0);
    useEffect(() => {
        let raf = 0;
        let start: number | null = null;
        const handle = (t: number) => {
            if (start === null) start = t;
            const elapsed = t - start - delay;
            if (elapsed < 0) { raf = requestAnimationFrame(handle); return; }
            const k = Math.min(1, elapsed / duration);
            const eased = 1 - Math.pow(1 - k, 3);
            setVal(Math.round(target * eased));
            if (k < 1) raf = requestAnimationFrame(handle);
        };
        raf = requestAnimationFrame(handle);
        return () => cancelAnimationFrame(raf);
    }, [target, duration, delay]);
    return val;
}

function Stat({ value, label, accent }: { value: number; label: string; accent: string }) {
    return (
        <View style={visuals.stat}>
            <Text style={[visuals.statValue, { color: accent }]}>{value}</Text>
            <Text style={visuals.statLabel}>{label}</Text>
        </View>
    );
}

function PersonalVisual({ accent }: { accent: string }) {
    const spin = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        Animated.loop(
            Animated.timing(spin, { toValue: 1, duration: 12000, useNativeDriver: true, easing: Easing.linear })
        ).start();
    }, [spin]);
    const rotate = spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
    return (
        <View style={{ width: 200, height: 200, alignItems: 'center', justifyContent: 'center' }}>
            <Animated.View
                style={{
                    position: 'absolute',
                    width: 200, height: 200, borderRadius: 100,
                    transform: [{ rotate }],
                }}
            >
                <View style={[visuals.orbDot, { top: 0, left: '50%', marginLeft: -5, backgroundColor: accent }]} />
                <View style={[visuals.orbDot, { bottom: 0, left: '50%', marginLeft: -5, backgroundColor: accent, opacity: 0.4 }]} />
                <View style={[visuals.orbDot, { top: '50%', left: 0, marginTop: -5, backgroundColor: accent, opacity: 0.6 }]} />
                <View style={[visuals.orbDot, { top: '50%', right: 0, marginTop: -5, backgroundColor: accent, opacity: 0.7 }]} />
            </Animated.View>
            <View style={[visuals.disc, { backgroundColor: hexToRgba(accent, 0.18), width: 110, height: 110, borderRadius: 55 }]}>
                <Ionicons name="person-outline" size={44} color={accent} />
            </View>
        </View>
    );
}

function LoopVisual({ accent }: { accent: string }) {
    const slide = useRef(new Animated.Value(-40)).current;
    const fade = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        Animated.parallel([
            Animated.timing(slide, { toValue: 0, duration: 600, delay: 300, useNativeDriver: true, easing: Easing.out(Easing.cubic) }),
            Animated.timing(fade, { toValue: 1, duration: 500, delay: 350, useNativeDriver: true }),
        ]).start();
    }, [slide, fade]);
    return (
        <Animated.View
            style={[
                visuals.notif,
                {
                    transform: [{ translateY: slide }],
                    opacity: fade,
                    borderColor: hexToRgba(accent, 0.22),
                    backgroundColor: 'rgba(255,255,255,0.85)',
                },
            ]}
        >
            <View style={[visuals.notifIcon, { backgroundColor: hexToRgba(accent, 0.14) }]}>
                <Ionicons name="notifications" size={16} color={accent} />
            </View>
            <View style={{ flex: 1 }}>
                <Text style={visuals.notifTitle}>Max</Text>
                <Text style={visuals.notifBody}>
                    pm routine: tret 0.025% → ceramide cream → done in 90 sec.
                </Text>
            </View>
            <Text style={visuals.notifTime}>9:42 PM</Text>
        </Animated.View>
    );
}

function AscendVisual({ accent }: { accent: string }) {
    const lift = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        Animated.loop(
            Animated.sequence([
                Animated.timing(lift, { toValue: 1, duration: 1200, useNativeDriver: true, easing: Easing.inOut(Easing.quad) }),
                Animated.timing(lift, { toValue: 0, duration: 1200, useNativeDriver: true, easing: Easing.inOut(Easing.quad) }),
            ])
        ).start();
    }, [lift]);
    const tY = lift.interpolate({ inputRange: [0, 1], outputRange: [0, -10] });
    return (
        <Animated.View style={{ transform: [{ translateY: tY }] }}>
            <View style={[visuals.discOuter, { borderColor: hexToRgba(accent, 0.18) }]}>
                <View style={[visuals.discInner, { borderColor: hexToRgba(accent, 0.36) }]}>
                    <View style={[visuals.disc, { backgroundColor: hexToRgba(accent, 0.18) }]}>
                        <Ionicons name="arrow-up" size={48} color={accent} />
                    </View>
                </View>
            </View>
        </Animated.View>
    );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Styles                                                                 */
/* ─────────────────────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.background },

    topBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: spacing.lg,
        paddingTop: Platform.OS === 'web' ? spacing.lg : 56,
        paddingBottom: spacing.sm,
        zIndex: 2,
    },
    dotsRow: { flexDirection: 'row', gap: 6, alignItems: 'center' },
    dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.border },
    dotActive: { width: 24, backgroundColor: colors.foreground },
    dotComplete: { backgroundColor: colors.foreground },

    skipPill: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingVertical: 6,
        paddingHorizontal: 10,
        borderRadius: borderRadius.full,
        backgroundColor: 'rgba(255,255,255,0.65)',
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
    },
    skipPillText: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        color: colors.textPrimary,
        letterSpacing: 0.2,
    },

    footer: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
        paddingBottom: spacing.xl,
        zIndex: 2,
    },
    cta: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        paddingVertical: 14,
        borderRadius: borderRadius.full,
    },
    ctaPrimary: {
        backgroundColor: colors.foreground,
    },
    ctaPrimaryText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13.5,
        letterSpacing: 0.3,
        color: colors.buttonText,
    },
    ctaSecondary: {
        borderWidth: 1,
        borderColor: colors.foreground,
    },
    ctaSecondaryText: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 13.5,
        letterSpacing: 0.3,
        color: colors.foreground,
    },
    demoButton: {
        alignSelf: 'center',
        paddingVertical: 8,
        paddingHorizontal: 12,
    },
    demoText: {
        fontFamily: fonts.sansMedium,
        fontSize: 12,
        color: colors.textMuted,
        textDecorationLine: 'underline',
    },
});

const paneStyles = StyleSheet.create({
    pane: {
        flex: 1,
        paddingHorizontal: spacing.lg,
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: spacing.lg,
    },
    /* hero (kept) */
    heroWrap: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingBottom: spacing.xxxl,
    },
    heroLogo: {
        fontFamily: fonts.serif,
        fontSize: 92,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -3,
        lineHeight: 96,
        marginBottom: spacing.xl,
    },
    heroLine1: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        letterSpacing: -0.3,
        color: colors.foreground,
        textAlign: 'center',
        marginBottom: 6,
    },
    heroLine2: {
        fontFamily: fonts.sans,
        fontSize: 15,
        lineHeight: 22,
        color: colors.textSecondary,
        textAlign: 'center',
    },

    /* standard slide */
    visualWrap: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingTop: spacing.xl,
    },
    copy: {
        alignItems: 'center',
        paddingBottom: spacing.xl,
        maxWidth: 400,
    },
    eyebrow: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 11,
        letterSpacing: 1.8,
        marginBottom: 10,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 32,
        fontWeight: '400',
        letterSpacing: -0.6,
        lineHeight: 38,
        color: colors.foreground,
        textAlign: 'center',
        marginBottom: spacing.md,
    },
    subtitle: {
        fontFamily: fonts.sans,
        fontSize: 15,
        lineHeight: 22,
        color: colors.textSecondary,
        textAlign: 'center',
    },
});

const visuals = StyleSheet.create({
    discOuter: {
        width: 200, height: 200, borderRadius: 100,
        alignItems: 'center', justifyContent: 'center',
        borderWidth: 1,
    },
    discInner: {
        width: 150, height: 150, borderRadius: 75,
        alignItems: 'center', justifyContent: 'center',
        borderWidth: 1,
    },
    disc: {
        width: 100, height: 100, borderRadius: 50,
        alignItems: 'center', justifyContent: 'center',
    },
    barLabel: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 10,
        letterSpacing: 1.6,
        color: colors.textMuted,
        marginBottom: 6,
    },
    barTrack: {
        height: 6, borderRadius: 3,
        backgroundColor: colors.border,
        overflow: 'hidden',
    },
    barFill: {
        height: 6, borderRadius: 3,
    },
    bubble: {
        paddingHorizontal: 14,
        paddingVertical: 10,
        borderRadius: 16,
        maxWidth: 220,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: 'transparent',
    },
    bubbleText: {
        fontFamily: fonts.sans,
        fontSize: 13,
        lineHeight: 18,
    },
    statsRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
    },
    stat: { alignItems: 'center', paddingHorizontal: 14 },
    statValue: {
        fontFamily: fonts.serif,
        fontSize: 44,
        fontWeight: '400',
        letterSpacing: -1,
    },
    statLabel: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 9.5,
        letterSpacing: 1.6,
        color: colors.textMuted,
        marginTop: 4,
    },
    statDivider: { width: 1, height: 36 },
    orbDot: {
        position: 'absolute',
        width: 10, height: 10, borderRadius: 5,
    },
    notif: {
        width: 280,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        padding: 12,
        borderRadius: borderRadius.lg,
        borderWidth: 1,
        ...(Platform.OS === 'ios'
            ? { shadowColor: '#0A0A0B', shadowOpacity: 0.12, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } }
            : { elevation: 4 }),
    },
    notifIcon: {
        width: 32, height: 32, borderRadius: 8,
        alignItems: 'center', justifyContent: 'center',
    },
    notifTitle: {
        fontFamily: fonts.sansSemiBold,
        fontSize: 12,
        color: colors.foreground,
        letterSpacing: 0.2,
    },
    notifBody: {
        fontFamily: fonts.sans,
        fontSize: 12,
        color: colors.textSecondary,
        lineHeight: 16,
        marginTop: 1,
    },
    notifTime: {
        fontFamily: fonts.sans,
        fontSize: 10,
        color: colors.textMuted,
    },
});
