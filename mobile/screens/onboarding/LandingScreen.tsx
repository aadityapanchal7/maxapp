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
    ActivityIndicator,
    Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, typography, fonts } from '../../theme/dark';
import { useAuth } from '../../context/AuthContext';

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
    const { fauxSignup } = useAuth();
    const [currentIndex, setCurrentIndex] = useState(0);
    const [demoLoading, setDemoLoading] = useState(false);
    const flatListRef = useRef<FlatList>(null);

    const handleTryNow = async () => {
        if (demoLoading) return;
        setDemoLoading(true);
        try {
            await fauxSignup();
        } catch (e: any) {
            const msg = e?.response?.data?.detail ?? e?.message ?? 'Something went wrong';
            if (Platform.OS === 'web') {
                window.alert(msg);
            } else {
                Alert.alert('Error', msg);
            }
        } finally {
            setDemoLoading(false);
        }
    };

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
                    </View>
                ) : (
                    <View style={styles.actions}>
                        <TouchableOpacity style={styles.nextButton} onPress={goNext} activeOpacity={0.85}>
                            <Text style={styles.nextButtonText}>Next</Text>
                            <Ionicons name="arrow-forward" size={18} color={colors.buttonText} />
                        </TouchableOpacity>
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
                    </View>
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
        paddingHorizontal: spacing.xl + spacing.sm,
        paddingTop: 96,
        paddingBottom: spacing.xl + spacing.md,
        justifyContent: 'space-between',
    },
    heroContent: {
        alignItems: 'center',
        flex: 1,
        justifyContent: 'center',
        paddingVertical: spacing.lg,
    },
    heroLogo: {
        fontFamily: fonts.serif,
        fontSize: 62,
        fontWeight: '300',
        color: colors.textPrimary,
        letterSpacing: -2,
        marginBottom: spacing.xl,
        lineHeight: 68,
    },
    heroLine1: {
        fontSize: 16,
        color: colors.textSecondary,
        marginBottom: spacing.sm,
        textAlign: 'center',
        letterSpacing: 0.2,
        lineHeight: 24,
    },
    heroLine2: {
        fontSize: 16,
        color: colors.textMuted,
        textAlign: 'center',
        letterSpacing: 0.2,
        lineHeight: 24,
    },
    coachingContent: {
        flex: 1,
    },
    coachingLabel: {
        fontSize: 11,
        fontWeight: '500',
        color: colors.textMuted,
        letterSpacing: 2,
        marginBottom: spacing.md,
    },
    coachingTitle: {
        fontFamily: fonts.serif,
        fontSize: 26,
        fontWeight: '400',
        color: colors.textPrimary,
        letterSpacing: -0.4,
        marginBottom: spacing.lg,
        lineHeight: 32,
    },
    coachingDescription: {
        fontSize: 15,
        color: colors.textSecondary,
        lineHeight: 24,
        marginBottom: spacing.xl + spacing.sm,
    },
    chatPreview: {
        backgroundColor: colors.surface,
        borderRadius: borderRadius.md,
        padding: spacing.lg,
        gap: spacing.md,
        borderWidth: 1,
        borderColor: colors.border,
    },
    chatBubble: {
        maxWidth: '90%',
        paddingVertical: spacing.sm + 2,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.sm,
        alignSelf: 'flex-start',
        borderWidth: 1,
    },
    chatBubbleMax: {
        backgroundColor: colors.card,
        borderColor: colors.border,
        borderBottomLeftRadius: borderRadius.sm,
    },
    chatBubbleUser: {
        alignSelf: 'flex-end',
        backgroundColor: colors.background,
        borderColor: colors.border,
        borderBottomRightRadius: borderRadius.sm,
    },
    chatBubbleText: {
        fontSize: 14,
        color: colors.textPrimary,
        lineHeight: 21,
    },
    chatBubbleTextUser: {
        color: colors.textPrimary,
    },
    chatTime: {
        fontSize: 11,
        color: colors.textMuted,
        marginTop: 4,
    },
    footer: {
        paddingHorizontal: spacing.xl,
        paddingBottom: spacing.xxxl + spacing.md,
        paddingTop: spacing.xl,
        gap: spacing.xl,
        ...(isWeb && { width: '100%', maxWidth: WEB_MAX_SLIDE_WIDTH }),
    },
    dots: {
        flexDirection: 'row',
        justifyContent: 'center',
        alignItems: 'center',
        gap: 10,
    },
    dot: {
        width: 5,
        height: 5,
        borderRadius: 2.5,
        backgroundColor: colors.border,
    },
    dotActive: {
        backgroundColor: colors.textPrimary,
        width: 18,
        height: 4,
        borderRadius: 2,
    },
    actions: {
        gap: spacing.sm,
    },
    primaryButton: {
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.sm,
        paddingVertical: spacing.sm + 6,
        paddingHorizontal: spacing.lg,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.foreground,
        ...(isWeb && { cursor: 'pointer' as const }),
    },
    primaryText: {
        ...typography.button,
        fontSize: 13,
        letterSpacing: 0.8,
    },
    secondaryButton: {
        borderRadius: borderRadius.sm,
        paddingVertical: spacing.sm + 6,
        paddingHorizontal: spacing.lg,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: 'transparent',
        ...(isWeb && { cursor: 'pointer' as const }),
    },
    secondaryText: {
        fontSize: 13,
        color: colors.textSecondary,
        fontWeight: '500',
        letterSpacing: 0.5,
    },
    nextButton: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.sm,
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.sm,
        paddingVertical: spacing.sm + 6,
        paddingHorizontal: spacing.lg,
        borderWidth: 1,
        borderColor: colors.foreground,
        ...(isWeb && { cursor: 'pointer' as const }),
    },
    nextButtonText: {
        ...typography.button,
        fontSize: 13,
        letterSpacing: 0.8,
    },
    demoButton: {
        paddingVertical: spacing.sm + 4,
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 40,
    },
    demoText: {
        fontSize: 13,
        color: colors.textMuted,
        fontWeight: '400',
        letterSpacing: 0.2,
        textDecorationLine: 'underline',
    },
});
