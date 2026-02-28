import React from 'react';
import { createDrawerNavigator, DrawerContentScrollView, DrawerItemList, DrawerItem } from '@react-navigation/drawer';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { colors, spacing, typography } from '../theme/dark';

import AdminDashboard from '../screens/admin/AdminDashboard';
import UserManageScreen from '../screens/admin/UserManageScreen';
import ForumManageScreen from '../screens/admin/ForumManageScreen';
import LeaderboardManageScreen from '../screens/admin/LeaderboardManageScreen';
import AdminSupportScreen from '../screens/admin/AdminSupportScreen';
import AdminUserChatScreen from '../screens/admin/AdminUserChatScreen';
import ChannelChatScreen from '../screens/forums/ChannelChatScreen';

const Drawer = createDrawerNavigator();

function CustomDrawerContent(props: any) {
    const { logout, user } = useAuth();

    return (
        <DrawerContentScrollView {...props} contentContainerStyle={styles.drawerContainer}>
            <View style={styles.drawerHeader}>
                <View style={styles.avatar}>
                    <Text style={styles.avatarText}>{user?.email[0].toUpperCase()}</Text>
                </View>
                <View style={styles.headerInfo}>
                    <Text style={styles.adminName}>Admin Portal</Text>
                    <Text style={styles.adminEmail}>{user?.email}</Text>
                </View>
            </View>

            <View style={styles.drawerList}>
                <DrawerItemList {...props} />
            </View>

            <TouchableOpacity style={styles.logoutBtn} onPress={logout}>
                <Ionicons name="log-out-outline" size={22} color={colors.error} />
                <Text style={styles.logoutText}>Logout</Text>
            </TouchableOpacity>
        </DrawerContentScrollView>
    );
}

export default function AdminNavigator() {
    return (
        <Drawer.Navigator
            drawerContent={(props) => <CustomDrawerContent {...props} />}
            screenOptions={{
                headerStyle: { backgroundColor: colors.background, elevation: 0, shadowOpacity: 0 },
                headerTintColor: colors.textPrimary,
                drawerStyle: { backgroundColor: colors.background, width: 280 },
                drawerActiveTintColor: colors.accent,
                drawerInactiveTintColor: colors.textMuted,
                drawerLabelStyle: { fontWeight: '600', marginLeft: -16 },
            }}
        >
            <Drawer.Screen name="Dashboard" component={AdminDashboard} options={{ drawerIcon: ({ color }) => <Ionicons name="grid-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="Users" component={UserManageScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="people-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="Forums" component={ForumManageScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="chatbubbles-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="Leaderboard" component={LeaderboardManageScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="trophy-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="Support" component={AdminSupportScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="headset-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="AdminUserChat" component={AdminUserChatScreen} options={{ drawerItemStyle: { display: 'none' }, headerShown: false }} />
            <Drawer.Screen name="ChannelChat" component={ChannelChatScreen} options={{ drawerItemStyle: { display: 'none' }, headerShown: false }} />
        </Drawer.Navigator>
    );
}

const styles = StyleSheet.create({
    drawerContainer: { flex: 1 },
    drawerHeader: { padding: spacing.lg, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md },
    avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.accent, justifyContent: 'center', alignItems: 'center' },
    avatarText: { color: colors.buttonText, fontSize: 20, fontWeight: 'bold' },
    headerInfo: { marginLeft: spacing.md },
    adminName: { ...typography.body, fontWeight: 'bold', color: colors.textPrimary },
    adminEmail: { ...typography.caption, color: colors.textMuted },
    drawerList: { flex: 1 },
    logoutBtn: { flexDirection: 'row', alignItems: 'center', padding: spacing.lg, borderTopWidth: 1, borderTopColor: colors.border, marginTop: 'auto' },
    logoutText: { color: colors.error, fontWeight: 'bold', marginLeft: spacing.md },
});
