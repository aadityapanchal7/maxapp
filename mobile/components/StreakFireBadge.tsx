/**
 * Streak badge: single-color Ionicons flame + centered count (flat, minimal detail).
 */
import React, { useEffect, useState } from 'react';
import { AccessibilityInfo, Platform, View, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Text as SvgText } from 'react-native-svg';
import { colors } from '../theme/dark';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

const AnimatedView = Animated.createAnimatedComponent(View);

type Props = {
  streakDays: number;
  variant?: 'header' | 'hero';
};

const FLAME_ACTIVE = '#F97316';
const FLAME_INACTIVE = colors.textMuted;

const VARIANT_DIM = {
  header: { box: 40, flameSize: 28, numSize: 11, numLineHeight: 13 },
  hero: { box: 46, flameSize: 32, numSize: 12, numLineHeight: 14 },
} as const;

export function StreakFireBadge({ streakDays, variant = 'header' }: Props) {
  const dim = VARIANT_DIM[variant];
  const display = streakDays > 999 ? '999+' : String(Math.max(0, streakDays));
  const inactive = streakDays <= 0;
  const narrow = display.length >= 3;

  const floatY = useSharedValue(0);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void AccessibilityInfo.isReduceMotionEnabled().then((v) => {
      if (!cancelled) setReduceMotion(v);
    });
    const sub = AccessibilityInfo.addEventListener?.('reduceMotionChanged', setReduceMotion);
    return () => {
      cancelled = true;
      sub?.remove?.();
    };
  }, []);

  useEffect(() => {
    if (reduceMotion) {
      floatY.value = 0;
      return;
    }
    floatY.value = withRepeat(
      withSequence(
        withTiming(-0.55, { duration: 2800, easing: Easing.inOut(Easing.sin) }),
        withTiming(0.55, { duration: 2800, easing: Easing.inOut(Easing.sin) }),
      ),
      -1,
      true,
    );
  }, [floatY, reduceMotion]);

  const flameMotion = useAnimatedStyle(() => ({
    transform: [{ translateY: floatY.value }],
  }));

  const fontSize = narrow ? dim.numSize - 1 : dim.numSize;
  const flameColor = inactive ? FLAME_INACTIVE : FLAME_ACTIVE;
  /** Optical vertical center for SVG text baseline */
  const numCenterY = dim.box / 2 + fontSize * 0.32;

  return (
    <View
      style={[styles.wrap, { width: dim.box, height: dim.box }]}
      accessibilityLabel={`${streakDays} day streak`}
      accessibilityRole="image"
    >
      <View style={[styles.stack, { width: dim.box, height: dim.box }]}>
        <AnimatedView style={[styles.flameAnim, flameMotion]}>
          <Ionicons
            name="flame"
            size={dim.flameSize}
            color={flameColor}
            accessibilityElementsHidden
          />
        </AnimatedView>
        <View style={styles.numOverlay} pointerEvents="none">
          <Svg width={dim.box} height={dim.box} viewBox={`0 0 ${dim.box} ${dim.box}`}>
            <SvgText
              x={dim.box / 2}
              y={numCenterY}
              textAnchor="middle"
              fontSize={fontSize}
              fontWeight="800"
              letterSpacing={narrow ? -0.5 : 0}
              fill="#FFFFFF"
              stroke="#000000"
              strokeWidth={0.45}
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={inactive ? 0.85 : 1}
              fontFamily={Platform.OS === 'ios' ? 'System' : 'sans-serif'}
            >
              {display}
            </SvgText>
          </Svg>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  stack: {
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  flameAnim: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  numOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
