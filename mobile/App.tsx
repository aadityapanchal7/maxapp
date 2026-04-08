import React, { useEffect, useRef } from 'react';
import { AppState, View, Platform, type AppStateStatus, type ViewStyle } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { CommonActions, NavigationContainer, useNavigationContainerRef } from '@react-navigation/native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RootNavigator } from './navigation/RootNavigator';
import { queryClient } from './lib/queryClient';
import { colors } from './theme/dark';
import MaxLoadingView from './components/MaxLoadingView';
import { StripeProviderGate } from './components/StripeProviderGate';
import api from './services/api';
import {
    getPendingFaceScanSubmit,
    clearPendingFaceScanSubmit,
    clearFaceScanDraft,
} from './lib/faceScanDraft';
// Side-effect import: registers expo-notifications handler at cold-start so
// remote pushes arriving while the app is foregrounded show a banner.
import './services/localScheduleNotifications';

function AppNavigator() {
    const { isAuthenticated, refreshUser, user } = useAuth();
    const navRef = useNavigationContainerRef();
    const appStateRef = useRef<AppStateStatus>(AppState.currentState);
    const recoveryRunning = useRef(false);

    // Root-level face scan recovery: runs whenever the app comes back to the
    // foreground so a pending upload that was interrupted in the background
    // (or while on a different screen) still resolves correctly.
    useEffect(() => {
        if (!isAuthenticated || !user?.id) return;

        const runRecovery = async () => {
            if (recoveryRunning.current) return;
            const pending = await getPendingFaceScanSubmit().catch(() => null);
            if (!pending || pending.userId !== user.id) return;

            recoveryRunning.current = true;
            try {
                const delays = [0, 1500, 3000, 4500];
                for (const ms of delays) {
                    if (ms > 0) await new Promise((r) => setTimeout(r, ms));
                    try {
                        const u = await refreshUser();
                        if (u?.first_scan_completed) {
                            await clearPendingFaceScanSubmit();
                            await clearFaceScanDraft();
                            navRef.dispatch(
                                CommonActions.reset({ index: 1, routes: [{ name: 'FeaturesIntro' }, { name: 'FaceScanResults' }] }),
                            );
                            return;
                        }
                    } catch { /* continue */ }
                    try {
                        const latest = await api.getLatestScan();
                        const st = (latest as { processing_status?: string })?.processing_status;
                        if (st === 'completed') {
                            await refreshUser();
                            await clearPendingFaceScanSubmit();
                            await clearFaceScanDraft();
                            navRef.dispatch(
                                CommonActions.reset({ index: 1, routes: [{ name: 'FeaturesIntro' }, { name: 'FaceScanResults' }] }),
                            );
                            return;
                        }
                        if (st === 'failed') {
                            await clearPendingFaceScanSubmit();
                            return;
                        }
                    } catch { /* 404 = no scan row yet */ }
                }
                // Still processing — clear flag and let FaceScanResultsScreen poll
                try {
                    const latest = await api.getLatestScan();
                    const st = (latest as { processing_status?: string })?.processing_status;
                    if (st === 'processing') {
                        await clearPendingFaceScanSubmit();
                        navRef.dispatch(
                            CommonActions.reset({ index: 1, routes: [{ name: 'FeaturesIntro' }, { name: 'FaceScanResults' }] }),
                        );
                    }
                } catch { /* no scan */ }
                await clearPendingFaceScanSubmit().catch(() => undefined);
            } finally {
                recoveryRunning.current = false;
            }
        };

        // Run once on mount (covers cold-start after OS kill)
        void runRecovery();

        const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
            const prev = appStateRef.current;
            appStateRef.current = next;
            if (prev.match(/inactive|background/) && next === 'active') {
                void runRecovery();
            }
        });
        return () => sub.remove();
    }, [isAuthenticated, user?.id, refreshUser, navRef]);

    return (
        <NavigationContainer ref={navRef} key={isAuthenticated ? 'auth' : 'guest'}>
            <StatusBar style="dark" />
            <RootNavigator />
        </NavigationContainer>
    );
}

export default function App() {
    const [fontsLoaded] = useFonts({
        'Matter-Regular': require('./assets/fonts/Matter-Regular.ttf'),
        'Matter-Medium': require('./assets/fonts/Matter-Medium.ttf'),
        'Matter-SemiBold': require('./assets/fonts/Matter-SemiBold.ttf'),
        'Matter-Bold': require('./assets/fonts/Matter-Bold.ttf'),
        'Matter-Light': require('./assets/fonts/Matter-Light.ttf'),
        'PlayfairDisplay': require('./assets/fonts/PlayfairDisplay-Variable.ttf'),
        'PlayfairDisplay-Italic': require('./assets/fonts/PlayfairDisplay-Italic-Variable.ttf'),
    });

    if (!fontsLoaded) {
        return <MaxLoadingView />;
    }

    const webContainerStyle: ViewStyle =
        Platform.OS === 'web' ? { maxWidth: 1200, width: '100%', alignSelf: 'center' } : {};

    return (
        <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.background }}>
            <StripeProviderGate>
                <QueryClientProvider client={queryClient}>
                    <SafeAreaProvider style={{ flex: 1, backgroundColor: colors.background }}>
                        <View style={[{ flex: 1, backgroundColor: colors.background }, webContainerStyle]}>
                            <AuthProvider>
                                <AppNavigator />
                            </AuthProvider>
                        </View>
                    </SafeAreaProvider>
                </QueryClientProvider>
            </StripeProviderGate>
        </GestureHandlerRootView>
    );
}
