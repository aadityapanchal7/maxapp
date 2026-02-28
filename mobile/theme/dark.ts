/**
 * Refined Warm Minimalist Theme
 */

export const colors = {
    background: '#FAFAF7',
    surface: '#F3F2EE',
    surfaceLight: '#EFEEE9',
    card: '#F6F5F1',

    primary: '#1A1A1A',
    primaryLight: '#2E2E2E',
    primaryDark: '#0D0D0D',

    accent: '#B8986E',
    accentLight: '#D4BC96',
    accentMuted: 'rgba(184, 152, 110, 0.12)',

    textPrimary: '#1A1A1A',
    textSecondary: '#6E6A63',
    textMuted: '#9E9A93',

    success: '#4CAF72',
    warning: '#D4952B',
    error: '#D45050',
    info: '#5B8FD4',

    border: '#E6E3DD',
    borderLight: '#EDEBE6',
    divider: '#E6E3DD',

    gradientStart: '#FAFAF7',
    gradientEnd: '#F3F2EE',

    buttonText: '#FAFAF7',

    overlay: 'rgba(15, 15, 12, 0.35)',
    blur: 'rgba(250, 250, 247, 0.92)',
};

export const spacing = {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
};

export const borderRadius = {
    sm: 10,
    md: 14,
    lg: 18,
    xl: 26,
    full: 9999,
};

export const typography = {
    h1: {
        fontSize: 30,
        fontFamily: 'Matter-Medium',
        fontWeight: '600' as const,
        color: colors.textPrimary,
        letterSpacing: -0.5,
    },
    h2: {
        fontSize: 22,
        fontFamily: 'Matter-Medium',
        fontWeight: '600' as const,
        color: colors.textPrimary,
        letterSpacing: -0.3,
    },
    h3: {
        fontSize: 18,
        fontFamily: 'Matter-Medium',
        fontWeight: '500' as const,
        color: colors.textPrimary,
    },
    body: {
        fontSize: 15,
        fontFamily: 'Matter-Regular',
        fontWeight: '400' as const,
        color: colors.textPrimary,
        lineHeight: 22,
    },
    bodySmall: {
        fontSize: 13,
        fontFamily: 'Matter-Regular',
        fontWeight: '400' as const,
        color: colors.textSecondary,
        lineHeight: 19,
    },
    caption: {
        fontSize: 11,
        fontFamily: 'Matter-Regular',
        fontWeight: '400' as const,
        color: colors.textMuted,
    },
    button: {
        fontSize: 15,
        fontFamily: 'Matter-Medium',
        fontWeight: '600' as const,
        color: colors.buttonText,
        letterSpacing: 0.3,
    },
};

export const shadows = {
    sm: {
        shadowColor: '#1A1A0F',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.04,
        shadowRadius: 4,
        elevation: 1,
    },
    md: {
        shadowColor: '#1A1A0F',
        shadowOffset: { width: 0, height: 3 },
        shadowOpacity: 0.06,
        shadowRadius: 10,
        elevation: 3,
    },
    lg: {
        shadowColor: '#1A1A0F',
        shadowOffset: { width: 0, height: 6 },
        shadowOpacity: 0.08,
        shadowRadius: 20,
        elevation: 5,
    },
};

export default {
    colors,
    spacing,
    borderRadius,
    typography,
    shadows,
};
