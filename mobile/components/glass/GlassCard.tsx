/**
 * GlassCard - a flat paper surface (Craft aesthetic). Despite the legacy name
 * there is no glass: a white card on a warm hairline border with a whisper-soft
 * shadow. The `intensity`/`tint` props are kept as no-ops for API compat so no
 * caller has to change.
 *
 * Two layers: the outer view carries the shadow (needs overflow visible); the
 * inner view clips content to the rounded shape. borderCurve 'continuous'
 * gives the iOS squircle corner.
 *
 * Plain react-native Views (was tamagui — its only consumers were this file
 * and GlassButton, so the dependency was dropped; token values are inlined:
 * $glass #FFFFFF, $glassBorder #E8E0D3).
 */
import React from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';

type GlassCardProps = {
    children?: React.ReactNode;
    intensity?: number;
    tint?: 'light' | 'dark' | 'default';
    radius?: number;
    style?: StyleProp<ViewStyle>;
};

export function GlassCard({
    children,
    intensity: _intensity,
    tint: _tint,
    radius = 18,
    style,
}: GlassCardProps) {
    return (
        <View
            style={[
                {
                    borderRadius: radius,
                    borderCurve: 'continuous',
                    shadowColor: '#2E2A20',
                    shadowOpacity: 0.07,
                    shadowRadius: 18,
                    shadowOffset: { width: 0, height: 8 },
                },
                style,
            ]}
        >
            <View
                style={{
                    backgroundColor: '#FFFFFF',
                    borderRadius: radius,
                    borderCurve: 'continuous',
                    overflow: 'hidden',
                    borderWidth: 1,
                    borderColor: '#E8E0D3',
                }}
            >
                {children}
            </View>
        </View>
    );
}

export default GlassCard;
