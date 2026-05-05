/**
 * Inline slider input rendered below a chat bubble when the assistant asks
 * a numeric question (e.g. "how old are you?").
 *
 * Backend protocol — see ChatResponse.input_widget on the server:
 *   {
 *     type: "slider",
 *     min: 13,
 *     max: 50,
 *     step: 1,
 *     default: 18,
 *     label: "How old are you?",
 *     unit: ""
 *   }
 *
 * UX notes — the previous version was controlled on every drag tick, which
 * caused the thumb to fight the user's finger on iOS (state update → re-render
 * → re-snap to last-committed value). Now the underlying slider is internally
 * uncontrolled after first mount: we read its drag value via onValueChange to
 * update the displayed number, and only commit to React state on
 * onSlidingComplete (or release on web). This makes scrubbing feel native.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, fonts, spacing } from '../theme/dark';

export interface SliderSpec {
    type: 'slider';
    min: number;
    max: number;
    step: number;
    default: number;
    label: string;
    unit?: string;
}

interface Props {
    spec: SliderSpec;
    onSubmit: (value: number) => void;
    disabled?: boolean;
}

export default function ChatSliderInput({ spec, onSubmit, disabled }: Props) {
    const initial = clamp(spec.default ?? Math.round((spec.min + spec.max) / 2), spec.min, spec.max);
    const [committedValue, setCommittedValue] = useState<number>(initial);
    const [displayValue, setDisplayValue] = useState<number>(initial);

    // Sync if the spec ever changes (e.g. server re-asks a different field).
    useEffect(() => {
        const next = clamp(spec.default ?? Math.round((spec.min + spec.max) / 2), spec.min, spec.max);
        setCommittedValue(next);
        setDisplayValue(next);
    }, [spec.min, spec.max, spec.default]);

    const submit = () => {
        if (disabled) return;
        onSubmit(committedValue);
    };

    return (
        <View style={styles.container}>
            <View style={styles.valueRow}>
                <Text style={styles.value}>{displayValue}</Text>
                {spec.unit ? <Text style={styles.unit}>{spec.unit}</Text> : null}
            </View>
            <SliderTrack
                min={spec.min}
                max={spec.max}
                step={spec.step}
                initialValue={initial}
                onChangeLive={setDisplayValue}
                onCommit={setCommittedValue}
                disabled={disabled}
            />
            <View style={styles.scaleRow}>
                <Text style={styles.scaleText}>{spec.min}</Text>
                <Text style={styles.scaleText}>{spec.max}</Text>
            </View>
            <Pressable
                onPress={submit}
                disabled={disabled}
                style={({ pressed }) => [
                    styles.submit,
                    disabled && styles.submitDisabled,
                    pressed && !disabled && styles.submitPressed,
                ]}
                accessibilityRole="button"
                accessibilityLabel={`Submit ${committedValue}`}
            >
                <Text style={styles.submitText}>Confirm</Text>
                <Ionicons name="arrow-forward" size={14} color={colors.foreground} />
            </Pressable>
        </View>
    );
}

// --------------------------------------------------------------------------- //
//  Track — web uses native range input; native uses @rn-community/slider when
//  available, falls back to a tap-to-pick row on platforms without it.
// --------------------------------------------------------------------------- //

interface TrackProps {
    min: number;
    max: number;
    step: number;
    initialValue: number;
    onChangeLive: (v: number) => void;
    onCommit: (v: number) => void;
    disabled?: boolean;
}

function SliderTrack({ min, max, step, initialValue, onChangeLive, onCommit, disabled }: TrackProps) {
    if (Platform.OS === 'web') {
        return (
            <View style={styles.trackWeb}>
                {/* @ts-expect-error - native HTML element under RN-Web */}
                <input
                    type="range"
                    min={min}
                    max={max}
                    step={step}
                    defaultValue={initialValue}
                    disabled={disabled}
                    onInput={(e: any) => {
                        const v = Number(e.target.value);
                        onChangeLive(v);
                    }}
                    onChange={(e: any) => {
                        const v = Number(e.target.value);
                        onChangeLive(v);
                        onCommit(v);
                    }}
                    style={{
                        // Bumped to 44 so the rail is taller + thumb is easier
                        // to land on. Width-100% lets the slider use the full
                        // chat-pane width so drag distance per step is bigger
                        // and granular values are easier to nail.
                        width: '100%',
                        height: 44,
                        accentColor: colors.foreground,
                        cursor: disabled ? 'not-allowed' : 'pointer',
                        touchAction: 'none',
                    }}
                />
            </View>
        );
    }

    // Native fallback: try @rn-community/slider, else tap rail.
    let CommunitySlider: any = null;
    try {
        // Lazy require so web bundling doesn't try to resolve the native module.
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        CommunitySlider = require('@react-native-community/slider').default;
    } catch {
        CommunitySlider = null;
    }
    if (CommunitySlider) {
        // Throttle live display updates so we don't blow the bridge with 60fps
        // numeric updates while the user is dragging.
        const lastEmitRef = useRef(0);
        return (
            <View style={styles.trackNative}>
                <CommunitySlider
                    minimumValue={min}
                    maximumValue={max}
                    step={step}
                    // value is intentionally NOT bound after mount — passing it
                    // on every render fights the user's finger on iOS.
                    value={initialValue}
                    disabled={disabled}
                    onValueChange={(v: number) => {
                        const now = Date.now();
                        if (now - lastEmitRef.current < 33) return;
                        lastEmitRef.current = now;
                        const snapped = step > 0 ? Math.round(v / step) * step : v;
                        onChangeLive(snapped);
                    }}
                    onSlidingComplete={(v: number) => {
                        const snapped = step > 0 ? Math.round(v / step) * step : v;
                        onChangeLive(snapped);
                        onCommit(snapped);
                    }}
                    minimumTrackTintColor={colors.foreground}
                    maximumTrackTintColor={colors.divider ?? '#d4d4d4'}
                    thumbTintColor={colors.foreground}
                    // Taller rail so the thumb is easier to grab; full width
                    // gives more horizontal travel per step (granular values
                    // become easier to land on).
                    style={{ width: '100%', height: 44 }}
                />
            </View>
        );
    }
    // Tap rail (very last-resort): show a few snap points.
    const snaps: number[] = [];
    const stepCount = Math.min(11, Math.floor((max - min) / step) + 1);
    for (let i = 0; i < stepCount; i++) {
        snaps.push(min + Math.round((i / Math.max(1, stepCount - 1)) * (max - min) / step) * step);
    }
    return (
        <View style={styles.snapRow}>
            {snaps.map((s) => (
                <Pressable
                    key={s}
                    onPress={() => {
                        if (disabled) return;
                        onChangeLive(s);
                        onCommit(s);
                    }}
                    style={({ pressed }) => [
                        styles.snap,
                        pressed && styles.snapPressed,
                    ]}
                >
                    <Text style={styles.snapText}>{s}</Text>
                </Pressable>
            ))}
        </View>
    );
}

function clamp(v: number, lo: number, hi: number): number {
    return Math.max(lo, Math.min(hi, v));
}

const styles = StyleSheet.create({
    container: {
        marginTop: spacing.sm,
        marginBottom: spacing.md,
        paddingVertical: spacing.lg,
        paddingHorizontal: spacing.xs,
        gap: spacing.sm,
    },
    valueRow: {
        flexDirection: 'row',
        alignItems: 'baseline',
        justifyContent: 'center',
        gap: 6,
        marginBottom: spacing.xs,
    },
    value: {
        fontFamily: fonts.serif,
        fontSize: 56,
        fontWeight: '400',
        color: colors.foreground,
        letterSpacing: -1.5,
        lineHeight: 60,
        includeFontPadding: false,
    },
    unit: {
        fontFamily: fonts.sans,
        fontSize: 14,
        fontWeight: '400',
        color: colors.textMuted ?? '#888',
        letterSpacing: 0.4,
        textTransform: 'lowercase',
    },
    trackWeb: {
        paddingVertical: spacing.sm,
        paddingHorizontal: 2,
        marginTop: spacing.xs,
    },
    trackNative: {
        paddingVertical: spacing.sm,
        paddingHorizontal: 2,
        marginTop: spacing.xs,
    },
    scaleRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        paddingHorizontal: 2,
        marginTop: -spacing.xs,
    },
    scaleText: {
        fontSize: 11,
        color: colors.textMuted ?? '#888',
        letterSpacing: 0.5,
        opacity: 0.7,
    },
    snapRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 6,
        paddingVertical: spacing.xs,
        justifyContent: 'center',
    },
    snap: {
        paddingVertical: 6,
        paddingHorizontal: 12,
        borderRadius: 999,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border ?? '#2a2a2a',
        backgroundColor: 'transparent',
    },
    snapPressed: {
        opacity: 0.7,
    },
    snapText: {
        fontSize: 13,
        color: colors.foreground,
    },
    submit: {
        marginTop: spacing.md,
        paddingVertical: 10,
        paddingHorizontal: spacing.lg,
        borderRadius: 999,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border ?? '#2a2a2a',
        backgroundColor: 'transparent',
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        alignSelf: 'center',
    },
    submitPressed: {
        opacity: 0.6,
    },
    submitDisabled: {
        opacity: 0.3,
    },
    submitText: {
        color: colors.foreground,
        fontWeight: '500',
        fontSize: 13,
        letterSpacing: 0.4,
        textTransform: 'uppercase',
    },
});
