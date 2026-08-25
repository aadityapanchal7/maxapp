/**
 * GlassButton - the CTA primitive for the glassy iOS-native aesthetic.
 *
 * Variants:
 *   primary - solid ink fill, white label (the main action)
 *   glass   - frosted translucent fill with hairline border (secondary)
 *   ghost   - no surface, muted underlined label (tertiary / text link)
 *
 * Built on TouchableOpacity so async handlers, disabled, and loading
 * (ActivityIndicator) behave exactly like the rest of the app.
 */
import React, { useId } from 'react';
import {
    TouchableOpacity,
    ActivityIndicator,
    StyleSheet,
    Text,
    View,
    type StyleProp,
    type ViewStyle,
} from 'react-native';
import { LiquidGlassFill } from './LiquidGlass';

type Variant = 'primary' | 'glass' | 'ghost';

export function GlassButton({
    label,
    onPress,
    variant = 'primary',
    loading = false,
    disabled = false,
    style,
}: {
    label: string;
    onPress?: () => void;
    variant?: Variant;
    loading?: boolean;
    disabled?: boolean;
    style?: StyleProp<ViewStyle>;
}) {
    const radius = 16;
    const glassId = useId().replace(/:/g, '');
    const isGhost = variant === 'ghost';
    const textColor = variant === 'primary' ? '#FFFFFF' : isGhost ? '#8C887E' : '#1C1A17';
    // A disabled button must LOOK disabled - otherwise taps silently no-op
    // and the user blames the app.
    const dimStyle = disabled && !loading ? { opacity: 0.45 } : null;
    const a11yProps = {
        accessibilityRole: 'button' as const,
        accessibilityLabel: label,
        accessibilityState: { disabled: disabled || loading, busy: loading },
    };

    const content = (
        <View
            style={{
                height: isGhost ? 44 : 54,
                alignItems: 'center',
                justifyContent: 'center',
                paddingHorizontal: 20,
                borderRadius: radius,
                borderCurve: 'continuous',
            }}
        >
            {loading ? (
                <ActivityIndicator color={textColor} />
            ) : (
                <Text style={[styles.label, { color: textColor }, isGhost && styles.ghostLabel]}>
                    {label}
                </Text>
            )}
        </View>
    );

    if (variant === 'glass') {
        return (
            <TouchableOpacity
                activeOpacity={0.85}
                onPress={onPress}
                disabled={disabled || loading}
                style={[styles.shadow, style, dimStyle]}
                {...a11yProps}
            >
                <View
                    style={{
                        borderRadius: radius,
                        borderCurve: 'continuous',
                        overflow: 'hidden',
                        borderWidth: 1,
                        borderColor: '#E8E0D3',
                    }}
                >
                    {/* Canonical liquid-glass optics behind the label — same
                        material, speculars and rim as every other glass surface. */}
                    <LiquidGlassFill idSuffix={`btn${glassId}`} />
                    {content}
                </View>
            </TouchableOpacity>
        );
    }

    if (isGhost) {
        return (
            <TouchableOpacity
                activeOpacity={0.6}
                onPress={onPress}
                disabled={disabled || loading}
                style={[style, dimStyle]}
                {...a11yProps}
            >
                {content}
            </TouchableOpacity>
        );
    }

    return (
        <TouchableOpacity
            activeOpacity={0.9}
            onPress={onPress}
            disabled={disabled || loading}
            style={[styles.shadow, style, dimStyle]}
            {...a11yProps}
        >
            <View style={{ backgroundColor: '#1C1A17', borderRadius: radius, borderCurve: 'continuous' }}>
                {content}
            </View>
        </TouchableOpacity>
    );
}

const styles = StyleSheet.create({
    label: { fontFamily: 'Matter-SemiBold', fontSize: 15, letterSpacing: 0.3 },
    ghostLabel: {
        fontFamily: 'Matter-Regular',
        fontSize: 13,
        letterSpacing: 0.2,
        textDecorationLine: 'underline',
    },
    shadow: {
        shadowColor: '#3A352B',
        shadowOpacity: 0.06,
        shadowRadius: 10,
        shadowOffset: { width: 0, height: 4 },
    },
});

export default GlassButton;
