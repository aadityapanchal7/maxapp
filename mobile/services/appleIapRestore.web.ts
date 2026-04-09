export async function syncApplePurchasesWithBackend(): Promise<{ verified: number; lastError?: string }> {
    return { verified: 0, lastError: 'In-app restore is only available in the iOS app.' };
}
