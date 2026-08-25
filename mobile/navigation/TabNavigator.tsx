import React, { useEffect } from 'react';
import { StyleSheet, Platform, View, TouchableOpacity } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { LiquidGlassFill } from '../components/glass/LiquidGlass';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, spacing, shadows } from '../theme/dark';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { queryClient } from '../lib/queryClient';
import { prefetchMainTabData } from '../lib/prefetchMainTabData';
import HomeScreen from '../screens/home/HomeScreen';
import MaxChatScreen from '../screens/chat/MaxChatScreen';
import ForumsHomeV2Screen from '../screens/forums/ForumsHomeV2Screen';
import ComingSoonOverlay from '../components/ComingSoonOverlay';
import SubforumThreadsV2Screen from '../screens/forums/SubforumThreadsV2Screen';
import ThreadV2Screen from '../screens/forums/ThreadV2Screen';
import NewThreadV2Screen from '../screens/forums/NewThreadV2Screen';
import ForumNotificationsV2Screen from '../screens/forums/ForumNotificationsV2Screen';
import DayPlannerScreen from '../screens/profile/DayPlannerScreen';
import MarketplaceScreen from '../screens/marketplace/MarketplaceScreen';
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

// The first-run walkthrough (features/mainTour) is rendered by HomeScreen —
// an anchor-free overlay, so this navigator carries no tour machinery anymore.

export default function TabNavigator() {
    const insets = useSafeAreaInsets();

    useEffect(() => {
        prefetchMainTabData(queryClient);
    }, []);

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
