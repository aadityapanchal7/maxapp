/**
 * List/detail labels for maxxes — normalizes stale API/RDS rows
 * (e.g. SkinMax, long skin descriptions) and surfaces a curated set
 * of short looksmaxx-coded descriptions per module.
 */

/**
 * Per-maxx display description. Lowercase, terse, slightly cocky —
 * no corporate hedges, no "for clearer brighter skin" copy.
 *
 * Tone target: looksmaxx forum confidence, not influencer. Each line
 * is ≤ 60 chars so it fits the editorial hero comfortably.
 */
const MAXX_DESCRIPTIONS: Record<string, string> = {
    skinmax:   'skin, barrier, glow.',
    hairmax:   'hairline, density, scalp.',
    fitmax:    'frame, leanness, v-taper.',
    bonemax:   'jaw, midface, structure.',
    heightmax: 'posture, decompression, frame.',
};

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

export function getMaxxDisplayDescription(
    maxx: { id?: string; description?: string },
): string | undefined {
    const id = String(maxx.id || '').toLowerCase().trim();
    return MAXX_DESCRIPTIONS[id] ?? maxx.description;
}
