import { FitmaxInlineCard, FitmaxMessageUi, FitmaxMacroSummary, FitmaxWorkoutDay, FitmaxExercise } from './types';

const FITMAX_ACCENT = '#0f766e';

export const fitmaxAccent = FITMAX_ACCENT;

const CARD_ID = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export function parseFitmaxMessageUi(content: string): FitmaxMessageUi {
  const text = (content || '').toLowerCase();
  const cards: FitmaxInlineCard[] = [];

  if (text.includes('view your fitmax plan') || text.includes('show me my plan') || text.includes('your fitmax plan')) {
    cards.push({
      id: CARD_ID(),
      type: 'plan',
      title: 'View Your Fitmax Plan',
      subtitle: 'Calories, macros, and weekly split',
      cta: 'View Your Fitmax Plan ->',
    });
  }

  if (text.includes('show my calories') || text.includes('what have i logged') || text.includes('calories left')) {
    cards.push({
      id: CARD_ID(),
      type: 'calorie_log',
      title: 'Today\'s Calorie Log',
      subtitle: 'Consumed vs target and meal breakdown',
      cta: 'Open Calorie Log ->',
    });
  }

  if (text.includes('show my progress') || text.includes('how am i doing') || text.includes('progress trend')) {
    cards.push({
      id: CARD_ID(),
      type: 'progress',
      title: 'Progress Dashboard',
      subtitle: 'Body, lifts, and photos',
      cta: 'Open Progress ->',
    });
  }

  if (text.includes('start my workout') || text.includes('log my session') || text.includes('workout tracker')) {
    cards.push({
      id: CARD_ID(),
      type: 'workout',
      title: 'Start Workout Tracker',
      subtitle: 'Launch your live session now',
      cta: 'Start Workout ->',
    });
  }

  const kind: FitmaxMessageUi['kind'] =
    text.includes('logged.') || text.includes('that\'s roughly')
      ? 'confirmation'
      : text.includes('quick check-in') || text.includes('lock in') || text.includes('stay on target')
      ? 'coaching_insight'
      : 'standard';

  return { kind, cards };
}

export function defaultFitmaxMacroSummary(): FitmaxMacroSummary {
  return {
    calories: 2340,
    protein: 185,
    carbs: 245,
    fat: 70,
    goalLabel: 'Fat Loss · 500 cal deficit',
  };
}

export function defaultFitmaxSplit(): FitmaxWorkoutDay[] {
  return [
    { day: 'Mon', short: 'Push', full: 'Push (Chest · Shoulders · Triceps)', type: 'training' },
    { day: 'Tue', short: 'Pull', full: 'Pull (Back · Rear Delts · Biceps)', type: 'training' },
    { day: 'Wed', short: 'Legs', full: 'Legs (Quads · Hamstrings · Glutes)', type: 'training' },
    { day: 'Thu', short: 'Rest', full: 'Recovery + Steps', type: 'rest' },
    { day: 'Fri', short: 'Push', full: 'Push (Chest · Shoulders · Triceps)', type: 'training' },
    { day: 'Sat', short: 'Pull', full: 'Pull (Back · Rear Delts · Biceps)', type: 'training' },
    { day: 'Sun', short: 'Rest', full: 'Recovery + Mobility', type: 'rest' },
  ];
}

export function defaultWorkoutLibrary(): Record<string, FitmaxExercise[]> {
  return {
    Push: [
      { name: 'Incline Dumbbell Press', setsReps: '4 × 6-10', formNote: 'Control the lowering phase for 2-3 seconds.', equipment: 'Dumbbells' },
      { name: 'Flat Bench Press', setsReps: '3 × 6-8', formNote: 'Keep shoulder blades packed and elbows ~60°.', equipment: 'Barbell' },
      { name: 'Seated Overhead Press', setsReps: '3 × 8-10', formNote: 'Brace hard and press in a straight line.', equipment: 'Dumbbells' },
      { name: 'Cable Lateral Raise', setsReps: '3 × 12-15', formNote: 'Lead with elbows; avoid shrugging.', equipment: 'Cable' },
      { name: 'Rope Pressdown', setsReps: '3 × 10-12', formNote: 'Lock elbows to your side and fully extend.', equipment: 'Cable' },
    ],
    Pull: [
      { name: 'Lat Pulldown', setsReps: '4 × 8-12', formNote: 'Depress scapula first, then drive elbows down.', equipment: 'Machine' },
      { name: 'Chest-Supported Row', setsReps: '3 × 8-10', formNote: 'Pause and squeeze upper back each rep.', equipment: 'Machine' },
      { name: 'Single-Arm Dumbbell Row', setsReps: '3 × 10-12', formNote: 'Pull to the hip, not the chest.', equipment: 'Dumbbells' },
      { name: 'Rear Delt Fly', setsReps: '3 × 12-15', formNote: 'Move through full range, don\'t swing.', equipment: 'Cable' },
      { name: 'EZ-Bar Curl', setsReps: '3 × 8-12', formNote: 'Control both directions, no torso sway.', equipment: 'EZ bar' },
    ],
    Legs: [
      { name: 'Back Squat', setsReps: '4 × 5-8', formNote: 'Knees track out; hit at least parallel.', equipment: 'Barbell' },
      { name: 'Romanian Deadlift', setsReps: '3 × 6-10', formNote: 'Hinge at hips and keep lats tight.', equipment: 'Barbell' },
      { name: 'Leg Press', setsReps: '3 × 10-12', formNote: 'Lower controlled and keep heels planted.', equipment: 'Machine' },
      { name: 'Walking Lunge', setsReps: '2 × 20 steps', formNote: 'Keep torso tall and stride consistent.', equipment: 'Dumbbells' },
      { name: 'Seated Calf Raise', setsReps: '4 × 10-15', formNote: 'Pause at stretch and peak contraction.', equipment: 'Machine' },
    ],
  };
}

export interface DerivedCalorieLog {
  targetCalories: number;
  consumedCalories: number;
  protein: number;
  carbs: number;
  fat: number;
  meals: { bucket: 'Breakfast' | 'Lunch' | 'Dinner' | 'Snacks'; item: string; calories: number }[];
}

function bucketByMessage(msg: string): 'Breakfast' | 'Lunch' | 'Dinner' | 'Snacks' {
  const text = msg.toLowerCase();
  if (text.includes('breakfast')) return 'Breakfast';
  if (text.includes('lunch')) return 'Lunch';
  if (text.includes('dinner')) return 'Dinner';
  return 'Snacks';
}

export function deriveCalorieLogFromMessages(messages: Array<{ role: string; content: string }>): DerivedCalorieLog {
  const target = 2340;
  let consumed = 0;
  let protein = 0;
  let carbs = 0;
  let fat = 0;
  const meals: DerivedCalorieLog['meals'] = [];

  for (const m of messages) {
    if (m.role !== 'assistant') continue;
    const text = m.content || '';
    const lower = text.toLowerCase();
    if (!lower.includes('logged')) continue;

    const calsMatch = text.match(/(\d{2,4})\s*calories?/i);
    const protMatch = text.match(/(\d{1,3})\s*g\s*protein/i);
    const carbMatch = text.match(/(\d{1,3})\s*g\s*carbs?/i);
    const fatMatch = text.match(/(\d{1,3})\s*g\s*fat/i);

    const cals = calsMatch ? Number(calsMatch[1]) : 0;
    const p = protMatch ? Number(protMatch[1]) : Math.round(cals * 0.27 / 4);
    const c = carbMatch ? Number(carbMatch[1]) : Math.round(cals * 0.45 / 4);
    const f = fatMatch ? Number(fatMatch[1]) : Math.round(cals * 0.28 / 9);

    consumed += cals;
    protein += p;
    carbs += c;
    fat += f;

    meals.push({
      bucket: bucketByMessage(text),
      item: 'Logged via chat',
      calories: cals,
    });
  }

  return {
    targetCalories: target,
    consumedCalories: Math.max(0, consumed),
    protein,
    carbs,
    fat,
    meals,
  };
}

export interface DerivedProgressPoint {
  date: string;
  weight: number;
}

export function deriveWeightTrend(messages: Array<{ role: string; content: string; created_at?: string }>): DerivedProgressPoint[] {
  const out: DerivedProgressPoint[] = [];
  for (const m of messages) {
    if (m.role !== 'user') continue;
    const match = (m.content || '').toLowerCase().match(/weighed\s*in\s*at\s*(\d{2,3}(?:\.\d)?)/i);
    if (!match) continue;
    out.push({
      date: m.created_at ? new Date(m.created_at).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10),
      weight: Number(match[1]),
    });
  }
  return out;
}
