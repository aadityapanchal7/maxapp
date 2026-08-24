/**
 * GlassBar — a progress/segment fill rendered as black liquid glass.
 *
 * The canonical <LiquidGlassFill> is tuned for CARDS: its corner speculars are
 * radial gradients sized as a % of the surface, so on a 300×10 bar they smear
 * into a broad left-side wash instead of reading as glints. So this composes the
 * house optics with `corners={false}` and adds the highlight a bar actually
 * needs: a cylindrical gleam, which is what makes a pill read as a rounded ROD
 * of glass rather than a flat dark stripe.
 *
 * Layering (bottom → top):
 *   1. The obsidian ramp — `glassBlackAt(from→to)`. Callers pass their slice of
 *      one continuous ramp, so a row of bars reads as a single piece of glass.
 *   2. LiquidGlassFill (dark) — the real iOS material, top sheen, luminous rims,
 *      inner bottom shadow. Shared with every other glass surface in the app.
 *   3. A cylindrical gleam — bright along the bar's centre-line and tapering to
 *      nothing at both ends, clipped to the upper band. This is the curvature
 *      cue: flat sheets get an even sheen, tubes get a hot line.
 *   4. A bottom bounce — light that has travelled through the glass and caught
 *      the lower edge. Sells thickness.
 *   5. A travelling specular sweep — a slim angled light band crossing the bar
 *      every ~5s (Reanimated, UI-thread). Slow and rare so it reads as light
 *      moving on glass, not a loading shimmer.
 *
 * Everything is decorative and pointer-transparent.
 */
import React, { useEffect, useState } from 'react';
import { View, StyleSheet, Platform, type StyleProp, type ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
    Easing, useAnimatedStyle, useSharedValue, withDelay, withRepeat, withSequence, withTiming,
} from 'react-native-reanimated';
import { LiquidGlassFill } from './LiquidGlass';
import { glassBlackAt } from '../../theme/dark';

export type GlassBarProps = {
    /** Start position (0→1) on the shared obsidian ramp. */
    from?: number;
    /** End position (0→1) on the shared obsidian ramp. */
    to?: number;
    /** Sizing (width / height / radius) for the bar. */
    style?: StyleProp<ViewStyle>;
    /** Corner radius; keep >= half the height so the rod stays capsule-ended. */
    radius?: number;
    /**
     * Extra delay (ms) before each sweep pass. Give adjacent bars in a row a
     * rising stagger (i * ~200ms) so the reflection appears to travel across
     * the whole row as one light, instead of every bar flashing in phase.
     */
    sweepDelayMs?: number;
};

export default function GlassBar({ from = 0, to = 1, style, radius = 5, sweepDelayMs = 0 }: GlassBarProps) {
    const [width, setWidth] = useState(0);
    return (
        // OUTER: carries the float shadow and must NOT clip — `overflow:'hidden'`
        // on the rounding layer would clip the view's own shadow away. The
        // backgroundColor is what gives iOS a shape to cast from; every pixel of
        // it is covered by the clipped stack below.
        <View
            style={[
                { borderRadius: radius, borderCurve: 'continuous', backgroundColor: glassBlackAt(to) },
                styles.float,
                style,
            ]}
            pointerEvents="none"
        >
            <View
                style={[StyleSheet.absoluteFill, styles.clip, { borderRadius: radius, borderCurve: 'continuous' }]}
                pointerEvents="none"
                onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
            >
                {/* 1. Obsidian ramp. */}
                <LinearGradient
                    colors={[glassBlackAt(from), glassBlackAt(to)]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={StyleSheet.absoluteFill}
                />

                {/* 2. House glass optics. Intensity is dialled well below the card
                    default: a thin bar has no room to show a blur, and a strong
                    material veil just lifts the black toward grey. */}
                <LiquidGlassFill dark corners={false} intensity={22} spec={0.9} />

                {/* 3. Cylindrical gleam — the curvature cue. */}
                <LinearGradient
                    colors={[
                        'rgba(255,255,255,0)',
                        'rgba(255,255,255,0.34)',
                        'rgba(255,255,255,0.62)',
                        'rgba(255,255,255,0.30)',
                        'rgba(255,255,255,0)',
                    ]}
                    locations={[0, 0.22, 0.5, 0.78, 1]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={styles.gleam}
                />

                {/* 4. Bottom bounce — light through the glass catching the lower edge. */}
                <LinearGradient
                    colors={['rgba(255,255,255,0)', 'rgba(214,226,255,0.22)']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 0, y: 1 }}
                    style={styles.bounce}
                />

                {/* 5. Travelling specular — the motion cue. A slim angled light
                    band sweeps the bar every few seconds, like light moving
                    across polished glass. Slow + rare on purpose: a constant
                    shimmer reads as a loading skeleton, not a material. */}
                {width > 0 ? <SweepGleam width={width} delayMs={sweepDelayMs} /> : null}
            </View>
        </View>
    );
}

function SweepGleam({ width, delayMs }: { width: number; delayMs: number }) {
    // The band starts fully off the left edge and exits off the right.
    const band = Math.max(28, width * 0.22);
    const x = useSharedValue(-band);
    useEffect(() => {
        x.value = -band;
        // ~1.6s sweep, then rest ~3.4s — one pass every 5s. withSequence puts
        // the rest INSIDE the repeated unit so the pause recurs between passes.
        // The stagger (delayMs) is applied ONCE, outside the repeat: inside it
        // would stretch this bar's cycle and the row would drift out of phase.
        x.value = withDelay(
            delayMs,
            withRepeat(
                withSequence(
                    withDelay(3_400, withTiming(-band, { duration: 0 })),
                    withTiming(width + band, { duration: 1_600, easing: Easing.inOut(Easing.quad) }),
                ),
                -1,
                false,
            ),
        );
        // Reanimated cancels the loop on unmount; re-arm if the bar resizes.
    }, [band, width, delayMs, x]);

    const anim = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }, { skewX: '-18deg' }] }));

    return (
        <Animated.View pointerEvents="none" style={[styles.sweep, { width: band }, anim]}>
            <LinearGradient
                colors={['rgba(255,255,255,0)', 'rgba(255,255,255,0.38)', 'rgba(255,255,255,0)']}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 0 }}
                style={StyleSheet.absoluteFill}
            />
        </Animated.View>
    );
}

const styles = StyleSheet.create({
    clip: { overflow: 'hidden' },
    // Tight and low-opacity: a bar sits close to the surface, so a card-sized
    // float shadow would read as a smudge rather than lift.
    float: Platform.select({
        ios: { shadowColor: '#0B0B12', shadowOpacity: 0.30, shadowRadius: 4, shadowOffset: { width: 0, height: 2 } },
        default: { elevation: 3 },
    })!,
    // Sits just below the top rim so the rim stays the brightest line, and stops
    // well short of the middle — a gleam that reaches halfway reads as a flat
    // sheet catching light, not a tube.
    gleam: { position: 'absolute', left: 0, right: 0, top: 1.5, height: '32%' },
    bounce: { position: 'absolute', left: 0, right: 0, bottom: 0, height: '28%' },
    sweep: { position: 'absolute', top: 0, bottom: 0, left: 0 },
});
