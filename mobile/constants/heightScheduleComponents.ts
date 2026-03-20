/**
 * HeightMax schedule tracks — IDs must match backend HEIGHTMAX_PROTOCOLS keys.
 */
export const HEIGHT_SCHEDULE_COMPONENTS = [
  {
    id: 'posturemaxxing',
    title: 'Posturemaxxing',
    description:
      'Highest-ROI adult height lever because posture changes how your frame reads immediately.',
  },
  {
    id: 'sprintmaxxing',
    title: 'Sprintmaxxing',
    description: 'Frame, leanness, and posture play. Useful, but not bone-length science.',
  },
  {
    id: 'deep_sleep_routine',
    title: 'Deep Sleep Routine',
    description: 'The actual hormone-support habit worth obsessing over.',
  },
  {
    id: 'decompress_lengthen',
    title: 'Decompress / Lengthen',
    description: 'Spinal decompression and posture height, not fake bone growth.',
  },
  {
    id: 'height_killers',
    title: 'Height Killers',
    description:
      'Anti-habit module for the boring stuff that actually wrecks your presentation and recovery.',
  },
  {
    id: 'look_taller_instantly',
    title: 'Look Taller Instantly',
    description:
      'Presentation layer: proportions, outfit choices, and how you read in the mirror.',
  },
] as const;

export type HeightScheduleComponentId = (typeof HEIGHT_SCHEDULE_COMPONENTS)[number]['id'];
