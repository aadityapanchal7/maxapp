/**
 * Root Navigator - Auth flow control
 */

import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { ActivityIndicator, View } from 'react-native';
import { useAuth } from '../context/AuthContext';
import { colors } from '../theme/dark';

// Screens
import LoginScreen from '../screens/auth/LoginScreen';
import SignupScreen from '../screens/auth/SignupScreen';
import OnboardingScreen from '../screens/onboarding/OnboardingScreen';
import FeaturesIntroScreen from '../screens/onboarding/FeaturesIntroScreen';
import FaceScanScreen from '../screens/scan/FaceScanScreen';
import BlurredResultScreen from '../screens/scan/BlurredResultScreen';
import FullResultScreen from '../screens/scan/FullResultScreen';
import ScanDetailScreen from '../screens/scan/ScanDetailScreen';
import PaymentScreen from '../screens/payment/PaymentScreen';
import ProfileScreen from '../screens/profile/ProfileScreen';
import CourseListScreen from '../screens/courses/CourseListScreen';
import CourseDetailScreen from '../screens/courses/CourseDetailScreen';
import ChapterViewScreen from '../screens/courses/ChapterViewScreen';
import ChannelChatScreen from '../screens/forums/ChannelChatScreen';
import TabNavigator from './TabNavigator';
import AdminNavigator from './AdminNavigator';

const Stack = createNativeStackNavigator();

export function RootNavigator() {
    const { user, isLoading, isAuthenticated, isPaid } = useAuth();

    if (isLoading) {
        return (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background }}>
                <ActivityIndicator size="large" color={colors.primary} />
            </View>
        );
    }

    return (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
            {!isAuthenticated ? (
                // Auth screens
                <>
                    <Stack.Screen name="Login" component={LoginScreen} />
                    <Stack.Screen name="Signup" component={SignupScreen} />
                </>
            ) : user?.is_admin ? (
                // Admin Portal
                <>
                    <Stack.Screen name="Admin" component={AdminNavigator} />
                </>
            ) : !user?.onboarding?.completed ? (
                // Onboarding flow
                <>
                    <Stack.Screen name="Onboarding" component={OnboardingScreen} />
                    <Stack.Screen name="FeaturesIntro" component={FeaturesIntroScreen} />
                </>
            ) : !user?.first_scan_completed ? (
                // First scan flow (not paid yet)
                <>
                    <Stack.Screen name="FaceScan" component={FaceScanScreen} />
                    <Stack.Screen name="BlurredResult" component={BlurredResultScreen} />
                    <Stack.Screen name="Payment" component={PaymentScreen} />
                </>
            ) : !isPaid ? (
                // Blocked until payment
                <>
                    <Stack.Screen name="BlurredResult" component={BlurredResultScreen} />
                    <Stack.Screen name="Payment" component={PaymentScreen} />
                </>
            ) : (
                // Main app (paid user)
                <>
                    <Stack.Screen name="Main" component={TabNavigator} />
                    <Stack.Screen name="FaceScan" component={FaceScanScreen} />
                    <Stack.Screen name="FullResult" component={FullResultScreen} />
                    <Stack.Screen name="ScanDetail" component={ScanDetailScreen} />
                    <Stack.Screen name="Profile" component={ProfileScreen} />

                    {/* Course Screens */}
                    <Stack.Screen name="CourseList" component={CourseListScreen} />
                    <Stack.Screen name="CourseDetail" component={CourseDetailScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="ChapterView" component={ChapterViewScreen} options={{ headerShown: false }} />
                </>
            )}
        </Stack.Navigator>
    );
}

export default RootNavigator;

