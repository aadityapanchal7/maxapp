import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';

const DRAFT_DIR = `${FileSystem.documentDirectory ?? ''}face-scan-draft`;
const META_KEY = '@max_face_scan_draft_meta_v1';
const PENDING_KEY = '@max_face_scan_pending_submit_v1';

type DraftMeta = {
    v: 1;
    userId: string;
    stepIndex: number;
    /** Which slots have a saved file on disk */
    has: [boolean, boolean, boolean];
};

function slotUri(i: number): string {
    return `${DRAFT_DIR}/${i}.jpg`;
}

export async function setPendingFaceScanSubmit(userId: string): Promise<void> {
    if (Platform.OS === 'web') return;
    await AsyncStorage.setItem(PENDING_KEY, JSON.stringify({ userId, at: new Date().toISOString() }));
}

export async function clearPendingFaceScanSubmit(): Promise<void> {
    await AsyncStorage.removeItem(PENDING_KEY);
}

export async function getPendingFaceScanSubmit(): Promise<{ userId: string } | null> {
    try {
        const raw = await AsyncStorage.getItem(PENDING_KEY);
        if (!raw) return null;
        const o = JSON.parse(raw) as { userId?: string };
        return typeof o.userId === 'string' ? { userId: o.userId } : null;
    } catch {
        return null;
    }
}

/** Persist captured angles to app documents + metadata (survives app restart). */
export async function saveFaceScanDraft(userId: string, stepIndex: number, uris: (string | null)[]): Promise<void> {
    if (Platform.OS === 'web' || !FileSystem.documentDirectory) return;
    await FileSystem.makeDirectoryAsync(DRAFT_DIR, { intermediates: true }).catch(() => undefined);

    const has: [boolean, boolean, boolean] = [false, false, false];

    for (let i = 0; i < 3; i++) {
        const u = uris[i];
        const dest = slotUri(i);
        if (!u) {
            const info = await FileSystem.getInfoAsync(dest);
            if (info.exists) await FileSystem.deleteAsync(dest, { idempotent: true });
            continue;
        }
        if (u === dest) {
            const info = await FileSystem.getInfoAsync(dest);
            if (info.exists) {
                has[i] = true;
                continue;
            }
        }
        await FileSystem.copyAsync({ from: u, to: dest });
        has[i] = true;
    }

    const meta: DraftMeta = { v: 1, userId, stepIndex, has };
    await AsyncStorage.setItem(META_KEY, JSON.stringify(meta));
}

export async function loadFaceScanDraft(userId: string): Promise<{ stepIndex: number; uris: (string | null)[] } | null> {
    if (Platform.OS === 'web' || !FileSystem.documentDirectory) return null;
    try {
        const raw = await AsyncStorage.getItem(META_KEY);
        if (!raw) return null;
        const meta = JSON.parse(raw) as DraftMeta;
        if (meta.v !== 1 || meta.userId !== userId) return null;

        const uris: (string | null)[] = [null, null, null];
        for (let i = 0; i < 3; i++) {
            if (!meta.has?.[i]) continue;
            const p = slotUri(i);
            const info = await FileSystem.getInfoAsync(p);
            if (info.exists) uris[i] = p;
        }
        return { stepIndex: meta.stepIndex, uris };
    } catch {
        return null;
    }
}

export async function clearFaceScanDraft(): Promise<void> {
    await AsyncStorage.removeItem(META_KEY);
    if (Platform.OS === 'web' || !FileSystem.documentDirectory) return;
    const info = await FileSystem.getInfoAsync(DRAFT_DIR);
    if (info.exists) await FileSystem.deleteAsync(DRAFT_DIR, { idempotent: true });
}
