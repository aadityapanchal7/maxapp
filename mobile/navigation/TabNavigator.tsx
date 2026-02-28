import React from 'react';
import { View, TouchableOpacity, StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing } from '../theme/dark';
import { useNavigation } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import HomeScreen from '../screens/home/HomeScreen';
import CannonChatScreen from '../screens/chat/CannonChatScreen';
import ForumsScreen from '../screens/forums/ForumsScreen';
import ChannelChatScreen from '../screens/forums/ChannelChatScreen';
import LeaderboardScreen from '../screens/leaderboard/LeaderboardScreen';

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

function ScanPlaceholder() {
    return <View />;
}

export default function TabNavigator() {
    const insets = useSafeAreaInsets();
    const navigation = useNavigation<any>();

    return (
        <Tab.Navigator
            screenOptions={{
                headerShown: false,
                tabBarStyle: [
                    styles.tabBar,
                    {
                        height: 56 + insets.bottom,
                        paddingBottom: insets.bottom,
                    }
                ],
                tabBarActiveTintColor: colors.primary,
                tabBarInactiveTintColor: colors.textMuted,
                tabBarLabelStyle: styles.tabLabel,
            }}
        >
            <Tab.Screen
                name="Home"
                component={HomeScreen}
                options={{
                    tabBarIcon: ({ color, size }) => <Ionicons name="home-outline" size={size} color={color} />,
                }}
            />
            <Tab.Screen
                name="Chat"
                component={CannonChatScreen}
                options={{
                    tabBarLabel: 'Cannon',
                    tabBarIcon: ({ color, size }) => <Ionicons name="chatbubble-outline" size={size} color={color} />,
                }}
            />
            <Tab.Screen
                name="Scan"
                component={ScanPlaceholder}
                listeners={{
                    tabPress: (e) => {
                        e.preventDefault();
                        navigation.navigate('FaceScan');
                    },
                }}
                options={{
                    tabBarLabel: () => null,
                    tabBarIcon: () => (
                        <View style={styles.scanIcon}>
                            <Ionicons name="add" size={24} color={colors.buttonText} />
                        </View>
                    ),
                }}
            />
            <Tab.Screen
                name="Forums"
                component={ForumsStack}
                options={{
                    tabBarIcon: ({ color, size }) => <Ionicons name="people-outline" size={size} color={color} />,
                }}
            />
            <Tab.Screen
                name="Rank"
                component={LeaderboardScreen}
                options={{
                    tabBarIcon: ({ color, size }) => <Ionicons name="trophy-outline" size={size} color={color} />,
                }}
            />
        </Tab.Navigator>
    );
}

const styles = StyleSheet.create({
    tabBar: {
        backgroundColor: colors.background,
        borderTopColor: colors.borderLight,
        borderTopWidth: 1,
        paddingTop: spacing.xs,
    },
    tabLabel: {
        fontSize: 10,
        fontWeight: '500',
        letterSpacing: 0.2,
    },
    scanIcon: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: colors.accent,
        justifyContent: 'center',
        alignItems: 'center',
    },
});
