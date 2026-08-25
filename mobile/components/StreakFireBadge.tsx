/**
 * Streak badge: glossy 3D "jelly" flame (Explore icon language, see c.md) with the
 * day-count centered on top in dark ink + white outline so it reads up to 3 digits.
 */
import React, { useEffect, useState } from 'react';
import { AccessibilityInfo, Platform, View, StyleSheet, Image } from 'react-native';
import Svg, { Text as SvgText } from 'react-native-svg';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

const AnimatedView = Animated.createAnimatedComponent(View);

type Props = {
  streakDays: number;
  variant?: 'header' | 'hero';
};

// Glossy 3D "jelly" streak flame (matches the Explore max-icon language — see
// c.md). Transparent PNG so it floats in the header; the day-count is drawn on
// top in dark ink with a white outline so it reads on the pale glowing core.
const FLAME_SRC = require('../assets/streakFlame.png');

const VARIANT_DIM = {
  header: { box: 40, flameSize: 42, numSize: 12, numLineHeight: 14 },
  hero: { box: 46, flameSize: 48, numSize: 13, numLineHeight: 15 },
} as const;

export function StreakFireBadge({ streakDays, variant = 'header' }: Props) {
  const dim = VARIANT_DIM[variant];
  const display = streakDays > 999 ? '999+' : String(Math.max(0, streakDays));
  const inactive = streakDays <= 0;
  const narrow = display.length >= 3;

  const floatY = useSharedValue(0);
  const pop = useSharedValue(1);
  const [reduceMotion, setReduceMotion] = useState(false);
  const prevStreak = React.useRef(streakDays);

  // Streak v2 (spec 3.5): the badge celebrates the INCREMENT, not just idle
  // float - scale pop 1 -> 1.18 -> 1 (damping 12) + one Success haptic.
  useEffect(() => {
    const prev = prevStreak.current;
    prevStreak.current = streakDays;
    if (streakDays <= prev) return;
    if (!reduceMotion) {
      pop.value = withSequence(
        withSpring(1.18, { damping: 12, stiffness: 220 }),
        withSpring(1, { damping: 12, stiffness: 200 }),
      );
    }
    if (Platform.OS !== 'web') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    }
  }, [streakDays, reduceMotion, pop]);

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
    transform: [{ translateY: floatY.value }, { scale: pop.value }],
  }));

  const fontSize = narrow ? dim.numSize - 1.5 : dim.numSize;
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
          <Image
            source={FLAME_SRC}
            style={{ width: dim.flameSize, height: dim.flameSize, opacity: inactive ? 0.4 : 1 }}
            resizeMode="contain"
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
              fill="#26222B"
              stroke="#FFFFFF"
              strokeWidth={0.85}
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
