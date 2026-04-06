import React from 'react';
import { createDrawerNavigator, DrawerContentScrollView, DrawerItemList } from '@react-navigation/drawer';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { colors, spacing, borderRadius } from '../theme/dark';

import AdminDashboard from '../screens/admin/AdminDashboard';
import UserManageScreen from '../screens/admin/UserManageScreen';
import ForumManageScreen from '../screens/admin/ForumManageScreen';
import LeaderboardManageScreen from '../screens/admin/LeaderboardManageScreen';
import AdminSupportScreen from '../screens/admin/AdminSupportScreen';
import AdminChannelReportsScreen from '../screens/admin/AdminChannelReportsScreen';
import AdminUserChatScreen from '../screens/admin/AdminUserChatScreen';
import ChannelChatScreen from '../screens/forums/ChannelChatScreen';

const Drawer = createDrawerNavigator();

function CustomDrawerContent(props: any) {
    const { logout, user } = useAuth();

    return (
        <DrawerContentScrollView
            {...props}
            contentContainerStyle={styles.drawerScrollContent}
            style={styles.drawerScroll}
        >
            <View style={styles.drawerHeader}>
                <View style={styles.avatar}>
                    <Text style={styles.avatarText}>{user?.email?.[0]?.toUpperCase()}</Text>
                </View>
                <View style={styles.headerInfo}>
                    <Text style={styles.adminName}>Admin Portal</Text>
                    <Text style={styles.adminEmail} numberOfLines={2}>
                        {user?.email}
                    </Text>
                </View>
            </View>

            <View style={styles.drawerList}>
                <DrawerItemList {...props} />
            </View>

            <View style={styles.drawerFooter}>
                <TouchableOpacity style={styles.logoutBtn} onPress={logout} activeOpacity={0.75}>
                    <Ionicons name="log-out-outline" size={22} color={colors.error} />
                    <Text style={styles.logoutText}>Logout</Text>
                </TouchableOpacity>
            </View>
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
                drawerStyle: { backgroundColor: colors.background, width: 300 },
                drawerActiveTintColor: colors.foreground,
                drawerInactiveTintColor: colors.textSecondary,
                drawerActiveBackgroundColor: colors.surface,
                drawerLabelStyle: {
                    fontSize: 16,
                    fontWeight: '600',
                    marginLeft: 4,
                    color: colors.textPrimary,
                },
                drawerItemStyle: {
                    marginHorizontal: spacing.sm,
                    marginVertical: 4,
                    paddingVertical: 6,
                    borderRadius: borderRadius.lg,
                    borderWidth: 0,
                },
            }}
        >
            <Drawer.Screen name="Dashboard" component={AdminDashboard} options={{ drawerIcon: ({ color }) => <Ionicons name="grid-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="Users" component={UserManageScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="people-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="Forums" component={ForumManageScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="chatbubbles-outline" size={22} color={color} /> }} />
            <Drawer.Screen
                name="ChannelReports"
                component={AdminChannelReportsScreen}
                options={{ title: 'UGC reports', drawerIcon: ({ color }) => <Ionicons name="flag-outline" size={22} color={color} /> }}
            />
            <Drawer.Screen name="Leaderboard" component={LeaderboardManageScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="trophy-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="Support" component={AdminSupportScreen} options={{ drawerIcon: ({ color }) => <Ionicons name="headset-outline" size={22} color={color} /> }} />
            <Drawer.Screen name="AdminUserChat" component={AdminUserChatScreen} options={{ drawerItemStyle: { display: 'none' }, headerShown: false }} />
            <Drawer.Screen name="ChannelChat" component={ChannelChatScreen} options={{ drawerItemStyle: { display: 'none' }, headerShown: false }} />
        </Drawer.Navigator>
    );
}

const styles = StyleSheet.create({
    drawerScroll: { flex: 1, backgroundColor: colors.background },
    drawerScrollContent: {
        flexGrow: 1,
        paddingBottom: spacing.lg,
    },
    drawerHeader: {
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.xl,
        paddingBottom: spacing.lg,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: spacing.sm,
    },
    avatar: {
        width: 48,
        height: 48,
        borderRadius: 24,
        backgroundColor: colors.foreground,
        justifyContent: 'center',
        alignItems: 'center',
    },
    avatarText: { color: colors.buttonText, fontSize: 20, fontWeight: '700' },
    headerInfo: { marginLeft: spacing.md, flex: 1, minWidth: 0 },
    adminName: { fontSize: 17, fontWeight: '700', color: colors.textPrimary, marginBottom: 4 },
    adminEmail: { fontSize: 13, color: colors.textMuted, lineHeight: 18 },
    drawerList: {
        paddingTop: spacing.sm,
        paddingHorizontal: spacing.xs,
    },
    drawerFooter: {
        marginTop: spacing.xl,
        paddingTop: spacing.md,
        borderTopWidth: StyleSheet.hairlineWidth,
        borderTopColor: colors.border,
        paddingHorizontal: spacing.sm,
    },
    logoutBtn: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        borderRadius: borderRadius.lg,
    },
    logoutText: { color: colors.error, fontWeight: '700', fontSize: 16, marginLeft: spacing.md },
});
