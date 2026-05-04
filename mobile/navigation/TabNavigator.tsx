import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Platform, View, Text, TouchableOpacity, Modal } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, shadows, fonts, borderRadius } from '../theme/dark';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { queryClient } from '../lib/queryClient';
import { prefetchMainTabData } from '../lib/prefetchMainTabData';
import { useAuth } from '../context/AuthContext';
import { SpotlightTourProvider, AttachStep, useSpotlightTour } from 'react-native-spotlight-tour';
import { TOUR_STEPS, TOUR_STEP } from '../features/mainTour/mainTourSteps';
import api from '../services/api';

import HomeScreen from '../screens/home/HomeScreen';
import MaxChatScreen from '../screens/chat/MaxChatScreen';
import ForumsHomeV2Screen from '../screens/forums/ForumsHomeV2Screen';
import ComingSoonOverlay from '../components/ComingSoonOverlay';
import SubforumThreadsV2Screen from '../screens/forums/SubforumThreadsV2Screen';
import ThreadV2Screen from '../screens/forums/ThreadV2Screen';
import NewThreadV2Screen from '../screens/forums/NewThreadV2Screen';
import ForumNotificationsV2Screen from '../screens/forums/ForumNotificationsV2Screen';
import MasterScheduleScreen from '../screens/courses/MasterScheduleScreen';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

function ScanPlaceholder() { return null; }

// Forums are gated behind a "coming soon" screen until the feature ships.
// The full forum stack (threads, posts, etc.) is preserved below — we just
// don't expose it from the tab. When ready, swap `ForumsComingSoon` for
// the original `ForumsHomeV2Screen` and the rest of the stack lights up.
function ForumsComingSoon() {
    return (
        <ComingSoonOverlay
            eyebrow="soon"
            title="forums"
            subtitle="we're cooking."
            iconName="people-outline"
        />
    );
}

function ForumsStack() {
    return (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
            <Stack.Screen name="ForumsHomeV2" component={ForumsComingSoon} />
            <Stack.Screen name="SubforumThreadsV2" component={SubforumThreadsV2Screen} />
            <Stack.Screen name="ThreadV2" component={ThreadV2Screen} />
            <Stack.Screen name="NewThreadV2" component={NewThreadV2Screen} />
            <Stack.Screen name="ForumNotificationsV2" component={ForumNotificationsV2Screen} />
        </Stack.Navigator>
    );
}

function PremiumGateModal({
    visible,
    onClose,
    onUpgrade,
}: {
    visible: boolean;
    onClose: () => void;
    onUpgrade: () => void;
}) {
    return (
        <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
            <TouchableOpacity style={modal.overlay} activeOpacity={1} onPress={onClose}>
                <TouchableOpacity style={modal.card} activeOpacity={1} onPress={() => {}}>
                    <View style={modal.iconWrap}>
                        <Ionicons name="scan-outline" size={28} color={colors.foreground} />
                    </View>
                    <Text style={modal.title}>Premium Feature</Text>
                    <Text style={modal.body}>
                        Face scans are only available for Premium subscribers. Upgrade to unlock daily AI-powered face analysis.
                    </Text>
                    <TouchableOpacity
                        style={modal.upgradeBtn}
                        onPress={onUpgrade}
                        activeOpacity={0.8}
                    >
                        <Text style={modal.upgradeBtnText}>Upgrade to Premium</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                        style={modal.dismissBtn}
                        onPress={onClose}
                        activeOpacity={0.65}
                    >
                        <Text style={modal.dismissText}>Not now</Text>
                    </TouchableOpacity>
                </TouchableOpacity>
            </TouchableOpacity>
        </Modal>
    );
}

const modal = StyleSheet.create({
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(0,0,0,0.4)',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 32,
    },
    card: {
        width: '100%',
        maxWidth: 320,
        backgroundColor: colors.background,
        borderRadius: borderRadius['2xl'],
        paddingVertical: 36,
        paddingHorizontal: 28,
        alignItems: 'center',
    },
    iconWrap: {
        width: 56,
        height: 56,
        borderRadius: 28,
        backgroundColor: colors.surface,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 20,
    },
    title: {
        fontFamily: fonts.serif,
        fontSize: 22,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -0.3,
        marginBottom: 10,
        textAlign: 'center',
    },
    body: {
        fontSize: 14,
        fontFamily: fonts.sans,
        color: colors.textSecondary,
        lineHeight: 21,
        textAlign: 'center',
        marginBottom: 28,
        letterSpacing: 0.1,
    },
    upgradeBtn: {
        width: '100%',
        height: 46,
        borderRadius: borderRadius.full,
        backgroundColor: colors.foreground,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 14,
    },
    upgradeBtnText: {
        fontSize: 14,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.buttonText,
        letterSpacing: 0.3,
    },
    dismissBtn: {
        paddingVertical: 6,
    },
    dismissText: {
        fontSize: 13,
        fontFamily: fonts.sansMedium,
        fontWeight: '500',
        color: colors.textMuted,
        letterSpacing: 0.2,
    },
});

function TourTrigger() {
    const { user, isPaid } = useAuth();
    const { start } = useSpotlightTour();
    const fired = useRef(false);

    useEffect(() => {
        if (fired.current) return;
        if (!isPaid) return;
        const ob = user?.onboarding as Record<string, unknown> | undefined;
        if (ob?.post_subscription_onboarding) return;
        if (ob?.main_app_tour_completed) return;

        fired.current = true;
        const id = setTimeout(() => start(), 600);
        return () => clearTimeout(id);
    }, [isPaid, user?.onboarding, start]);

    return null;
}

export default function TabNavigator() {
    const insets = useSafeAreaInsets();
    const { isPaid, isPremium, refreshUser } = useAuth();
    const [showGate, setShowGate] = useState(false);
    const navigation = useNavigation<any>();

    useEffect(() => {
        prefetchMainTabData(queryClient);
    }, []);

    const handleTourStop = useCallback(async () => {
        try {
            await api.completeMainAppTour();
            await refreshUser();
        } catch { /* non-fatal */ }
    }, [refreshUser]);

    return (
        <>
            <SpotlightTourProvider
                steps={TOUR_STEPS}
                overlayColor="black"
                overlayOpacity={0.65}
                nativeDriver={false}
                onBackdropPress="continue"
                onStop={handleTourStop}
            >
            <Tab.Navigator
                screenOptions={{
                    headerShown: false,
                    tabBarStyle: [
                        styles.tabBar,
                        {
                            height: 52 + insets.bottom,
                            paddingBottom: insets.bottom,
                        },
                    ],
                    tabBarActiveTintColor: '#000000',
                    tabBarInactiveTintColor: colors.textMuted,
                    tabBarLabelStyle: styles.tabLabel,
                }}
            >
                <Tab.Screen
                    name="Home"
                    component={HomeScreen}
                    options={{
                        tabBarIcon: ({ color }) => (
                            <Ionicons name="home-outline" size={22} color={color} />
                        ),
                    }}
                />
                <Tab.Screen
                    name="MasterScheduleTab"
                    component={MasterScheduleScreen}
                    options={{
                        title: 'Schedule',
                        tabBarLabel: 'Schedule',
                        tabBarIcon: ({ color }) => (
                            <AttachStep index={TOUR_STEP.SCHEDULE_TAB}>
                                <View style={styles.tourIconWrap}>
                                    <Ionicons name="calendar-outline" size={22} color={color} />
                                </View>
                            </AttachStep>
                        ),
                    }}
                />
                <Tab.Screen
                    name="ScanTab"
                    component={ScanPlaceholder}
                    listeners={({ navigation: nav }) => ({
                        tabPress: (e) => {
                            e.preventDefault();
                            if (!isPaid) {
                                nav.navigate('Payment');
                            } else if (!isPremium) {
                                setShowGate(true);
                            } else {
                                nav.navigate('FaceScan');
                            }
                        },
                    })}
                    options={{
                        title: 'Scan',
                        tabBarIcon: ({ color }) => (
                            <AttachStep index={TOUR_STEP.SCAN_TAB}>
                                <View style={styles.tourIconWrap}>
                                    <Ionicons name="scan-outline" size={22} color={color} />
                                </View>
                            </AttachStep>
                        ),
                    }}
                />
                <Tab.Screen
                    name="Chat"
                    component={MaxChatScreen}
                    options={{
                        tabBarIcon: ({ color }) => (
                            <AttachStep index={TOUR_STEP.CHAT_TAB}>
                                <View style={styles.tourIconWrap}>
                                    <Ionicons name="chatbubble-outline" size={22} color={color} />
                                </View>
                            </AttachStep>
                        ),
                    }}
                />
                <Tab.Screen
                    name="Forums"
                    component={ForumsStack}
                    options={{
                        tabBarIcon: ({ color }) => (
                            <AttachStep index={TOUR_STEP.FORUMS_TAB}>
                                <View style={styles.tourIconWrap}>
                                    <Ionicons name="people-outline" size={22} color={color} />
                                </View>
                            </AttachStep>
                        ),
                    }}
                />
            </Tab.Navigator>
            <TourTrigger />
            </SpotlightTourProvider>

            <PremiumGateModal
                visible={showGate}
                onClose={() => setShowGate(false)}
                onUpgrade={() => {
                    setShowGate(false);
                    navigation.navigate('ManageSubscription' as never);
                }}
            />
        </>
    );
}

const styles = StyleSheet.create({
    tabBar: {
        backgroundColor: 'rgba(255, 255, 255, 0.88)',
        borderTopWidth: 0,
        paddingTop: spacing.xs,
        ...shadows.lg,
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)' } : {}),
    } as any,
    tabLabel: {
        fontSize: 10,
        fontWeight: '500',
        letterSpacing: 0.2,
    },
    tourIconWrap: {
        width: 28,
        height: 28,
        alignItems: 'center' as const,
        justifyContent: 'center' as const,
    },
});
