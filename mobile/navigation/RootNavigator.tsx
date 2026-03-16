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
import PaymentThankYouScreen from '../screens/payment/PaymentThankYouScreen';
import ProfileScreen from '../screens/profile/ProfileScreen';
import EditPersonalScreen from '../screens/profile/EditPersonalScreen';
import ProgressArchiveScreen from '../screens/profile/ProgressArchiveScreen';
import CourseListScreen from '../screens/courses/CourseListScreen';
import CourseDetailScreen from '../screens/courses/CourseDetailScreen';
import ChapterViewScreen from '../screens/courses/ChapterViewScreen';
import ScheduleScreen from '../screens/courses/ScheduleScreen';
import ChannelChatScreen from '../screens/forums/ChannelChatScreen';
import MaxxDetailScreen from '../screens/courses/MaxxDetailScreen';
import TabNavigator from './TabNavigator';
import LandingScreen from '../screens/onboarding/LandingScreen';
import AdminNavigator from './AdminNavigator';

const Stack = createNativeStackNavigator();

export function RootNavigator() {
    const { user, isLoading, isAuthenticated, isPaid } = useAuth();

    if (isLoading) {
        return (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background }}>
                <ActivityIndicator size="large" color={colors.accent} />
            </View>
        );
    }

    const onboardingCompleted = user?.onboarding?.completed === true;
    const initialRoute = !isAuthenticated
        ? 'Landing'
        : user?.is_admin
            ? 'Admin'
            : !onboardingCompleted
                ? 'Onboarding'
                : !isPaid
                    ? 'Payment'
                    : 'Main';

    return (
        <Stack.Navigator
            key={isAuthenticated ? 'auth' : 'guest'}
            screenOptions={{ headerShown: false }}
            initialRouteName={initialRoute}
        >
            {!isAuthenticated ? (
                // Pre-auth: landing -> sign in (login/signup)
                <>
                    <Stack.Screen name="Landing" component={LandingScreen} />
                    <Stack.Screen name="Login" component={LoginScreen} />
                    <Stack.Screen name="Signup" component={SignupScreen} />
                </>
            ) : !onboardingCompleted ? (
                // Post-auth: onboarding (goals, profile, face scan) -> payment -> main
                <>
                    <Stack.Screen name="Onboarding" component={OnboardingScreen} />
                    <Stack.Screen name="FeaturesIntro" component={FeaturesIntroScreen} />
                    <Stack.Screen name="FaceScan" component={FaceScanScreen} />
                    <Stack.Screen name="BlurredResult" component={BlurredResultScreen} />
                    <Stack.Screen name="FullResult" component={FullResultScreen} />
                    <Stack.Screen name="ScanDetail" component={ScanDetailScreen} />
                    <Stack.Screen name="Payment" component={PaymentScreen} />
                    <Stack.Screen name="PaymentThankYou" component={PaymentThankYouScreen} options={{ headerShown: false }} />
                </>
            ) : user?.is_admin ? (
                // Admin Portal
                <>
                    <Stack.Screen name="Admin" component={AdminNavigator} />
                </>
            ) : !isPaid ? (
                // Blocked until payment (no onboarding after sign-in)
                <>
                    <Stack.Screen name="Payment" component={PaymentScreen} />
                    <Stack.Screen name="PaymentThankYou" component={PaymentThankYouScreen} options={{ headerShown: false }} />
                </>
            ) : (
                // Main app (paid user) — no Onboarding screen so post-auth never shows it
                <>
                    <Stack.Screen name="Main" component={TabNavigator} />
                    <Stack.Screen name="Profile" component={ProfileScreen} />
                    <Stack.Screen name="EditPersonal" component={EditPersonalScreen} />
                    <Stack.Screen name="ProgressArchive" component={ProgressArchiveScreen} options={{ headerShown: false }} />

                    {/* Course Screens */}
                    <Stack.Screen name="CourseList" component={CourseListScreen} />
                    <Stack.Screen name="CourseDetail" component={CourseDetailScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="ChapterView" component={ChapterViewScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="Schedule" component={ScheduleScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="MaxxDetail" component={MaxxDetailScreen} options={{ headerShown: false }} />
                </>
            )}
        </Stack.Navigator>
    );
}

export default RootNavigator;

