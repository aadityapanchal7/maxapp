import React, { useState, useRef } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    FlatList,
    Dimensions,
    NativeSyntheticEvent,
    NativeScrollEvent,
    Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, typography, shadows } from '../../theme/dark';

const isWeb = Platform.OS === 'web';
const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const WEB_MAX_SLIDE_WIDTH = 440;
const SLIDE_WIDTH = isWeb ? Math.min(SCREEN_WIDTH, WEB_MAX_SLIDE_WIDTH) : SCREEN_WIDTH;
const SLIDE_HEIGHT = SCREEN_HEIGHT * 0.72;

const SLIDES = [
    {
        id: 'hero',
        type: 'hero',
        title: 'max',
        line1: 'Your AI looksmaxxing coach.',
        line2: 'Personalized advice, texted daily.',
    },
    {
        id: 'coaching',
        type: 'coaching',
        label: 'HOW IT FEELS',
        title: 'Coaching that comes to you',
        description: 'Max texts you personalized advice throughout the day. Onboard in the app, then get real guidance straight to your messages.',
        chatPreview: [
            { from: 'max', text: 'Good morning. Time for your skincare routine — cleanser, vitamin C serum, then SPF 50. Don\'t skip the sunscreen.', time: '8:02 AM' },
            { from: 'user', text: 'Done. What about my hair?', time: '8:14 AM' },
            { from: 'max', text: 'Your hair type responds well to less washing. Skip today, use dry texture spray instead. Trust the process.', time: '' },
            { from: 'max', text: 'Also — posture check. Shoulders back, chin slightly up. People notice instantly.', time: '8:15 AM' },
        ],
    },
];

export default function LandingScreen() {
    const navigation = useNavigation<any>();
    const [currentIndex, setCurrentIndex] = useState(0);
    const flatListRef = useRef<FlatList>(null);

    const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
        const index = Math.min(
            Math.round(e.nativeEvent.contentOffset.x / SLIDE_WIDTH),
            SLIDES.length - 1
        );
        setCurrentIndex(index);
    };

    const goNext = () => {
        if (currentIndex < SLIDES.length - 1) {
            flatListRef.current?.scrollToIndex({ index: currentIndex + 1, animated: true });
        }
    };

    const renderSlide = ({ item }: { item: typeof SLIDES[0] }) => {
        if (item.type === 'hero') {
            return (
                <View style={styles.slide}>
                    <View style={styles.heroContent}>
                        <Text style={styles.heroLogo}>{item.title}</Text>
                        <Text style={styles.heroLine1}>{item.line1}</Text>
                        <Text style={styles.heroLine2}>{item.line2}</Text>
                    </View>
                    <TouchableOpacity style={styles.arrowDown} onPress={goNext} activeOpacity={0.7}>
                        <Ionicons name="chevron-down" size={28} color={colors.textMuted} />
                    </TouchableOpacity>
                </View>
            );
        }

        if (item.type === 'coaching') {
            return (
                <View style={styles.slide}>
                    <View style={styles.coachingContent}>
                        <Text style={styles.coachingLabel}>{item.label}</Text>
                        <Text style={styles.coachingTitle}>{item.title}</Text>
                        <Text style={styles.coachingDescription}>{item.description}</Text>
                        <View style={styles.chatPreview}>
                            {item.chatPreview!.map((msg, i) => (
                                <View
                                    key={i}
                                    style={[
                                        styles.chatBubble,
                                        msg.from === 'user' ? styles.chatBubbleUser : styles.chatBubbleMax,
                                    ]}
                                >
                                    <Text style={[styles.chatBubbleText, msg.from === 'user' && styles.chatBubbleTextUser]}>
                                        {msg.text}
                                    </Text>
                                    {msg.time ? <Text style={styles.chatTime}>{msg.time}</Text> : null}
                                </View>
                            ))}
                        </View>
                    </View>
                </View>
            );
        }

        return null;
    };

    return (
        <View style={styles.container}>
            <View style={styles.carouselWrap}>
                <FlatList
                    ref={flatListRef}
                    data={SLIDES}
                    renderItem={renderSlide}
                    keyExtractor={(item) => item.id}
                    horizontal
                    pagingEnabled
                    showsHorizontalScrollIndicator={false}
                    onScroll={onScroll}
                    scrollEventThrottle={16}
                    getItemLayout={(_, index) => ({
                        length: SLIDE_WIDTH,
                        offset: SLIDE_WIDTH * index,
                        index,
                    })}
                />
            </View>

            <View style={styles.footer}>
                <View style={styles.dots}>
                    {SLIDES.map((_, i) => (
                        <View
                            key={i}
                            style={[styles.dot, i === currentIndex && styles.dotActive]}
                        />
                    ))}
                </View>

                {currentIndex === SLIDES.length - 1 ? (
                    <View style={styles.actions}>
                        <TouchableOpacity
                            style={styles.primaryButton}
                            activeOpacity={0.85}
                            onPress={() => navigation.navigate('Login')}
                        >
                            <Text style={styles.primaryText}>Sign In</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={styles.secondaryButton}
                            activeOpacity={0.85}
                            onPress={() => navigation.navigate('Signup')}
                        >
                            <Text style={styles.secondaryText}>Create account</Text>
                        </TouchableOpacity>
                    </View>
                ) : (
                    <TouchableOpacity style={styles.nextButton} onPress={goNext} activeOpacity={0.85}>
                        <Text style={styles.nextButtonText}>Next</Text>
                        <Ionicons name="arrow-forward" size={18} color={colors.buttonText} />
                    </TouchableOpacity>
                )}
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: colors.background,
        ...(isWeb && { alignItems: 'center' as const }),
    },
    carouselWrap: {
        flex: 1,
        ...(isWeb && { width: '100%', maxWidth: WEB_MAX_SLIDE_WIDTH }),
    },
    slide: {
        width: SLIDE_WIDTH,
        minHeight: SLIDE_HEIGHT,
        paddingHorizontal: spacing.xl,
        paddingTop: 80,
        paddingBottom: spacing.xl,
        justifyContent: 'space-between',
    },
    heroContent: {
        alignItems: 'center',
        flex: 1,
        justifyContent: 'center',
    },
    heroLogo: {
        fontSize: 48,
        fontWeight: '700',
        color: colors.foreground,
        letterSpacing: -1,
        marginBottom: spacing.lg,
    },
    heroLine1: {
        fontSize: 17,
        color: colors.textPrimary,
        marginBottom: spacing.xs,
        textAlign: 'center',
    },
    heroLine2: {
        fontSize: 17,
        color: colors.textSecondary,
        textAlign: 'center',
    },
    arrowDown: {
        alignSelf: 'center',
        padding: spacing.sm,
        ...(isWeb && { cursor: 'pointer' as const }),
    },
    coachingContent: {
        flex: 1,
    },
    coachingLabel: {
        fontSize: 12,
        fontWeight: '600',
        color: colors.textMuted,
        letterSpacing: 1.5,
        marginBottom: spacing.sm,
    },
    coachingTitle: {
        fontSize: 28,
        fontWeight: '700',
        color: colors.foreground,
        letterSpacing: -0.5,
        marginBottom: spacing.md,
        lineHeight: 34,
    },
    coachingDescription: {
        fontSize: 15,
        color: colors.textSecondary,
        lineHeight: 22,
        marginBottom: spacing.xl,
    },
    chatPreview: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.lg,
        padding: spacing.md,
        gap: spacing.sm,
        ...shadows.sm,
    },
    chatBubble: {
        maxWidth: '88%',
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.lg,
        alignSelf: 'flex-start',
    },
    chatBubbleMax: {
        backgroundColor: colors.card,
        borderBottomLeftRadius: 4,
    },
    chatBubbleUser: {
        alignSelf: 'flex-end',
        backgroundColor: colors.foreground,
        borderBottomRightRadius: 4,
    },
    chatBubbleText: {
        fontSize: 14,
        color: colors.textPrimary,
        lineHeight: 20,
    },
    chatBubbleTextUser: {
        color: colors.buttonText,
    },
    chatTime: {
        fontSize: 11,
        color: colors.textMuted,
        marginTop: 4,
    },
    footer: {
        paddingHorizontal: spacing.lg,
        paddingBottom: spacing.xxl + 24,
        paddingTop: spacing.lg,
        gap: spacing.lg,
        ...(isWeb && { width: '100%', maxWidth: WEB_MAX_SLIDE_WIDTH }),
    },
    dots: {
        flexDirection: 'row',
        justifyContent: 'center',
        gap: spacing.sm,
    },
    dot: {
        width: 8,
        height: 8,
        borderRadius: 4,
        backgroundColor: colors.borderLight,
    },
    dotActive: {
        backgroundColor: colors.foreground,
        width: 24,
    },
    actions: {
        gap: spacing.md,
    },
    primaryButton: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.md,
        alignItems: 'center',
        ...shadows.md,
        ...(isWeb && { cursor: 'pointer' as const }),
    },
    primaryText: {
        ...typography.button,
    },
    secondaryButton: {
        borderRadius: borderRadius.full,
        paddingVertical: spacing.md,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
        ...(isWeb && { cursor: 'pointer' as const }),
    },
    secondaryText: {
        fontSize: 14,
        color: colors.textSecondary,
        fontWeight: '500',
    },
    nextButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.full,
        paddingVertical: spacing.md,
        ...shadows.md,
        ...(isWeb && { cursor: 'pointer' as const }),
    },
    nextButtonText: {
        ...typography.button,
    },
});
