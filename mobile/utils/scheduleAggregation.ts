/**
 * Shared merge + colors for master schedule and Home "today" tasks.
 */

export const FALLBACK_MODULE_COLORS = ['#6366f1', '#ec4899', '#14b8a6', '#f97316', '#8b5cf6', '#0ea5e9'];

/** Must match backend seed_rds_maxes / app naming so tasks never pick up the wrong program from course_title alone. */
const DEFAULT_MAXX_LABELS: Record<string, string> = {
  skinmax: 'skinmax',
  hairmax: 'Hairmax',
  fitmax: 'Fitmax',
  bonemax: 'Bonemax',
  heightmax: 'Heightmax',
};

const DEFAULT_MAXX_COLORS: Record<string, string> = {
  skinmax: '#8B5CF6',
  hairmax: '#3B82F6',
  fitmax: '#10B981',
  bonemax: '#F59E0B',
  heightmax: '#6366F1',
};

/** Normalize DB/API maxx id (spacing, casing). */
export function normalizeMaxxId(raw: unknown): string {
  if (raw == null) return '';
  const s = String(raw).trim().toLowerCase().replace(/\s+/g, '');
  if (!s) return '';
  if (s === 'skin-max' || s === 'skinmax') return 'skinmax';
  if (s === 'hair-max' || s === 'hairmax') return 'hairmax';
  if (s === 'fit-max' || s === 'fitmax') return 'fitmax';
  if (s === 'bone-max' || s === 'bonemax') return 'bonemax';
  if (s === 'height-max' || s === 'heightmax') return 'heightmax';
  return s;
}

export function fallbackColor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h << 5) - h + key.charCodeAt(i);
  return FALLBACK_MODULE_COLORS[Math.abs(h) % FALLBACK_MODULE_COLORS.length];
}

export type MergedScheduleTask = {
  task_id: string;
  time: string;
  title: string;
  description: string;
  task_type: string;
  duration_minutes: number;
  status: string;
  scheduleId: string;
  moduleLabel: string;
  moduleColor: string;
};

/** When the AI puts skincare copy on the hair schedule (or vice versa), infer display module from task text. */
const SKIN_TASK_RE =
  /\b(skinmax|skincare|skin care|spf\b|sunscreen|retinoid|retinol|\bam\s+skincare|\bpm\s+skincare|cleanser?\b|niacinamide|exfoliat|your skinmax|moisturiz\w*|moisturis\w*|evening routine:\s*cleanse)\b/i;
const HAIR_TASK_RE =
  /\b(hairmax|minoxidil|finasteride|dutasteride|hair loss|ketoconazole\s+shampoo|microneedl(?:e|ing)\s+(?:for\s+)?hair|dermaroll(?:er)?\s+(?:for\s+)?(?:hair|scalp))\b/i;

/** Collapse duplicate rows when two schedules (or bad AI) emit the same routine at the same time. */
function normalizeRoutineTitle(title: string): string {
  let s = (title || '').toLowerCase().replace(/\s+/g, ' ').trim();
  s = s.replace(/\s*\([^)]*\)\s*/g, ' ').replace(/\s+/g, ' ').trim();
  return s.slice(0, 56);
}

/** Same-day duplicate PM (or AM) skincare rows often differ only by time or wording — collapse to one per bucket. */
function skincareRoutineFingerprint(title: string, desc: string): string {
  const blob = `${title || ''} ${desc || ''}`;
  if (!SKIN_TASK_RE.test(blob)) return '';
  let core = (title || '')
    .toLowerCase()
    .replace(/\b(pm|am|p\.?m\.?|a\.?m\.?|evening|night|morning|bedtime|skincare|skin care|routine|daily)\b/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (core.length < 2) core = 'skincare_routine';
  return core.slice(0, 48);
}

function skincareAmPmBucket(task: MergedScheduleTask): 'am' | 'pm' | 'x' {
  const blob = `${task.title || ''} ${task.description || ''}`;
  if (/\b(pm|evening|night|bedtime|before bed)\b/i.test(blob)) return 'pm';
  if (/\b(am|morning)\b/i.test(blob)) return 'am';
  const time = (task.time || '').trim();
  if (time.includes(':')) {
    const h = parseInt(time.split(':')[0], 10);
    if (!isNaN(h)) {
      if (h < 12) return 'am';
      return 'pm';
    }
  }
  return 'x';
}

function dedupeKeyForTask(t: MergedScheduleTask): string {
  const fp = skincareRoutineFingerprint(t.title || '', t.description || '');
  if (fp) {
    const bucket = skincareAmPmBucket(t);
    return `${t.moduleLabel}|SC|${bucket}|${fp}`;
  }
  const rk = normalizeRoutineTitle(t.title || '');
  return `${t.moduleLabel}|${(t.time || '').trim()}|${rk}`;
}

function dedupeMasterTasksForDay(tasks: MergedScheduleTask[]): MergedScheduleTask[] {
  const best = new Map<string, MergedScheduleTask>();
  for (const t of tasks) {
    const key = dedupeKeyForTask(t);
    const prev = best.get(key);
    if (!prev) {
      best.set(key, t);
      continue;
    }
    const nextLen = (t.description || '').length;
    const prevLen = (prev.description || '').length;
    best.set(key, nextLen >= prevLen ? t : prev);
  }
  return Array.from(best.values()).sort((a, b) => (a.time || '').localeCompare(b.time || ''));
}

function displayModuleForTask(
  task: { title?: string; description?: string },
  scheduleMid: string,
  baseLabel: string,
  baseColor: string,
  activeMaxxIds: Set<string>,
  maxxLabels: Record<string, string>,
  maxxColors: Record<string, string>,
): { moduleLabel: string; moduleColor: string } {
  const blob = `${task.title || ''} ${task.description || ''}`;
  const skinish = SKIN_TASK_RE.test(blob);
  const hairish = HAIR_TASK_RE.test(blob);

  if (scheduleMid === 'skinmax' && hairish && !skinish && activeMaxxIds.has('hairmax')) {
    return {
      moduleLabel: maxxLabels['hairmax'] || DEFAULT_MAXX_LABELS.hairmax,
      moduleColor: maxxColors['hairmax'] || DEFAULT_MAXX_COLORS.hairmax,
    };
  }
  return { moduleLabel: baseLabel, moduleColor: baseColor };
}

export function buildMaxxMaps(maxxes: any[]): {
  labels: Record<string, string>;
  colors: Record<string, string>;
} {
  const labels: Record<string, string> = {};
  const colors: Record<string, string> = {};
  for (const x of maxxes || []) {
    if (x?.id) {
      const id = normalizeMaxxId(x.id);
      if (!id) continue;
      labels[id] = x.label || DEFAULT_MAXX_LABELS[id] || x.id;
      if (x.color) colors[id] = x.color;
    }
  }
  return { labels, colors };
}

export function mergeSchedules(
  schedules: any[],
  maxxLabels: Record<string, string>,
  maxxColors: Record<string, string>,
): {
  byDate: Record<string, MergedScheduleTask[]>;
  dates: string[];
  legend: { id: string; label: string; color: string }[];
} {
  const byDate: Record<string, MergedScheduleTask[]> = {};
  const legendMap = new Map<string, { label: string; color: string }>();
  const activeMaxxIds = new Set<string>();
  for (const s of schedules || []) {
    const m = normalizeMaxxId(s.maxx_id);
    if (m) activeMaxxIds.add(m);
  }

  for (const s of schedules || []) {
    const mid = normalizeMaxxId(s.maxx_id);
    const label = mid
      ? maxxLabels[mid] || DEFAULT_MAXX_LABELS[mid] || s.maxx_id || mid
      : s.course_title || s.maxx_id || 'Program';
    const color = mid
      ? maxxColors[mid] || DEFAULT_MAXX_COLORS[mid] || fallbackColor(mid)
      : fallbackColor(String(s.course_title || s.maxx_id || 'program').toLowerCase());
    legendMap.set(s.id, { label, color });

    for (const day of s.days || []) {
      const d = day.date;
      if (!d) continue;
      for (const t of day.tasks || []) {
        const blobEarly = `${t.title || ''} ${t.description || ''}`;
        const skinEarly = SKIN_TASK_RE.test(blobEarly);
        const hairEarly = HAIR_TASK_RE.test(blobEarly);
        if (mid === 'hairmax' && skinEarly && !hairEarly) continue;

        if (!byDate[d]) byDate[d] = [];
        const { moduleLabel, moduleColor } = displayModuleForTask(
          t,
          mid,
          label,
          color,
          activeMaxxIds,
          maxxLabels,
          maxxColors,
        );
        byDate[d].push({
          ...t,
          scheduleId: s.id,
          moduleLabel,
          moduleColor,
        });
      }
    }
  }

  const dates = Object.keys(byDate).sort();
  for (const d of dates) {
    byDate[d] = dedupeMasterTasksForDay(byDate[d]);
  }

  const legend = Array.from(legendMap.entries()).map(([id, v]) => ({
    id,
    label: v.label,
    color: v.color,
  }));

  return { byDate, dates, legend };
}

export function moduleColorForSchedule(
  schedule: { maxx_id?: string; course_title?: string } | null,
  maxxColors: Record<string, string>,
): string {
  if (!schedule) return FALLBACK_MODULE_COLORS[0];
  const mid = normalizeMaxxId(schedule.maxx_id);
  if (mid) {
    return maxxColors[mid] || DEFAULT_MAXX_COLORS[mid] || fallbackColor(mid);
  }
  return fallbackColor(String(schedule.course_title || schedule.maxx_id || 'x').toLowerCase());
}

export function moduleLabelForSchedule(
  schedule: { maxx_id?: string; course_title?: string } | null,
  maxxLabels: Record<string, string>,
): string {
  if (!schedule) return 'Program';
  const mid = normalizeMaxxId(schedule.maxx_id);
  if (mid) {
    return maxxLabels[mid] || DEFAULT_MAXX_LABELS[mid] || schedule.maxx_id || mid;
  }
  return schedule.course_title || schedule.maxx_id || 'Program';
}
