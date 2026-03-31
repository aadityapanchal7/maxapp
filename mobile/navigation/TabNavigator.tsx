import React, { useEffect } from 'react';
import { StyleSheet, Platform } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, shadows } from '../theme/dark';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { queryClient } from '../lib/queryClient';
import { prefetchMainTabData } from '../lib/prefetchMainTabData';

import HomeScreen from '../screens/home/HomeScreen';
import MaxChatScreen from '../screens/chat/MaxChatScreen';
import ForumsHomeV2Screen from '../screens/forums/ForumsHomeV2Screen';
import SubforumThreadsV2Screen from '../screens/forums/SubforumThreadsV2Screen';
import ThreadV2Screen from '../screens/forums/ThreadV2Screen';
import NewThreadV2Screen from '../screens/forums/NewThreadV2Screen';
import ForumNotificationsV2Screen from '../screens/forums/ForumNotificationsV2Screen';
import CreateSubforumV2Screen from '../screens/forums/CreateSubforumV2Screen';
import MasterScheduleScreen from '../screens/courses/MasterScheduleScreen';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

function ForumsStack() {
    return (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
            <Stack.Screen name="ForumsHomeV2" component={ForumsHomeV2Screen} />
            <Stack.Screen name="SubforumThreadsV2" component={SubforumThreadsV2Screen} />
            <Stack.Screen name="ThreadV2" component={ThreadV2Screen} />
            <Stack.Screen name="NewThreadV2" component={NewThreadV2Screen} />
            <Stack.Screen name="ForumNotificationsV2" component={ForumNotificationsV2Screen} />
            <Stack.Screen name="CreateSubforumV2" component={CreateSubforumV2Screen} />
        </Stack.Navigator>
    );
}

export default function TabNavigator() {
    const insets = useSafeAreaInsets();

    useEffect(() => {
        prefetchMainTabData(queryClient);
    }, []);

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
                name="MasterScheduleTab"
                component={MasterScheduleScreen}
                options={{
                    title: 'Schedule',
                    tabBarLabel: 'Schedule',
                    tabBarIcon: ({ color, size }) => <Ionicons name="calendar-outline" size={22} color={color} />,
                }}
            />
            <Tab.Screen
                name="Chat"
                component={MaxChatScreen}
                options={{
                    tabBarIcon: ({ color, size }) => (
                        <Ionicons name="chatbubble-outline" size={22} color={color} />
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
});
