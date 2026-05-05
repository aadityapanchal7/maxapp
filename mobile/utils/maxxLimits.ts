/**
 * Per-tier feature limits.
 *
 *   Chadlite (basic):   1 active program, 1 face scan / week, no course docs
 *   Chad (premium):     3 active programs, 1 face scan / day, full course docs
 *
 * Keep mobile limits in sync with backend enforcement
 * (backend/api/scans.py for scan rate-limiting; PaymentScreen.tsx for
 * the user-facing feature copy).
 */

export type TierUser = {
    is_paid?: boolean;
    subscription_tier?: string | null;
} | null;

export function isPremium(user: TierUser): boolean {
    if (!user?.is_paid) return false;
    return (user.subscription_tier || '').toLowerCase() === 'premium';
}

/** "My Maxxes" home tile slots — Chadlite 1, Chad 3, unpaid 1. */
export function maxHomeMaxxesForUser(user: TierUser): number {
    if (!user?.is_paid) return 1;
    return isPremium(user) ? 3 : 1;
}

/** Whether the user can see the per-maxx chapter library (TOC + reader). */
export function canAccessCourseDocs(user: TierUser): boolean {
    return isPremium(user);
}
