import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';

const DEFAULT_CHANNEL_ID = 'max-schedule-reminders';

if (Platform.OS !== 'web') {
    Notifications.setNotificationHandler({
        handleNotification: async () => ({
            shouldShowAlert: true,
            shouldShowBanner: true,
            shouldShowList: true,
            shouldPlaySound: true,
            shouldSetBadge: true,
        }),
    });
}

export async function ensureAppNotificationPermission(): Promise<boolean> {
    const existing = await Notifications.getPermissionsAsync();
    if (existing.status === 'granted') return true;

    const requested = await Notifications.requestPermissionsAsync();
    return requested.status === 'granted';
}

export async function ensureAndroidNotificationChannel() {
    // Android channels are required for scheduled notifications to show reliably.
    // Safe no-op on iOS.
    try {
        await Notifications.setNotificationChannelAsync(DEFAULT_CHANNEL_ID, {
            name: 'Schedule reminders',
            importance: Notifications.AndroidImportance.MAX,
            sound: false,
        } as any);
    } catch {
        // Ignore if channel cannot be created (older clients / web).
    }
}

export async function scheduleScheduleReminder(params: {
    title: string;
    body: string;
    fireDate: Date;
}): Promise<string> {
    await ensureAndroidNotificationChannel();
    const id = await Notifications.scheduleNotificationAsync({
        content: {
            title: params.title,
            body: params.body,
            sound: false,
        },
        trigger: params.fireDate,
    });
    return String(id);
}

export async function cancelScheduleReminder(notificationId: string): Promise<void> {
    if (!notificationId) return;
    try {
        await Notifications.cancelScheduledNotificationAsync(notificationId);
    } catch {
        // Best-effort cancellation.
    }
}

