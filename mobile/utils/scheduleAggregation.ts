/**
 * Shared merge + colors for master schedule and Home "today" tasks.
 */

export const FALLBACK_MODULE_COLORS = ['#6366f1', '#ec4899', '#14b8a6', '#f97316', '#8b5cf6', '#0ea5e9'];

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

export function buildMaxxMaps(maxxes: any[]): {
  labels: Record<string, string>;
  colors: Record<string, string>;
} {
  const labels: Record<string, string> = {};
  const colors: Record<string, string> = {};
  for (const x of maxxes || []) {
    if (x?.id) {
      const id = String(x.id).toLowerCase();
      labels[id] = x.label || x.id;
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

  for (const s of schedules || []) {
    const mid = (s.maxx_id || '').toLowerCase();
    const label = (mid && maxxLabels[mid]) || s.course_title || s.maxx_id || 'Program';
    const color =
      (mid && maxxColors[mid]) || fallbackColor((s.course_title || s.maxx_id || 'x').toLowerCase());
    legendMap.set(s.id, { label, color });

    for (const day of s.days || []) {
      const d = day.date;
      if (!d) continue;
      for (const t of day.tasks || []) {
        if (!byDate[d]) byDate[d] = [];
        byDate[d].push({
          ...t,
          scheduleId: s.id,
          moduleLabel: label,
          moduleColor: color,
        });
      }
    }
  }

  const dates = Object.keys(byDate).sort();
  for (const d of dates) {
    byDate[d].sort((a, b) => (a.time || '').localeCompare(b.time || ''));
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
  const mid = (schedule.maxx_id || '').toLowerCase();
  if (mid && maxxColors[mid]) return maxxColors[mid];
  return fallbackColor((schedule.course_title || schedule.maxx_id || 'x').toLowerCase());
}

export function moduleLabelForSchedule(
  schedule: { maxx_id?: string; course_title?: string } | null,
  maxxLabels: Record<string, string>,
): string {
  if (!schedule) return 'Program';
  const mid = (schedule.maxx_id || '').toLowerCase();
  if (mid && maxxLabels[mid]) return maxxLabels[mid];
  return schedule.course_title || schedule.maxx_id || 'Program';
}
