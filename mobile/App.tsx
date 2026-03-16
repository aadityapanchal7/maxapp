import React from 'react';
import { View, ActivityIndicator, Platform } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { useFonts } from 'expo-font';
import { AuthProvider, useAuth } from './context/AuthContext';
import { RootNavigator } from './navigation/RootNavigator';
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

    const webContainerStyle = Platform.OS === 'web' ? { maxWidth: 1200, width: '100%', alignSelf: 'center' as const, paddingTop: 24 } : {};

    return (
        <GestureHandlerRootView style={{ flex: 1 }}>
            <View style={[{ flex: 1 }, webContainerStyle]}>
                <AuthProvider>
                    <AppNavigator />
                </AuthProvider>
            </View>
        </GestureHandlerRootView>
    );
}
