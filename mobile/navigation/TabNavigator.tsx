import React, { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { StyleSheet, Platform, View, Text, TouchableOpacity, Modal } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { LiquidGlassFill } from '../components/glass/LiquidGlass';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, spacing, shadows, fonts, borderRadius } from '../theme/dark';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { queryClient } from '../lib/queryClient';
import { prefetchMainTabData } from '../lib/prefetchMainTabData';
import { useAuth } from '../context/AuthContext';
// Deep import (pinned v4.0.0): the public API doesn't surface the live `spot`,
// which the safety watchdog needs to detect a zero-spot trap.
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
import DayPlannerScreen from '../screens/profile/DayPlannerScreen';
import MarketplaceScreen from '../screens/marketplace/MarketplaceScreen';
import YouScreen from '../screens/you/YouScreen';
import TodayV2Screen from '../screens/today/TodayScreen';
import { useFlag } from '../constants/featureFlags';
import { getRestoredTab, pickInitialTab } from '../lib/navState';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

function ScanPlaceholder() { return null; }

function ScanCenterButton() {
    const scanNav = useNavigation<any>();
    return (
        <TouchableOpacity
            onPress={() => scanNav.navigate('FaceScan')}
            style={scanBtnStyles.touch}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Scan"
            testID="tab-scan"
        >
            {/* Same canonical liquid-glass optics as the Planner top-bar buttons:
                outer carrier holds the float shadow (un-clipped), inner clips the
                LiquidGlassFill material. */}
            <View style={scanBtnStyles.shadowWrap}>
                <View style={scanBtnStyles.circleWrap}>
                    <LiquidGlassFill idSuffix="scanTab" />
                    <Ionicons name="scan" size={22} color={colors.foreground} />
                </View>
            </View>
        </TouchableOpacity>
    );
}

const scanBtnStyles = StyleSheet.create({
    touch: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    // Outer carrier: casts the soft warm float shadow (matches the Planner glass
    // buttons). NOT clipped — overflow stays visible.
    // Stronger float shadow than the Planner buttons — the scan button sits on
    // the near-white tab bar, so it needs a deeper drop shadow to read as a
    // distinct glass disc instead of blending in.
    shadowWrap: {
        width: 50,
        height: 50,
        borderRadius: 25,
        backgroundColor: 'transparent',
        shadowColor: '#1C1E26',
        shadowOpacity: 0.30,
        shadowRadius: 16,
        shadowOffset: { width: 0, height: 8 },
        elevation: 10,
        ...(Platform.OS === 'ios' ? { borderCurve: 'continuous' as any } : {}),
    },
    // Inner: clips the LiquidGlassFill material. More body + a crisper rim than the
    // Planner buttons so it stays visible on the white bar while still reading as glass.
    circleWrap: {
        width: 50,
        height: 50,
        borderRadius: 25,
        overflow: 'hidden',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(255,255,255,0.42)',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.95)',
        ...(Platform.OS === 'ios' ? { borderCurve: 'continuous' as any } : {}),
    },
    // Bright top edge of the frosted tab bar.
    tabTopRim: {
        position: 'absolute', top: 0, left: 0, right: 0,
        height: StyleSheet.hairlineWidth,
        backgroundColor: 'rgba(255,255,255,0.85)',
    },
});

// Frosted-glass tab bar background — real blur + milky fill + soft top sheen
// and a crisp bright top rim, matching the glass scan button.
function TabBarFrost() {
    return (
        // Purely decorative — must never intercept touches meant for the bar
        // buttons or the screen content above it.
        <View style={StyleSheet.absoluteFill} pointerEvents="none">
            <BlurView
                intensity={Platform.OS === 'ios' ? 40 : 60}
                tint="extraLight"
                style={StyleSheet.absoluteFill}
                pointerEvents="none"
                experimentalBlurMethod={Platform.OS === 'android' ? 'dimezisBlurView' : undefined}
            />
            {/* Milky frosted fill */}
            <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(255,255,255,0.62)' }]} pointerEvents="none" />
            {/* Soft top-down sheen */}
            <LinearGradient
                colors={['rgba(255,255,255,0.55)', 'rgba(255,255,255,0)']}
                locations={[0, 0.4]}
                style={StyleSheet.absoluteFill}
                pointerEvents="none"
            />
            {/* Crisp bright top rim — the glass edge */}
            <View style={scanBtnStyles.tabTopRim} pointerEvents="none" />
        </View>
    );
}

// Render the week planner as a tab root (no back button — it isn't pushed).
function PlannerTab() {
    return <DayPlannerScreen embedded />;
}

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

// The first-run walkthrough (features/mainTour) is rendered by HomeScreen —
// an anchor-free overlay, so this navigator carries no tour machinery anymore.

// The 4-tab pivot nav (spec 3.1): Today / Explore / Coach / You. No Forums
// registration, no ScanTab remnant, no duplicate Planner tab - the week
// editor lives under You (ONE source of truth). Route names that other code
// navigates to are preserved: MasterScheduleTab, Explore, Chat.
function NewTabNavigator({ insets }: { insets: { bottom: number } }) {
    // Today v2 ships behind its own flag; the 1457-line MasterScheduleScreen
    // stays the fallback so newNav can ship without todayV2.
    const todayV2 = useFlag('todayV2');
    const TodayComponent = todayV2 ? TodayV2Screen : MasterScheduleScreen;
    return (
        <Tab.Navigator
            // Restore the tab the user left (lib/navState); falls back to the
            // first tab when there's nothing valid to restore.
            initialRouteName={pickInitialTab(getRestoredTab(), [
                'MasterScheduleTab', 'Explore', 'ScanCenter', 'Chat', 'YouTab',
            ])}
            screenOptions={{
                headerShown: false,
                tabBarBackground: () => <TabBarFrost />,
                tabBarStyle: [
                    styles.tabBarGlass,
                    { height: 52 + insets.bottom, paddingBottom: insets.bottom, overflow: 'visible' as any },
                ],
                tabBarActiveTintColor: colors.foreground,
                tabBarInactiveTintColor: colors.textMuted,
                tabBarLabelStyle: styles.tabLabel,
            }}
        >
            <Tab.Screen
                name="MasterScheduleTab"
                component={TodayComponent}
                options={{
                    title: 'Today',
                    tabBarLabel: 'Today',
                    tabBarIcon: ({ color }) => (
                        <Ionicons name="today-outline" size={22} color={color} />
                    ),
                }}
            />
            <Tab.Screen
                name="Explore"
                component={MarketplaceScreen}
                options={{
                    title: 'Explore',
                    tabBarLabel: 'Explore',
                    tabBarIcon: ({ color }) => (
                        <Ionicons name="compass-outline" size={22} color={color} />
                    ),
                }}
            />
            <Tab.Screen
                name="ScanCenter"
                component={ScanPlaceholder}
                options={{
                    tabBarLabel: 'Scan',
                    tabBarButton: () => <ScanCenterButton />,
                }}
            />
            <Tab.Screen
                name="Chat"
                component={MaxChatScreen}
                options={{
                    title: 'Coach',
                    tabBarLabel: 'Coach',
                    tabBarIcon: ({ color }) => (
                        <Ionicons name="chatbubble-outline" size={22} color={color} />
                    ),
                }}
            />
            <Tab.Screen
                name="YouTab"
                component={YouScreen}
                options={{
                    title: 'You',
                    tabBarLabel: 'You',
                    tabBarIcon: ({ color }) => (
                        <Ionicons name="person-outline" size={22} color={color} />
                    ),
                }}
            />
        </Tab.Navigator>
    );
}

export default function TabNavigator() {
    const insets = useSafeAreaInsets();
    const { isPaid, isPremium, refreshUser } = useAuth();
    const [showGate, setShowGate] = useState(false);
    const navigation = useNavigation<any>();
    const newNav = useFlag('newNav');

    useEffect(() => {
        prefetchMainTabData(queryClient);
    }, []);

    if (newNav) {
        return <NewTabNavigator insets={insets} />;
    }

    return (
        <>
            <Tab.Navigator
                // Restore the tab the user left (lib/navState); falls back to
                // Home when there's nothing valid to restore.
                initialRouteName={pickInitialTab(getRestoredTab(), [
                    'Home', 'MasterScheduleTab', 'ScanCenter', 'Explore', 'Chat', 'Forums',
                ])}
                screenOptions={{
                    headerShown: false,
                    tabBarBackground: () => <TabBarFrost />,
                    tabBarStyle: [
                        styles.tabBar,
                        {
                            height: 52 + insets.bottom,
                            paddingBottom: insets.bottom,
                            overflow: 'visible' as any,
                        },
                    ],
                    tabBarActiveTintColor: colors.foreground,
                    tabBarInactiveTintColor: colors.textMuted,
                    tabBarLabelStyle: styles.tabLabel,
                }}
            >
                <Tab.Screen
                    name="Home"
                    component={HomeScreen}
                    options={{
                        title: 'Home',
                        tabBarLabel: 'Home',
                        tabBarButtonTestID: 'tab-home',
                        tabBarIcon: ({ color }) => (
                            <Ionicons name="home-outline" size={22} color={color} />
                        ),
                    }}
                />
                {/* Planner replaces the old Schedule tab — the day-planner
                    timeline is now the second tab. Route name stays
                    'MasterScheduleTab' so existing navigate() calls and the
                    onboarding tour step keep working. */}
                <Tab.Screen
                    name="MasterScheduleTab"
                    component={PlannerTab}
                    options={{
                        title: 'Planner',
                        tabBarLabel: 'Planner',
                        tabBarButtonTestID: 'tab-planner',
                        tabBarIcon: ({ color }) => (
                            <Ionicons name="map-outline" size={22} color={color} />
                        ),
                    }}
                />
                <Tab.Screen
                    name="ScanCenter"
                    component={ScanPlaceholder}
                    options={{
                        tabBarLabel: 'Scan',
                        tabBarButton: () => <ScanCenterButton />,
                    }}
                />
                <Tab.Screen
                    name="Explore"
                    component={MarketplaceScreen}
                    options={{
                        title: 'Explore',
                        tabBarLabel: 'Explore',
                        tabBarButtonTestID: 'tab-explore',
                        tabBarIcon: ({ color }) => (
                            <Ionicons name="compass-outline" size={22} color={color} />
                        ),
                    }}
                />
                <Tab.Screen
                    name="Chat"
                    component={MaxChatScreen}
                    options={{
                        tabBarButtonTestID: 'tab-chat',
                        tabBarIcon: ({ color }) => (
                            <Ionicons name="chatbubble-outline" size={22} color={color} />
                        ),
                    }}
                />
                {/* Forums tab hidden from the bar (permanent "coming soon" dead-end).
                    Route stays registered so deep links / the forum stack still work —
                    tabBarButton renders null so no tab button shows. */}
                <Tab.Screen
                    name="Forums"
                    component={ForumsStack}
                    options={{
                        tabBarButton: () => null,
                        tabBarItemStyle: { display: 'none' },
                    }}
                />
            </Tab.Navigator>

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
        backgroundColor: 'transparent',
        borderTopWidth: 0,
        paddingTop: spacing.xs,
        ...shadows.lg,
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)' } : {}),
    } as any,
    // Frosted glass tab bar — fill/blur come from <TabBarFrost/> behind it.
    tabBarGlass: {
        backgroundColor: 'transparent',
        borderTopWidth: 0,
        paddingTop: spacing.xs,
        overflow: 'visible',
        ...shadows.lg,
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)' } : {}),
    } as any,
    tabLabel: {
        fontSize: 10,
        fontWeight: '500',
        letterSpacing: 0.2,
    },
});
