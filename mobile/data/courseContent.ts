/**
 * Course-content schema + module registry.
 *
 * Each maxx ships its course in its own file under `./courses/{id}.ts`.
 * Adding a new module:
 *   1. Create `./courses/{id}.ts` exporting a `CourseModule`
 *   2. Import it here and register it in the COURSES map
 * The TOC + Reader render uniformly from this shape — no UI changes.
 */

/* -------------------------------------------------------------------------- */
/*  Types                                                                     */
/* -------------------------------------------------------------------------- */

export type CourseSection = {
    /** Slug, e.g. "what-skin-is". Stable across renders. */
    id: string;
    /** Outline number, e.g. "1.1". */
    number: string;
    /** Slide title — Playfair serif, ≤ 28 chars. */
    title: string;
    /** One-sentence framing, ≤ 110 chars. */
    subtitle: string;
    /** Ionicons -outline name. */
    icon: string;
    /** 4–6 short bullets. Keep each ≤ 90 chars. */
    bullets: string[];
    /** Optional longer paragraph for high-depth sections. */
    body?: string;
    /** "3 min", "1 min", etc. — surfaced as a small pill. */
    eta?: string;
};

export type CourseChapter = {
    id: string;
    /** 1-indexed. */
    number: number;
    title: string;
    subtitle: string;
    /** Ionicons -outline icon for the TOC row. */
    icon: string;
    sections: CourseSection[];
};

export type CourseModule = {
    maxxId: 'skinmax' | 'hairmax' | 'fitmax' | 'bonemax' | 'heightmax';
    /** Single accent color the entire course view tints with. */
    accent: string;
    /** ~10% opacity tint of `accent` for soft backgrounds. */
    accentSoft: string;
    /** ~18% opacity tint for borders / mid-strength highlights. */
    accentMid: string;
    /** Pre-TOC caption (legacy — most surfaces no longer render this). */
    caption?: string;
    chapters: CourseChapter[];
};

/* -------------------------------------------------------------------------- */
/*  Registry                                                                  */
/* -------------------------------------------------------------------------- */

import { SKINMAX_COURSE } from './courses/skinmax';
import { HAIRMAX_COURSE } from './courses/hairmax';
import { FITMAX_COURSE } from './courses/fitmax';
import { BONEMAX_COURSE } from './courses/bonemax';
import { HEIGHTMAX_COURSE } from './courses/heightmax';

const COURSES: Record<string, CourseModule> = {
    skinmax: SKINMAX_COURSE,
    hairmax: HAIRMAX_COURSE,
    fitmax: FITMAX_COURSE,
    bonemax: BONEMAX_COURSE,
    heightmax: HEIGHTMAX_COURSE,
};

export function getCourseForMaxx(maxxId: string): CourseModule | null {
    return COURSES[maxxId] ?? null;
}

/** Flatten chapters into a single ordered section list with chapter context. */
export function flattenSections(course: CourseModule): Array<{
    chapter: CourseChapter;
    section: CourseSection;
    globalIndex: number;
}> {
    const out: Array<{
        chapter: CourseChapter;
        section: CourseSection;
        globalIndex: number;
    }> = [];
    let i = 0;
    for (const ch of course.chapters) {
        for (const s of ch.sections) {
            out.push({ chapter: ch, section: s, globalIndex: i++ });
        }
    }
    return out;
}

/* Re-export the bundled modules so callers can grab a specific one. */
export { SKINMAX_COURSE, HAIRMAX_COURSE, FITMAX_COURSE, BONEMAX_COURSE, HEIGHTMAX_COURSE };
