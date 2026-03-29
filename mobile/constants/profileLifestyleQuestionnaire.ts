/**
 * Shared option lists + helpers for profile "Edit lifestyle" (parity with onboarding v2).
 */

export const PRIORITY_KEYS = ['face_structure', 'skin', 'hair', 'body', 'height'] as const;
export type PriorityKey = (typeof PRIORITY_KEYS)[number];

export const PRIORITY_LABELS: Record<PriorityKey, string> = {
  face_structure: 'Face structure',
  skin: 'Skin',
  hair: 'Hair',
  body: 'Body',
  height: 'Height',
};

export const APPEARANCE_OPTIONS: { id: string; label: string }[] = [
  { id: 'jawline', label: 'Jawline' },
  { id: 'skin', label: 'Skin' },
  { id: 'hair_thinning', label: 'Hair thinning' },
  { id: 'body_fat', label: 'Body fat' },
  { id: 'posture', label: 'Posture' },
  { id: 'height', label: 'Height' },
  { id: 'under_eye', label: 'Under-eye area' },
  { id: 'asymmetry', label: 'Facial asymmetry' },
  { id: 'acne', label: 'Acne' },
  { id: 'teeth', label: 'Teeth' },
];

export const SKIN_CONCERNS = [
  { id: 'acne', label: 'Acne' },
  { id: 'pigmentation', label: 'Pigmentation' },
  { id: 'texture-scarring', label: 'Texture / scarring' },
  { id: 'redness', label: 'Redness' },
  { id: 'aging', label: 'Aging' },
];

export const SCREEN_TIME_BANDS = [
  { id: 'under_4', label: 'Under 4h' },
  { id: '4_6', label: '4–6h' },
  { id: '6_8', label: '6–8h' },
  { id: '8_plus', label: '8h+' },
];

export const TIME_OPTIONS: string[] = Array.from({ length: 48 }, (_, i) => {
  const h = Math.floor(i / 2);
  const m = i % 2 === 0 ? 0 : 30;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
});

export function mapSkinConcernToType(concern: string): string {
  const c: Record<string, string> = {
    acne: 'oily',
    pigmentation: 'combination',
    'texture-scarring': 'combination',
    redness: 'sensitive',
    aging: 'normal',
  };
  return c[concern] || 'normal';
}

export function mapTrainingToExperience(t: string): string {
  if (t === 'never' || t === 'beginner') return 'beginner';
  if (t === 'intermediate') return 'intermediate';
  if (t === 'advanced') return 'advanced';
  return 'beginner';
}

export function mapEquipmentToList(eq: string): string[] {
  if (eq === 'full_gym') return ['gym'];
  if (eq === 'home_gym') return ['dumbbells'];
  return ['none'];
}

export function formatTime12h(hhmm24: string): string {
  const [hs, ms] = hhmm24.split(':');
  const h = parseInt(hs || '0', 10);
  const m = parseInt(ms || '0', 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return hhmm24;
  const suffix = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, '0')} ${suffix}`;
}

export function hhmm(s: string): string {
  const p = s.trim().split(':');
  const h = Math.min(23, Math.max(0, parseInt(p[0] || '0', 10)));
  const m = Math.min(59, Math.max(0, parseInt(p[1] || '0', 10)));
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function heavyScreenFromBand(screenBand: string): string {
  return screenBand === '6_8' || screenBand === '8_plus'
    ? '6+ hours/day'
    : screenBand === '4_6'
      ? '4-6 hours/day'
      : 'under 4 hours/day';
}

export function inferScreenBand(ob: Record<string, unknown>): string {
  const s = ob.screen_hours_daily;
  if (s === 'under_4' || s === '4_6' || s === '6_8' || s === '8_plus') return s as string;
  const h = String(ob.heightmax_screen_hours || ob.bonemax_heavy_screen_time || '');
  if (h.includes('6+') || h.includes('8')) return '8_plus';
  if (h.includes('4-6') || h.includes('4–6')) return '4_6';
  if (h.includes('6-8') || h.includes('6–8')) return '6_8';
  if (h.toLowerCase().includes('under')) return 'under_4';
  return '';
}

export function normalizePriorityOrder(raw: unknown): PriorityKey[] {
  const valid = new Set<string>(PRIORITY_KEYS);
  const arr = Array.isArray(raw) ? raw.filter((x) => typeof x === 'string' && valid.has(x)) : [];
  if (arr.length === PRIORITY_KEYS.length) return arr as PriorityKey[];
  return [...PRIORITY_KEYS];
}

export function inferFitEquipmentFromOnboarding(ob: Record<string, unknown>): string {
  const fe = String(ob.fitmax_equipment || '').trim();
  if (fe === 'full_gym' || fe === 'home_gym' || fe === 'bodyweight') return fe;
  const eq = ob.equipment;
  if (Array.isArray(eq)) {
    if (eq.includes('gym')) return 'full_gym';
    if (eq.includes('dumbbells')) return 'home_gym';
  }
  return 'bodyweight';
}
