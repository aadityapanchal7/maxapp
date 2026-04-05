import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import { ensureAppNotificationPermission } from './localScheduleNotifications';

/** Expo Go / permission dialogs can leave getDevicePushTokenAsync() pending forever without rejecting. */
const IOS_PUSH_TOKEN_FLOW_MS = 22_000;

/**
 * Native APNs device token for direct server push (hex). iOS only.
 */
export async function getIosApnsDeviceTokenForBackend(): Promise<string | null> {
    if (Platform.OS !== 'ios') return null;
    const flow = async (): Promise<string | null> => {
        const granted = await ensureAppNotificationPermission();
        if (!granted) return null;
        try {
            const res = await Notifications.getDevicePushTokenAsync();
            const data = typeof res?.data === 'string' ? res.data.trim() : '';
            return data || null;
        } catch {
            return null;
        }
    };
    try {
        return await Promise.race([
            flow(),
            new Promise<null>((_, reject) =>
                setTimeout(() => reject(new Error('ios_push_token_flow_timeout')), IOS_PUSH_TOKEN_FLOW_MS),
            ),
        ]);
    } catch {
        return null;
    }
}
