export interface FitmaxModule {
  id: number;
  title: string;
  phase: string;
  duration: string;
  level: string;
  status: 'locked' | 'available' | 'in_progress' | 'complete';
  content: string;
}

import { FITMAX_MODULES_FULL } from './modules.full';

export const FITMAX_MODULES: FitmaxModule[] = FITMAX_MODULES_FULL;

export function fitmaxPhaseProgress(modules: FitmaxModule[]) {
  const completed = modules.filter(m => m.status === 'complete').length;
  const currentPhase = modules.find(m => m.status === 'available' || m.status === 'in_progress')?.phase || 'Foundation';
  return {
    currentPhase,
    completed,
    total: modules.length,
    ratio: modules.length ? completed / modules.length : 0,
  };
}
