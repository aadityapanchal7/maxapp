/**
 * Home Screen / Lock Screen widget data bridge.
 *
 * Writes a compact "today" snapshot into the shared App Group container so the
 * native WidgetKit extension (targets/widget/index.swift) can render it, then
 * asks WidgetKit to reload its timelines. The widget itself does NO network —
 * it only reads whatever the app last wrote here.
 *
 * Degrades to a no-op on Android, in Expo Go, and in any build where the
 * native module isn't present, so callers can fire it unconditionally.
 */
import { Platform } from 'react-native';

const APP_GROUP = 'group.com.cannon.mobile';
const KEY = 'todaySnapshot';
const QUEUE_KEY = 'widgetToggleQueue';

let storage: {
    set: (k: string, v: string) => void;
    get: (k: string) => string | null;
    remove: (k: string) => void;
} | null = null;
let reloadWidget: (() => void) | null = null;
try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require('@bacons/apple-targets');
    if (Platform.OS === 'ios' && mod?.ExtensionStorage) {
        storage = new mod.ExtensionStorage(APP_GROUP);
        if (typeof mod.ExtensionStorage.reloadWidget === 'function') {
            reloadWidget = () => mod.ExtensionStorage.reloadWidget();
        }
    }
} catch {
    // Native module unavailable (Android build / Expo Go) — stays a no-op.
}

export function clearTodayWidget(): void {
    if (!storage) return;
    try {
        storage.remove(KEY);
        storage.remove(QUEUE_KEY);
        reloadWidget?.();
    } catch {
        // Best-effort: never let a widget clear take down the app.
    }
}

