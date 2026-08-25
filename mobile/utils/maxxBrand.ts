/**
 * Brand color + icon fallbacks when /maxxes API omits them — matches in-app program cards (pastel tiles).
 */

export const MAXX_BRAND_FALLBACK: Record<string, string> = {
    hairmax: '#3B82F6',
    bonemax: '#F59E0B',
    heightmax: '#8B5CF6',
    skinmax: '#E879A9',
    fitmax: '#10B981',
    coloringmax: '#BC7A3C',
};


export function resolveMaxxBrand(id: string, apiColor?: string | null): string {
    const key = String(id || '').toLowerCase().trim();
    const c = apiColor != null ? String(apiColor).trim() : '';
    if (c) return c;
    return MAXX_BRAND_FALLBACK[key] || '#71717a';
}
