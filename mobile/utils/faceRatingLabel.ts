/** Short label for progress overlay (e.g. 7 or 7.2). */
export function formatFaceRatingLabel(v: number): string {
    if (!Number.isFinite(v)) return '';
    const r = Math.round(v * 10) / 10;
    return Number.isInteger(r) ? String(r) : r.toFixed(1);
}
