/**
 * Luxury minimalist design system
 * Off-white / near-black / serif headlines
 */

export const colors = {
    background: '#F5F5F3',
    surface: '#EEEEE9',
    surfaceLight: '#E8E8E3',
    card: '#FAFAF8',

    foreground: '#0A0A0A',
    primary: '#0A0A0A',
    primaryLight: '#1A1A1A',
    primaryDark: '#000000',

    accent: '#0A0A0A',
    accentLight: '#1A1A1A',
    accentMuted: 'rgba(10, 10, 10, 0.04)',

    textPrimary: '#0A0A0A',
    textSecondary: '#6B6B63',
    textMuted: '#9C9C94',

    success: '#3D6B4F',
    warning: '#A68A3E',
    error: '#8B3A3A',
    info: '#3A5F8B',

    premium: '#8B7355',
    premiumLight: '#8B735510',
    premiumBorder: '#8B735530',

    border: '#E0DED8',
    borderLight: '#EEEEE9',
    divider: '#E0DED8',

    gradientStart: '#F5F5F3',
    gradientEnd: '#EEEEE9',

    buttonText: '#FAFAF8',

    overlay: 'rgba(0, 0, 0, 0.35)',
    blur: 'rgba(250, 250, 248, 0.85)',
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
    sm: 6,
    md: 10,
    lg: 14,
    xl: 18,
    '2xl': 22,
    full: 9999,
};

export const fonts = {
    serif: 'PlayfairDisplay',
    sans: 'Matter-Regular',
    sansMedium: 'Matter-Medium',
    sansSemiBold: 'Matter-SemiBold',
    sansBold: 'Matter-Bold',
};

export const typography = {
    h1: {
        fontFamily: fonts.serif,
        fontSize: 34,
        fontWeight: '400' as const,
        color: colors.textPrimary,
        letterSpacing: -0.5,
        lineHeight: 42,
    },
    h2: {
        fontFamily: fonts.serif,
        fontSize: 24,
        fontWeight: '400' as const,
        color: colors.textPrimary,
        letterSpacing: -0.3,
        lineHeight: 32,
    },
    h3: {
        fontFamily: fonts.serif,
        fontSize: 18,
        fontWeight: '400' as const,
        color: colors.textPrimary,
        letterSpacing: -0.15,
        lineHeight: 26,
    },
    body: {
        fontSize: 15,
        fontWeight: '400' as const,
        color: colors.textPrimary,
        lineHeight: 24,
    },
    bodySmall: {
        fontSize: 13,
        fontWeight: '400' as const,
        color: colors.textSecondary,
        lineHeight: 20,
    },
    caption: {
        fontSize: 11,
        fontWeight: '500' as const,
        color: colors.textMuted,
        lineHeight: 16,
    },
    label: {
        fontSize: 10,
        fontWeight: '500' as const,
        color: colors.textMuted,
        letterSpacing: 1.2,
        textTransform: 'uppercase' as const,
    },
    button: {
        fontSize: 14,
        fontWeight: '500' as const,
        color: colors.buttonText,
        letterSpacing: 0.3,
    },
    hero: {
        fontFamily: fonts.serif,
        fontSize: 48,
        fontWeight: '400' as const,
        color: colors.textPrimary,
        letterSpacing: -1,
        lineHeight: 56,
    },
};

export const shadows = {
    sm: {
        shadowColor: '#0A0A0A',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.03,
        shadowRadius: 3,
        elevation: 1,
    },
    md: {
        shadowColor: '#0A0A0A',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.04,
        shadowRadius: 8,
        elevation: 2,
    },
    lg: {
        shadowColor: '#0A0A0A',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.06,
        shadowRadius: 16,
        elevation: 4,
    },
    xl: {
        shadowColor: '#0A0A0A',
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.08,
        shadowRadius: 24,
        elevation: 6,
    },
};

export default {
    colors,
    spacing,
    borderRadius,
    typography,
    shadows,
    fonts,
};
