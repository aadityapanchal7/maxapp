import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from './resilienceKeys';

/**
 * Scoped navigation-position memory. Full NavigationContainer state persistence
 * is risky in this auth-gated, key-swapped setup (it can trap a logged-out user
 * on a protected route, or restore a route shape an old build can't render).
 * So instead of persisting arbitrary deep state, we remember just ONE safe
 * thing: which TAB inside the paid Main stack the user was last on, and restore
 * it as that tab navigator's initialRouteName.
 *
 * Why this is safe:
 *  - It's only ever applied when the app boots into Main (paid) — never into
 *    guest/onboarding/payment stacks, so it can't trap anyone.
 *  - The restored value is validated against the tabs that actually exist in
 *    the active navigator variant; an unknown value falls back to the default.
 *  - The RootNavigator still computes the correct INITIAL stack from auth state,
 *    so the funnel is never skipped — this only restores intra-app position.
 */

// Tab route names of the live navigator (see navigation/TabNavigator).
const VALID_TABS = new Set<string>([
    'Home',
    'MasterScheduleTab',
    'Explore',
    'Chat',
    'Forums',
]);

// Loaded once at boot; read synchronously by the tab navigators at render.
let restoredTab: string | null = null;
let lastPersisted: string | null = null;

export function getRestoredTab(): string | null {
    return restoredTab;
}

/** Load the persisted tab into memory. Call once during the boot gate. */
export async function loadRestoredTab(): Promise<void> {
    try {
        const raw = await AsyncStorage.getItem(STORAGE_KEYS.navState);
        if (!raw) return;
        const o = JSON.parse(raw) as { tab?: string };
        if (o?.tab && VALID_TABS.has(o.tab)) {
            restoredTab = o.tab;
            // Seed the dedupe guard so the restored tab (which onStateChange
            // reports first) doesn't suppress a later genuine change.
            lastPersisted = o.tab;
        }
    } catch {
        /* ignore — fall back to the navigator's default tab */
    }
}

/** Persist the active tab (deduped — only writes on an actual change). */
export function persistActiveTab(tab: string | null): void {
    if (!tab || !VALID_TABS.has(tab)) return;
    if (tab === lastPersisted) return;
    lastPersisted = tab;
    AsyncStorage.setItem(STORAGE_KEYS.navState, JSON.stringify({ tab })).catch(() => undefined);
}

export async function clearRestoredTab(): Promise<void> {
    restoredTab = null;
    lastPersisted = null;
    await AsyncStorage.removeItem(STORAGE_KEYS.navState).catch(() => undefined);
}

/** Pull the currently-focused tab out of a NavigationContainer root state.
 *  Reads the Main route's nested tab state wherever Main sits in the stack, so
 *  it still captures the tab even when a screen is pushed over the tabs. */
export function extractActiveTab(navState: unknown): string | null {
    try {
        const s = navState as { routes?: { name?: string; state?: unknown }[] } | null;
        const mainRoute = s?.routes?.find((r) => r.name === 'Main');
        const tabState = mainRoute?.state as
            | { index?: number; routes?: { name?: string }[] }
            | undefined;
        if (!tabState || typeof tabState.index !== 'number') return null;
        const name = tabState.routes?.[tabState.index]?.name;
        return typeof name === 'string' ? name : null;
    } catch {
        return null;
    }
}

/** Choose an initialRouteName: the restored tab if it exists in THIS variant's
 *  tab list, else undefined (let the navigator use its own default first tab). */
export function pickInitialTab(
    restored: string | null,
    available: string[],
): string | undefined {
    if (restored && available.includes(restored)) return restored;
    return undefined;
}
