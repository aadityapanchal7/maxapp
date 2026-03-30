import React from 'react';
import { View, ActivityIndicator, Platform, type ViewStyle } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RootNavigator } from './navigation/RootNavigator';
import { queryClient } from './lib/queryClient';
import { colors } from './theme/dark';

function AppNavigator() {
    const { isAuthenticated } = useAuth();
    return (
        <NavigationContainer key={isAuthenticated ? 'auth' : 'guest'}>
            <StatusBar style="dark" />
            <RootNavigator />
        </NavigationContainer>
    );
}

export default function App() {
    const [fontsLoaded] = useFonts({
        'Matter-Regular': require('./assets/fonts/Matter-Regular.ttf'),
        'Matter-Medium': require('./assets/fonts/Matter-Medium.ttf'),
    });

    if (!fontsLoaded) {
        return (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background }}>
                <ActivityIndicator size="large" color={colors.accent} />
            </View>
        );
    }

    const webContainerStyle: ViewStyle =
        Platform.OS === 'web' ? { maxWidth: 1200, width: '100%', alignSelf: 'center' } : {};

    return (
        <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.background }}>
            <QueryClientProvider client={queryClient}>
                <SafeAreaProvider style={{ flex: 1, backgroundColor: colors.background }}>
                    <View style={[{ flex: 1, backgroundColor: colors.background }, webContainerStyle]}>
                        <AuthProvider>
                            <AppNavigator />
                        </AuthProvider>
                    </View>
                </SafeAreaProvider>
            </QueryClientProvider>
        </GestureHandlerRootView>
    );
}
