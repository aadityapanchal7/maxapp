/**
 * List/detail labels for maxxes — normalizes stale API/RDS rows (e.g. SkinMax, long skin descriptions).
 */

const SKINMAX_DESCRIPTION = 'skincare and your inner glow';

export function getMaxxDisplayLabel(maxx: { id?: string; label?: string }): string {
    const id = String(maxx.id || '').toLowerCase().trim();
    const raw = String(maxx.label ?? maxx.id ?? '').trim();
    if (id === 'skinmax') return 'Skinmax';
    return raw || id;
}

export function getMaxxDisplayDescription(maxx: { id?: string; description?: string }): string | undefined {
    const id = String(maxx.id || '').toLowerCase().trim();
    if (id === 'skinmax') return SKINMAX_DESCRIPTION;
    return maxx.description;
}
