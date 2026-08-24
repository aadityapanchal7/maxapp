/**
 * Sleek modern SaaS design system
 * Clean, shadowed, typographic
 */

// Clean B&W palette: pure white surfaces, near-black ink, neutral grays.
export const colors = {
    background: '#FFFFFF',    // pure white canvas
    surface: '#F2F2F2',      // subtle neutral inset
    surfaceLight: '#F7F7F7',
    card: '#FFFFFF',

    foreground: '#111113',   // near-black ink
    primary: '#111113',
    primaryLight: '#333333',
    primaryDark: '#000000',

    accent: '#2C6BED',       // blue (interactive / selected)
    accentLight: '#5A8CF2',
    accentMuted: 'rgba(44, 107, 237, 0.10)',

    textPrimary: '#111113',
    textSecondary: '#555555',
    textMuted: '#9A9A9A',

    success: '#2F9E60',
    warning: '#B5791C',
    error: '#C0452C',
    info: '#2C6BED',

    premium: '#2C6BED',
    premiumLight: '#2C6BED18',
    premiumBorder: '#2C6BED40',

    border: 'rgba(0,0,0,0.08)',  // neutral hairline
    borderLight: '#EBEBEB',
    divider: '#E5E5E5',

    gradientStart: '#FFFFFF',
    gradientEnd: '#F5F5F5',

    buttonText: '#FFFFFF',

    overlay: 'rgba(0,0,0,0.40)',
    blur: 'rgba(255,255,255,0.9)',
};

export const spacing = {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
    xxxl: 64,
};

export const borderRadius = {
    sm: 10,
    md: 14,
    lg: 18,
    xl: 22,
    '2xl': 28,
    full: 9999,
};

export const typography = {
    h1: {
        fontSize: 32,
        fontWeight: '700' as const,
        color: colors.textPrimary,
        letterSpacing: -0.8,
    },
    h2: {
        fontSize: 22,
        fontWeight: '600' as const,
        color: colors.textPrimary,
        letterSpacing: -0.4,
    },
    h3: {
        fontSize: 17,
        fontWeight: '600' as const,
        color: colors.textPrimary,
        letterSpacing: -0.2,
    },
    body: {
        fontSize: 15,
        fontWeight: '400' as const,
        color: colors.textPrimary,
        lineHeight: 22,
    },
    bodySmall: {
        fontSize: 13,
        fontWeight: '400' as const,
        color: colors.textSecondary,
        lineHeight: 18,
    },
    caption: {
        fontSize: 11,
        fontWeight: '500' as const,
        color: colors.textMuted,
    },
    label: {
        fontSize: 11,
        fontWeight: '600' as const,
        color: colors.textMuted,
        letterSpacing: 0.8,
        textTransform: 'uppercase' as const,
    },
    button: {
        fontSize: 15,
        fontWeight: '600' as const,
        color: colors.buttonText,
        letterSpacing: -0.1,
    },
    hero: {
        fontSize: 48,
        fontWeight: '400' as const,
        color: colors.textPrimary,
        letterSpacing: -2,
    },
};

export const shadows = {
    sm: {
        shadowColor: '#000000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.04,
        shadowRadius: 4,
        elevation: 1,
    },
    md: {
        shadowColor: '#000000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.05,
        shadowRadius: 14,
        elevation: 3,
    },
    lg: {
        shadowColor: '#000000',
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.07,
        shadowRadius: 24,
        elevation: 6,
    },
    xl: {
        shadowColor: '#000000',
        shadowOffset: { width: 0, height: 12 },
        shadowOpacity: 0.09,
        shadowRadius: 36,
        elevation: 9,
    },
};

// ─── Glassy black (Profile progress surfaces) ─────────────────────────────────
// Polished-obsidian ramp: a charcoal highlight edge falling to near-black. Used
// by BOTH profile progress bars (the maxes segment row and the XP bar) so they
// read as one material — hence living here rather than in either screen.
const GLASS_BLACK_STOPS: ReadonlyArray<readonly [number, number, number]> = [
    [66, 66, 74],   // charcoal — the lit edge of the glass
    [36, 36, 43],
    [18, 18, 22],
    [8, 8, 10],     // near-black
];

/** Colour at position `t` (0→1) along the glassy-black ramp. */
export function glassBlackAt(t: number): string {
    const c = Math.max(0, Math.min(1, t));
    // Position along the stop list, then lerp between the two stops we land on.
    const pos = c * (GLASS_BLACK_STOPS.length - 1);
    const i = Math.min(Math.floor(pos), GLASS_BLACK_STOPS.length - 2);
    const f = pos - i;
    const [r0, g0, b0] = GLASS_BLACK_STOPS[i];
    const [r1, g1, b1] = GLASS_BLACK_STOPS[i + 1];
    const mix = (a: number, b: number) => Math.round(a + f * (b - a));
    return `rgb(${mix(r0, r1)}, ${mix(g0, g1)}, ${mix(b0, b1)})`;
}

export const fonts = {
    serif: 'Fraunces',
    serifSemiBold: 'Fraunces-SemiBold',
    serifItalic: 'Fraunces-Italic',
    sans: 'Matter-Regular',
    sansMedium: 'Matter-Medium',
    sansSemiBold: 'Matter-SemiBold',
    sansBold: 'Matter-Bold',
    sansLight: 'Matter-Light',
};

export default {
    colors,
    spacing,
    borderRadius,
    typography,
    shadows,
    fonts,
};
