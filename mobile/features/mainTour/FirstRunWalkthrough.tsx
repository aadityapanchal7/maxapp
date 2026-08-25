/**
 * FirstRunWalkthrough — the guided first-actions overlay a brand-new user sees
 * on their first landing on Home (replaces the old five-stop spotlight tour).
 *
 * Philosophy: don't point at chrome, hand them their first WINS. Three steps,
 * each with one real action:
 *   1. "your plan is live" — confirms the auto-enrolled max landed (or that
 *      it's still building — the funnel-completion pass is async).
 *   2. "start with this" — their actual first task, one tap from TaskGuide.
 *      Skipped entirely when the plan hasn't landed yet.
 *   3. "max knows your setup" — the funnel conversation is saved in chat;
 *      one tap opens it.
 *
 * Visual: dim scrim + a bottom ink card in the editorial voice (Fraunces
 * serif title, Matter body, lowercase copy), progress dots, white pill CTA.
 * All-or-nothing overlay, no anchors, no measuring — it cannot trap touches
 * (the scrim itself advances on tap).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, fonts, borderRadius } from '../../theme/dark';

export type WalkthroughFirstTask = { title: string; time?: string | null } | null;

type Props = {
    visible: boolean;
    /** Label of the max the funnel auto-enrolled ("Skinmax"), if it landed. */
    maxxLabel: string | null;
    /** Today's first pending task, when the plan has landed. */
    firstTask: WalkthroughFirstTask;
    /** Open the first task in TaskGuide (caller owns navigation). */
    onOpenFirstTask: () => void;
    /** Jump to the Max chat tab. */
    onOpenChat: () => void;
    /** Walkthrough finished (any exit) — persist + hide. */
    onFinish: () => void;
};

type Step = {
    key: string;
    title: string;
    body: string;
    primary: string;
    onPrimary: 'next' | 'task' | 'chat';
    secondary?: string;   // always finishes
};

export default function FirstRunWalkthrough({
    visible, maxxLabel, firstTask, onOpenFirstTask, onOpenChat, onFinish,
}: Props) {
    const insets = useSafeAreaInsets();
    // Current step tracked by KEY, not index: the steps array is LIVE (the
    // "start with this" step inserts itself when the funnel-completion pass
    // lands the first task), and an index would swap the card's content under
    // the user mid-read. A key keeps the visible card stable while new steps
    // slot in around it.
    const [stepKey, setStepKey] = useState('plan');

    const steps = useMemo<Step[]>(() => {
        const s: Step[] = [];
        s.push({
            key: 'plan',
            title: 'your plan is live',
            body: maxxLabel
                ? `${maxxLabel.toLowerCase()} is on your planner, built around your real hours.`
                : 'max is building your day one right now — it lands on your planner in a moment.',
            primary: 'show me',
            onPrimary: 'next',
        });
        if (firstTask) {
            const when = (firstTask.time || '').trim();
            s.push({
                key: 'task',
                title: 'start with this',
                body: `“${firstTask.title.toLowerCase()}”${when ? ` at ${when}` : ''}. open it and max walks you through.`,
                primary: 'open it',
                onPrimary: 'task',
                secondary: 'later',
            });
        }
        s.push({
            key: 'chat',
            title: 'max knows your setup',
            body: 'everything you answered during setup is saved in chat. ask max to tweak any part of your day.',
            primary: 'open chat',
            onPrimary: 'chat',
            secondary: 'i’m set',
        });
        return s;
    }, [maxxLabel, firstTask]);

    const idx = Math.max(0, steps.findIndex((s) => s.key === stepKey));
    const step = steps[idx];

    // Entrance / step-change animation: card slides up + fades.
    const anim = useRef(new Animated.Value(0)).current;
    useEffect(() => {
        if (!visible) return;
        anim.setValue(0);
        Animated.timing(anim, {
            toValue: 1, duration: 320, easing: Easing.out(Easing.cubic), useNativeDriver: true,
        }).start();
    }, [visible, stepKey, anim]);

    if (!visible) return null;

    const advance = () => {
        if (idx < steps.length - 1) setStepKey(steps[idx + 1].key);
        else onFinish();
    };

    const handlePrimary = () => {
        if (step.onPrimary === 'task') { onFinish(); onOpenFirstTask(); return; }
        if (step.onPrimary === 'chat') { onFinish(); onOpenChat(); return; }
        advance();
    };

    return (
        <View style={StyleSheet.absoluteFill} pointerEvents="auto">
            {/* Scrim — tapping it advances (never a dead backdrop). */}
            <Pressable style={s.scrim} onPress={advance} accessibilityLabel="Continue walkthrough" />
            <Animated.View
                style={[
                    s.card,
                    { paddingBottom: 20 + insets.bottom },
                    {
                        opacity: anim,
                        transform: [{
                            translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [36, 0] }),
                        }],
                    },
                ]}
                testID="first-run-walkthrough"
            >
                <Text style={s.kicker}>getting started</Text>
                <Text style={s.title}>{step.title}</Text>
                <Text style={s.body}>{step.body}</Text>

                <View style={s.row}>
                    <View style={s.dots}>
                        {steps.map((st, i) => (
                            <View key={st.key} style={[s.dot, i === idx && s.dotActive]} />
                        ))}
                    </View>
                    <View style={s.actions}>
                        {step.secondary ? (
                            <TouchableOpacity onPress={advance} hitSlop={10} accessibilityRole="button">
                                <Text style={s.secondary}>{step.secondary}</Text>
                            </TouchableOpacity>
                        ) : null}
                        <TouchableOpacity
                            style={s.primaryBtn}
                            onPress={handlePrimary}
                            accessibilityRole="button"
                            testID="walkthrough-primary"
                        >
                            <Text style={s.primaryText}>{step.primary}</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            </Animated.View>
        </View>
    );
}

const s = StyleSheet.create({
    scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.45)' },
    card: {
        position: 'absolute', left: 12, right: 12, bottom: 12,
        backgroundColor: colors.foreground,
        borderRadius: borderRadius.lg + 4,
        borderCurve: 'continuous',
        paddingHorizontal: 22, paddingTop: 22,
        shadowColor: '#000', shadowOpacity: 0.35, shadowRadius: 24, shadowOffset: { width: 0, height: 12 },
        elevation: 10,
    },
    kicker: {
        fontFamily: fonts.sansMedium, fontSize: 11, letterSpacing: 1.6,
        textTransform: 'uppercase', color: 'rgba(255,255,255,0.45)', marginBottom: 8,
    },
    title: { fontFamily: fonts.serif, fontSize: 26, color: colors.buttonText, letterSpacing: -0.4 },
    body: {
        fontFamily: fonts.sans, fontSize: 14.5, lineHeight: 21,
        color: 'rgba(255,255,255,0.72)', marginTop: 8, marginBottom: 20,
    },
    row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
    dots: { flexDirection: 'row', gap: 6 },
    dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.25)' },
    dotActive: { backgroundColor: colors.buttonText },
    actions: { flexDirection: 'row', alignItems: 'center', gap: 18 },
    secondary: { fontFamily: fonts.sansMedium, fontSize: 13.5, color: 'rgba(255,255,255,0.55)' },
    primaryBtn: {
        backgroundColor: colors.buttonText, borderRadius: borderRadius.full,
        paddingHorizontal: 20, paddingVertical: 11,
    },
    primaryText: { fontFamily: fonts.sansMedium, fontSize: 14.5, color: colors.foreground },
});
