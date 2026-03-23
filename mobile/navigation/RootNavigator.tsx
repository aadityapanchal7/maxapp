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
import ForgotPasswordScreen from '../screens/auth/ForgotPasswordScreen';
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
import PersonalInfoScreen from '../screens/profile/PersonalInfoScreen';
import ProgressArchiveScreen from '../screens/profile/ProgressArchiveScreen';
import CourseListScreen from '../screens/courses/CourseListScreen';
import CourseDetailScreen from '../screens/courses/CourseDetailScreen';
import ChapterViewScreen from '../screens/courses/ChapterViewScreen';
import ScheduleScreen from '../screens/courses/ScheduleScreen';
import ChannelChatScreen from '../screens/forums/ChannelChatScreen';
import MaxxDetailScreen from '../screens/courses/MaxxDetailScreen';
import HeightScheduleComponentsScreen from '../screens/courses/HeightScheduleComponentsScreen';
import FitmaxPlanScreen from '../screens/courses/FitmaxPlanScreen';
import FitmaxWorkoutTrackerScreen from '../screens/courses/FitmaxWorkoutTrackerScreen';
import FitmaxCalorieLogScreen from '../screens/courses/FitmaxCalorieLogScreen';
import FitmaxProgressScreen from '../screens/courses/FitmaxProgressScreen';
import FitmaxModuleScreen from '../screens/courses/FitmaxModuleScreen';
import TabNavigator from './TabNavigator';
import LandingScreen from '../screens/onboarding/LandingScreen';
import LegalAndSafetyScreen from '../screens/legal/LegalAndSafetyScreen';
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
    const firstScanDone = user?.first_scan_completed === true;

    /**
     * Pre-pay: Onboarding → FeaturesIntro → FaceScan → BlurredResult (UMax results) → Payment (from results only).
     * If they already have a scan but aren’t paid, open on BlurredResult — never skip straight to Payment.
     */
    const initialRoute = !isAuthenticated
        ? 'Landing'
        : user?.is_admin
            ? 'Admin'
            : !isPaid
                ? !onboardingCompleted
                    ? 'Onboarding'
                    : firstScanDone
                        ? 'BlurredResult'
                        : 'FeaturesIntro'
                : 'Main';

    return (
        <Stack.Navigator
            key={isAuthenticated ? 'auth' : 'guest'}
            screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: colors.background },
            }}
            initialRouteName={initialRoute}
        >
            {!isAuthenticated ? (
                <>
                    <Stack.Screen name="Landing" component={LandingScreen} />
                    <Stack.Screen name="Login" component={LoginScreen} />
                    <Stack.Screen name="Signup" component={SignupScreen} />
                    <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
                    <Stack.Screen name="LegalAndSafety" component={LegalAndSafetyScreen} />
                </>
            ) : user?.is_admin ? (
                <>
                    <Stack.Screen name="Admin" component={AdminNavigator} />
                </>
            ) : !isPaid ? (
                <>
                    <Stack.Screen name="Onboarding" component={OnboardingScreen} />
                    <Stack.Screen name="FeaturesIntro" component={FeaturesIntroScreen} />
                    <Stack.Screen name="FaceScan" component={FaceScanScreen} />
                    <Stack.Screen name="BlurredResult" component={BlurredResultScreen} />
                    <Stack.Screen name="FullResult" component={FullResultScreen} />
                    <Stack.Screen name="ScanDetail" component={ScanDetailScreen} />
                    <Stack.Screen name="Payment" component={PaymentScreen} />
                    <Stack.Screen name="PaymentThankYou" component={PaymentThankYouScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="LegalAndSafety" component={LegalAndSafetyScreen} />
                </>
            ) : (
                <>
                    <Stack.Screen name="Main" component={TabNavigator} />
                    <Stack.Screen name="Profile" component={ProfileScreen} />
                    <Stack.Screen name="EditPersonal" component={EditPersonalScreen} />
                    <Stack.Screen name="PersonalInfo" component={PersonalInfoScreen} />
                    <Stack.Screen name="ProgressArchive" component={ProgressArchiveScreen} options={{ headerShown: false }} />

                    <Stack.Screen name="CourseList" component={CourseListScreen} />
                    <Stack.Screen name="CourseDetail" component={CourseDetailScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="ChapterView" component={ChapterViewScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="Schedule" component={ScheduleScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="MaxxDetail" component={MaxxDetailScreen} options={{ headerShown: false }} />
                    <Stack.Screen
                        name="HeightScheduleComponents"
                        component={HeightScheduleComponentsScreen}
                        options={{ headerShown: false }}
                    />
                    <Stack.Screen name="FitmaxPlan" component={FitmaxPlanScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxWorkoutTracker" component={FitmaxWorkoutTrackerScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxCalorieLog" component={FitmaxCalorieLogScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxProgress" component={FitmaxProgressScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxModule" component={FitmaxModuleScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="LegalAndSafety" component={LegalAndSafetyScreen} />
                </>
            )}
        </Stack.Navigator>
    );
}

export default RootNavigator;
