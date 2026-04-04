/**
 * Root Navigator - Auth flow control
 */

import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from '../context/AuthContext';
import MaxLoadingView from '../components/MaxLoadingView';
import { colors } from '../theme/dark';

// Screens
import LoginScreen from '../screens/auth/LoginScreen';
import SignupScreen from '../screens/auth/SignupScreen';
import ForgotPasswordScreen from '../screens/auth/ForgotPasswordScreen';
import OnboardingScreen from '../screens/onboarding/OnboardingScreen';
import FeaturesIntroScreen from '../screens/onboarding/FeaturesIntroScreen';
import FaceScanScreen from '../screens/scan/FaceScanScreen';
import FaceScanResultsScreen from '../screens/scan/FaceScanResultsScreen';
import SendblueConnectScreen from '../screens/scan/SendblueConnectScreen';
import NotificationChannelsScreen from '../screens/scan/NotificationChannelsScreen';
import ModuleSelectScreen from '../screens/scan/ModuleSelectScreen';
import ScanDetailScreen from '../screens/scan/ScanDetailScreen';
import PaymentScreen from '../screens/payment/PaymentScreen';
import PaymentThankYouScreen from '../screens/payment/PaymentThankYouScreen';
import ProfileScreen from '../screens/profile/ProfileScreen';
import SettingsScreen from '../screens/profile/SettingsScreen';
import EditPersonalScreen from '../screens/profile/EditPersonalScreen';
import ManageSubscriptionScreen from '../screens/profile/ManageSubscriptionScreen';
import PersonalInfoScreen from '../screens/profile/PersonalInfoScreen';
import ProgressArchiveScreen from '../screens/profile/ProgressArchiveScreen';
import FaceScanArchiveScreen from '../screens/profile/FaceScanArchiveScreen';
import CourseListScreen from '../screens/courses/CourseListScreen';
import CourseDetailScreen from '../screens/courses/CourseDetailScreen';
import ChapterViewScreen from '../screens/courses/ChapterViewScreen';
import ScheduleScreen from '../screens/courses/ScheduleScreen';
import MaxxDetailScreen from '../screens/courses/MaxxDetailScreen';
import FitmaxPlanScreen from '../screens/courses/FitmaxPlanScreen';
import FitmaxWorkoutTrackerScreen from '../screens/courses/FitmaxWorkoutTrackerScreen';
import FitmaxCalorieLogScreen from '../screens/courses/FitmaxCalorieLogScreen';
import FitmaxProgressScreen from '../screens/courses/FitmaxProgressScreen';
import FitmaxModuleScreen from '../screens/courses/FitmaxModuleScreen';
import TabNavigator from './TabNavigator';
import LandingScreen from '../screens/onboarding/LandingScreen';
import LegalDocumentScreen from '../screens/legal/LegalDocumentScreen';
import AdminNavigator from './AdminNavigator';

const Stack = createNativeStackNavigator();

export function RootNavigator() {
    const { user, isLoading, isAuthenticated, isPaid } = useAuth();

    if (isLoading) {
        return <MaxLoadingView />;
    }

    const onboardingCompleted = user?.onboarding?.completed === true;
    const firstScanDone = user?.first_scan_completed === true;

    /**
     * Pre-pay: Onboarding → FeaturesIntro → FaceScan → FaceScanResults (locked) → Payment.
     * Post-pay: optional FaceScanResults → ModuleSelect via onboarding.post_subscription_onboarding.
     */
    const initialRoute = !isAuthenticated
        ? 'Landing'
        : user?.is_admin
            ? 'Admin'
            : !isPaid
                ? !onboardingCompleted
                    ? 'Onboarding'
                    : firstScanDone
                        ? 'FaceScanResults'
                        : 'FeaturesIntro'
                : 'Main';

    const stackKey = !isAuthenticated
        ? 'guest'
        : user?.is_admin
            ? 'admin'
            : isPaid
                ? 'auth-paid'
                : 'auth-unpaid';

    return (
        <Stack.Navigator
            key={stackKey}
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
                    <Stack.Screen name="Settings" component={SettingsScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="LegalDocument" component={LegalDocumentScreen} options={{ headerShown: false }} />
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
                    <Stack.Screen name="FaceScanResults" component={FaceScanResultsScreen} />
                    <Stack.Screen name="ScanDetail" component={ScanDetailScreen} />
                    <Stack.Screen name="Payment" component={PaymentScreen} />
                    <Stack.Screen name="PaymentThankYou" component={PaymentThankYouScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="Settings" component={SettingsScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="LegalDocument" component={LegalDocumentScreen} options={{ headerShown: false }} />
                </>
            ) : (
                <>
                    <Stack.Screen name="Main" component={TabNavigator} />
                    <Stack.Screen name="FaceScan" component={FaceScanScreen} />
                    <Stack.Screen name="FaceScanResults" component={FaceScanResultsScreen} />
                    <Stack.Screen name="SendblueConnect" component={SendblueConnectScreen} />
                    <Stack.Screen name="NotificationChannels" component={NotificationChannelsScreen} />
                    <Stack.Screen name="ModuleSelect" component={ModuleSelectScreen} />
                    <Stack.Screen name="Profile" component={ProfileScreen} />
                    <Stack.Screen name="Settings" component={SettingsScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="EditPersonal" component={EditPersonalScreen} />
                    <Stack.Screen name="ManageSubscription" component={ManageSubscriptionScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="PersonalInfo" component={PersonalInfoScreen} />
                    <Stack.Screen name="ProgressArchive" component={ProgressArchiveScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FaceScanArchive" component={FaceScanArchiveScreen} options={{ headerShown: false }} />

                    <Stack.Screen name="CourseList" component={CourseListScreen} />
                    <Stack.Screen name="CourseDetail" component={CourseDetailScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="ChapterView" component={ChapterViewScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="Schedule" component={ScheduleScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="MaxxDetail" component={MaxxDetailScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxPlan" component={FitmaxPlanScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxWorkoutTracker" component={FitmaxWorkoutTrackerScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxCalorieLog" component={FitmaxCalorieLogScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxProgress" component={FitmaxProgressScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="FitmaxModule" component={FitmaxModuleScreen} options={{ headerShown: false }} />
                    <Stack.Screen name="LegalDocument" component={LegalDocumentScreen} options={{ headerShown: false }} />
                </>
            )}
        </Stack.Navigator>
    );
}

export default RootNavigator;
