/**
 * Per-tier feature limits.
 *
 *   Chadlite (basic):   2 active programs, 1 face scan / week, no course docs
 *   Chad (premium):     3 active programs, 1 face scan / day, full course docs
 *
 * Keep mobile limits in sync with backend enforcement (the source of truth):
 *   - backend/services/schedule_service.py MAX_ACTIVE_SCHEDULES_BASIC / PREMIUM
 *   - backend/api/scans.py for scan rate-limiting
 *   - PaymentScreen.tsx for the user-facing feature copy
 */

export type TierUser = {
    is_paid?: boolean;
    subscription_tier?: string | null;
} | null;

export function isPremium(user: TierUser): boolean {
    if (!user?.is_paid) return false;
    return (user.subscription_tier || '').toLowerCase() === 'premium';
}

/** Active-schedule cap — must match backend MAX_ACTIVE_SCHEDULES_*. */
export function maxActiveSchedulesForUser(user: TierUser): number {
    if (!user?.is_paid) return 2; // unpaid sees same cap as basic until paywall hits
    return isPremium(user) ? 3 : 2;
}

/** "My Maxxes" home tile slots — same as the active-schedule cap. */
export function maxHomeMaxxesForUser(user: TierUser): number {
    return maxActiveSchedulesForUser(user);
}

/** Whether the user can see the per-maxx chapter library (TOC + reader). */
export function canAccessCourseDocs(user: TierUser): boolean {
    return isPremium(user);
}
