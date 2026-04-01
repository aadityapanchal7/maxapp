/** Max "My Maxxes" slots on Home (matches schedule limits: Basic 2, Premium 3). Unpaid treated as 2. */
export function maxHomeMaxxesForUser(user: {
    is_paid?: boolean;
    subscription_tier?: string | null;
} | null): number {
    if (!user?.is_paid) return 2;
    const t = (user.subscription_tier || '').toLowerCase();
    if (t === 'premium') return 3;
    return 2;
}
