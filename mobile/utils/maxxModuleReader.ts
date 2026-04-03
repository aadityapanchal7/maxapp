/**
 * Build plain text for MaxxModuleReader / FitmaxModuleScreen from API module shapes:
 * - Fitmax-style: { content: string, ... }
 * - Legacy: { title, description?, steps?: { title, content }[] }
 */
export function buildModuleReaderContent(mod: Record<string, unknown> | null | undefined): string {
    if (!mod) return '';

    const content = mod.content;
    if (typeof content === 'string' && content.trim()) {
        return content;
    }

    const title = typeof mod.title === 'string' ? mod.title : 'Module';
    const steps = mod.steps;
    if (Array.isArray(steps) && steps.length > 0) {
        const parts: string[] = [title];
        const desc = mod.description;
        if (typeof desc === 'string' && desc.trim()) {
            parts.push('', desc.trim());
        }
        for (const s of steps) {
            const row = s as { title?: string; content?: string };
            const st = typeof row?.title === 'string' ? row.title : 'Section';
            const sc = typeof row?.content === 'string' ? row.content : '';
            parts.push('', st, '', sc);
        }
        return parts.join('\n');
    }

    const description = mod.description;
    if (typeof description === 'string' && description.trim()) {
        return `${title}\n\n${description.trim()}`;
    }

    return title;
}

export function modulePreviewFromContent(text: string, maxLen = 140): string {
    const cleaned = (text || '').replace(/\s+/g, ' ').trim();
    return cleaned.length > maxLen ? `${cleaned.slice(0, maxLen)}…` : cleaned;
}

/** API Fitmax course row (id, phase, duration, level, status, content, isPremium). */
export function isFitmaxCourseShape(mod: Record<string, unknown> | null | undefined): boolean {
    if (!mod || typeof mod !== 'object') return false;
    if (typeof mod.content !== 'string' || !(mod.content as string).trim()) return false;
    return typeof mod.phase === 'string' || typeof mod.id === 'number';
}
