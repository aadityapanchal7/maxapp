export type FitmaxCardType =
  | 'plan'
  | 'calorie_log'
  | 'progress'
  | 'workout'
  | 'module'
  | 'pr_notification'
  | 'quick_log';

export interface FitmaxInlineCard {
  id: string;
  type: FitmaxCardType;
  title: string;
  subtitle?: string;
  cta: string;
  payload?: Record<string, any>;
}

export interface FitmaxMessageUi {
  kind: 'standard' | 'confirmation' | 'coaching_insight';
  cards: FitmaxInlineCard[];
}

export interface FitmaxMacroSummary {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  goalLabel: string;
}

export interface FitmaxWorkoutDay {
  day: string;
  short: string;
  full: string;
  type: 'training' | 'rest';
}

export interface FitmaxExercise {
  name: string;
  setsReps: string;
  formNote: string;
  equipment: string;
}
