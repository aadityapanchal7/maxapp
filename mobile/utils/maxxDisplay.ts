/**
 * List/detail labels for maxxes — normalizes stale API/RDS rows (e.g. SkinMax, long skin descriptions).
 */

const SKINMAX_DESCRIPTION = 'skincare and your inner glow';

/**
 * Lowercase the "m" in *Max product names (FitMax → Fitmax, HAIRMAX → HAIRmax).
 * Also handles "FitMax — …" style titles.
 */
export function normalizeMaxxNameSuffix(label: string): string {
    let s = String(label || '').trim();
    if (!s) return s;
    s = s.replace(/Max$/i, 'max');
    s = s.replace(/([A-Za-z0-9])Max(?=\s*[—\-–])/g, '$1max');
    return s;
}

export function getMaxxDisplayLabel(maxx: { id?: string; label?: string }): string {
    const id = String(maxx.id || '').toLowerCase().trim();
    const raw = String(maxx.label ?? maxx.id ?? '').trim();
    if (id === 'skinmax') return 'Skinmax';
    return normalizeMaxxNameSuffix(raw || id);
}

export function getMaxxDisplayDescription(maxx: { id?: string; description?: string }): string | undefined {
    const id = String(maxx.id || '').toLowerCase().trim();
    if (id === 'skinmax') return SKINMAX_DESCRIPTION;
    return maxx.description;
}
