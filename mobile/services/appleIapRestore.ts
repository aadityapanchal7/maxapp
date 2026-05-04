import { Platform } from 'react-native';
import { finishTransaction, getAvailablePurchases, initConnection, type Purchase } from 'react-native-iap';
import { APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU } from '../constants/appleIap';
import api from './api';

const SKU_SET = new Set<string>([APPLE_IAP_BASIC_SKU, APPLE_IAP_PREMIUM_SKU]);

function iosTransactionId(p: Purchase): string | null {
    if (p.platform !== 'ios') return null;
    const raw = (p as { transactionId?: string; id?: string }).transactionId ?? (p as { id?: string }).id;
    const tid = raw != null && String(raw).trim() ? String(raw).trim() : '';
    return tid || null;
}

/**
 * Re-fetch StoreKit entitlements and verify each known Agartha subscription with the backend.
 * Used for Restore Purchases and after reinstall.
 */
export async function syncApplePurchasesWithBackend(): Promise<{ verified: number; lastError?: string }> {
    if (Platform.OS !== 'ios') {
        return { verified: 0, lastError: 'Available on iPhone only.' };
    }
    await initConnection();
    const purchases = await getAvailablePurchases({ onlyIncludeActiveItemsIOS: true });
    let verified = 0;
    let lastError: string | undefined;

    for (const p of purchases) {
        if (!SKU_SET.has(p.productId)) continue;
        const tid = iosTransactionId(p);
        if (!tid) continue;
        try {
            await api.verifyAppleIapTransaction(tid);
            await finishTransaction({ purchase: p });
            verified += 1;
        } catch (e: unknown) {
            const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
            lastError =
                typeof d === 'string'
                    ? d
                    : Array.isArray(d)
                      ? d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join('\n') ||
                        'Verification failed'
                      : (e as Error)?.message || 'Verification failed';
        }
    }

    return { verified, lastError };
}
