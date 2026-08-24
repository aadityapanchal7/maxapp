/**
 * XpProgressCard — the primary XP + rank surface (Profile). Shows the earned
 * RANK (with its ivory-marble + gold 3D icon, gently floating), the current
 * level, a progress bar toward the next level, and today's XP. Craft palette:
 * cream card, ink text, glassy-black progress fill (shared with the Profile
 * maxes bar). Renders nothing until the gamification block loads (cold-start
 * invisible).
 */
import React, { useEffect } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Image } from 'expo-image';
import Animated, {
    Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming,
} from 'react-native-reanimated';
import GlassBar from './glass/GlassBar';
import { fonts } from '../theme/dark';
import type { Gamification } from '../services/api';

const INK = '#111113';
const SUB = '#6B6B6B';
const MUTE = '#9A9A9A';
const CARD = '#F1F1EF';
const TRACK = '#E4E3E0';

// The 3D rank icons (Higgsfield ivory-marble + gold, keyed to transparent).
const RANK_ICONS: Record<string, any> = {
    Mortal: require('../assets/ranks/mortal.webp'),
    Aspirant: require('../assets/ranks/aspirant.webp'),
    Champion: require('../assets/ranks/champion.webp'),
    Hero: require('../assets/ranks/hero.webp'),
    Demigod: require('../assets/ranks/demigod.webp'),
    Titan: require('../assets/ranks/titan.webp'),
    Olympian: require('../assets/ranks/olympian.webp'),
};

export default function XpProgressCard({ data }: { data: Gamification | null | undefined }) {
    const nav = useNavigation<any>();
    // A gentle "floating" idle: a soft vertical bob + slight tilt, looped.
    const t = useSharedValue(0);
    useEffect(() => {
        t.value = withRepeat(
            withTiming(1, { duration: 2800, easing: Easing.inOut(Easing.sin) }),
            -1,
            true,
        );
    }, [t]);
    const floatStyle = useAnimatedStyle(() => ({
        transform: [
            { translateY: (t.value - 0.5) * 8 },
            { rotateZ: `${(t.value - 0.5) * 5}deg` },
        ],
    }));

    if (!data) return null;

    const { current_level, rank, xp_into_level, xp_for_next_level, xp_earned_today, is_max_level } = data;
    const mult = data.streak_multiplier ?? 1;
    const pct = is_max_level
        ? 1
        : Math.max(0, Math.min(1, xp_for_next_level > 0 ? xp_into_level / xp_for_next_level : 0));
    const icon = RANK_ICONS[rank] ?? RANK_ICONS.Mortal;

    return (
        <View style={s.card}>
            <View style={s.topRow}>
                <View style={{ flex: 1 }}>
                    <Text style={s.rank}>{rank}</Text>
                    <Text style={s.level}>Level {current_level}</Text>
                    {xp_earned_today > 0 || mult > 1 ? (
                        <Text style={s.today}>
                            {xp_earned_today > 0 ? `+${xp_earned_today.toLocaleString()} XP today` : ''}
                            {xp_earned_today > 0 && mult > 1 ? ' · ' : ''}
                            {mult > 1 ? `×${mult} streak bonus` : ''}
                        </Text>
                    ) : null}
                </View>
                <TouchableOpacity
                    onPress={() => nav.navigate('Ranks')}
                    activeOpacity={0.8}
                    hitSlop={8}
                    accessibilityRole="button"
                    accessibilityLabel="See all ranks"
                >
                    <Animated.View style={[s.iconWrap, floatStyle]}>
                        <Image source={icon} style={s.icon} contentFit="contain" transition={200} />
                    </Animated.View>
                </TouchableOpacity>
            </View>

            <View style={s.barTrack}>
                <GlassBar style={[s.barFill, { width: `${pct * 100}%` }]} radius={6} />
            </View>

            <Text style={s.progressText}>
                {is_max_level
                    ? 'Max rank reached'
                    : `${xp_into_level.toLocaleString()} / ${xp_for_next_level.toLocaleString()} XP to level ${current_level + 1}`}
            </Text>
        </View>
    );
}

const s = StyleSheet.create({
    card: {
        backgroundColor: CARD,
        borderRadius: 18,
        borderCurve: 'continuous',
        paddingHorizontal: 18,
        paddingVertical: 18,
        marginBottom: 14,
    },
    topRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
    rank: { fontFamily: fonts.serif, fontSize: 26, color: INK, letterSpacing: -0.3 },
    level: { fontFamily: fonts.sansMedium, fontSize: 13, color: SUB, marginTop: 3, letterSpacing: 0.2 },
    today: { fontFamily: fonts.sansSemiBold, fontSize: 12, color: '#8A6D2E', marginTop: 6 },
    iconWrap: { width: 72, height: 72, alignItems: 'center', justifyContent: 'center' },
    icon: { width: 72, height: 72 },
    // 12pt, not the old 8: glass needs thickness to read as a rod (see GlassBar).
    barTrack: { height: 12, borderRadius: 6, backgroundColor: TRACK, overflow: 'hidden' },
    barFill: { height: '100%', borderRadius: 6 },
    progressText: { fontFamily: fonts.sans, fontSize: 12.5, color: MUTE, marginTop: 9 },
});
