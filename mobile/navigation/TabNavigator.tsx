import React from 'react';
import { View, StyleSheet, Platform } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, shadows } from '../theme/dark';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import HomeScreen from '../screens/home/HomeScreen';
import MaxChatScreen from '../screens/chat/MaxChatScreen';
import ForumsScreen from '../screens/forums/ForumsScreen';
import ChannelChatScreen from '../screens/forums/ChannelChatScreen';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

function ForumsStack() {
    return (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
            <Stack.Screen name="ForumsList" component={ForumsScreen} />
            <Stack.Screen name="ChannelChat" component={ChannelChatScreen} />
        </Stack.Navigator>
    );
}

export default function TabNavigator() {
    const insets = useSafeAreaInsets();

    return (
        <Tab.Navigator
            screenOptions={{
                headerShown: false,
                tabBarStyle: [
                    styles.tabBar,
                    {
                        height: 52 + insets.bottom,
                        paddingBottom: insets.bottom,
                    }
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
                    tabBarIcon: ({ color, size }) => <Ionicons name="home-outline" size={22} color={color} />,
                }}
            />
            <Tab.Screen
                name="Chat"
                component={MaxChatScreen}
                options={{
                    tabBarLabel: () => null,
                    tabBarIcon: () => (
                        <View style={styles.centerIcon}>
                            <Ionicons name="chatbubble-outline" size={22} color={colors.buttonText} />
                        </View>
                    ),
                }}
            />
            <Tab.Screen
                name="Forums"
                component={ForumsStack}
                options={{
                    tabBarIcon: ({ color, size }) => <Ionicons name="people-outline" size={22} color={color} />,
                }}
            />
        </Tab.Navigator>
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
    centerIcon: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: colors.foreground,
        justifyContent: 'center',
        alignItems: 'center',
        ...shadows.md,
    },
});
