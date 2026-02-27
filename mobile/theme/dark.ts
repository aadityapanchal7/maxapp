/**
 * Dark Theme Configuration
 */

export const colors = {
    // Backgrounds (Figma: #0E0E0E base + gradient)
    background: '#0E0E0E',
    surface: '#171840',
    surfaceLight: '#1E1E4A',
    card: '#1A1A3A',

    // Primary accent (Purple from gradient)
    primary: '#6D37D4',
    primaryLight: '#8B5CF6',
    primaryDark: '#5B2BB8',

    // Text
    textPrimary: '#FFFFFF',
    textSecondary: '#B0B0C0',
    textMuted: '#6B6B80',

    // Status
    success: '#00D26A',
    warning: '#FFB800',
    error: '#FF4757',
    info: '#3498DB',

    // UI Elements
    border: '#2A2A4A',
    borderLight: '#3A3A5A',
    divider: '#252545',

    // Gradients (Figma: #171840 to #6D37D4)
    gradientStart: '#171840',
    gradientEnd: '#6D37D4',

    // Button
    buttonText: '#FFFFFF',

    // Overlay
    overlay: 'rgba(0, 0, 0, 0.7)',
    blur: 'rgba(14, 14, 14, 0.9)',
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
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
    full: 9999,
};

// Typography using Matter font (400 normal, 500 bold)
// Matter-Regular.ttf and Matter-Medium.ttf must be in assets/fonts/
export const typography = {
    h1: {
        fontSize: 32,
        fontFamily: 'Matter-Medium',
        fontWeight: '500' as const,
        color: colors.textPrimary,
    },
    h2: {
        fontSize: 24,
        fontFamily: 'Matter-Medium',
        fontWeight: '500' as const,
        color: colors.textPrimary,
    },
    h3: {
        fontSize: 20,
        fontFamily: 'Matter-Medium',
        fontWeight: '500' as const,
        color: colors.textPrimary,
    },
    body: {
        fontSize: 16,
        fontFamily: 'Matter-Regular',
        fontWeight: '400' as const,
        color: colors.textPrimary,
    },
    bodySmall: {
        fontSize: 14,
        fontFamily: 'Matter-Regular',
        fontWeight: '400' as const,
        color: colors.textSecondary,
    },
    caption: {
        fontSize: 12,
        fontFamily: 'Matter-Regular',
        fontWeight: '400' as const,
        color: colors.textMuted,
    },
    button: {
        fontSize: 16,
        fontFamily: 'Matter-Medium',
        fontWeight: '500' as const,
        color: colors.buttonText,
    },
};

export const shadows = {
    sm: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 2,
    },
    md: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 8,
        elevation: 4,
    },
    lg: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.2,
        shadowRadius: 16,
        elevation: 8,
    },
};

export default {
    colors,
    spacing,
    borderRadius,
    typography,
    shadows,
};
