/**
 * Flat, quiet surfaces — no gradients.
 */
import type { ViewStyle } from 'react-native';
import { colors, borderRadius } from './dark';

export const screenTopWashGradient = {
    colors: [colors.background, colors.background, colors.background] as [string, string, string],
    locations: [0, 0.5, 1] as [number, number, number],
    start: { x: 0, y: 0 },
    end: { x: 1, y: 1 },
};

export const elevatedCardSurface: ViewStyle = {
    backgroundColor: colors.card,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.border,
};
