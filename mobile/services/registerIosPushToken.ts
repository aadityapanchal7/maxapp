import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import { ensureAppNotificationPermission } from './localScheduleNotifications';

/**
 * Native APNs device token for direct server push (hex). iOS only.
 */
export async function getIosApnsDeviceTokenForBackend(): Promise<string | null> {
    if (Platform.OS !== 'ios') return null;
    const granted = await ensureAppNotificationPermission();
    if (!granted) return null;
    try {
        const res = await Notifications.getDevicePushTokenAsync();
        const data = typeof res?.data === 'string' ? res.data.trim() : '';
        return data || null;
    } catch {
        return null;
    }
}
