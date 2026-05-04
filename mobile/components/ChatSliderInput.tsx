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
 * On submit we fire `onSubmit(value)` and the screen sends the value (as a
 * plain string, e.g. "17") as the next user message. The server-side
 * onboarding_questioner coerces it back into the int answer for the
 * required field.
 *
 * On native we use @react-native-community/slider; on web we fall back to a
 * styled native <input type="range"> wrapped in a Pressable. RN-Web ships
 * View renders cleanly on both — keeping the same JSX path simplifies
 * styling at the cost of a tiny render-branch on Platform.OS.
 */

import React, { useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, spacing } from '../theme/dark';

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
    const [value, setValue] = useState<number>(initial);

    // Sync if the spec ever changes (e.g. server re-asks a different field).
    useEffect(() => {
        setValue(clamp(spec.default ?? Math.round((spec.min + spec.max) / 2), spec.min, spec.max));
    }, [spec.min, spec.max, spec.default]);

    const submit = () => {
        if (disabled) return;
        onSubmit(value);
    };

    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.value}>{value}{spec.unit ? ` ${spec.unit}` : ''}</Text>
                <Text style={styles.range}>{spec.min}–{spec.max}</Text>
            </View>
            <SliderTrack
                min={spec.min}
                max={spec.max}
                step={spec.step}
                value={value}
                onChange={setValue}
                disabled={disabled}
            />
            <Pressable
                onPress={submit}
                disabled={disabled}
                style={({ pressed }) => [
                    styles.submit,
                    disabled && styles.submitDisabled,
                    pressed && !disabled && styles.submitPressed,
                ]}
                accessibilityRole="button"
                accessibilityLabel={`Submit ${value}`}
            >
                <Text style={styles.submitText}>Submit · {value}{spec.unit ? ` ${spec.unit}` : ''}</Text>
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
    value: number;
    onChange: (v: number) => void;
    disabled?: boolean;
}

function SliderTrack({ min, max, step, value, onChange, disabled }: TrackProps) {
    if (Platform.OS === 'web') {
        // RN-Web View → div; we can mount a native HTML range input directly.
        return (
            <View style={styles.trackWeb}>
                {/* @ts-expect-error - native HTML element under RN-Web */}
                <input
                    type="range"
                    min={min}
                    max={max}
                    step={step}
                    value={value}
                    disabled={disabled}
                    onChange={(e: any) => onChange(Number(e.target.value))}
                    style={{
                        width: '100%',
                        height: 28,
                        accentColor: colors.foreground,
                        cursor: disabled ? 'not-allowed' : 'pointer',
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
        return (
            <View style={styles.trackNative}>
                <CommunitySlider
                    minimumValue={min}
                    maximumValue={max}
                    step={step}
                    value={value}
                    disabled={disabled}
                    onValueChange={(v: number) => onChange(v)}
                    minimumTrackTintColor={colors.foreground}
                    maximumTrackTintColor={colors.divider ?? '#d4d4d4'}
                    thumbTintColor={colors.foreground}
                    style={{ width: '100%', height: 32 }}
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
                    onPress={() => !disabled && onChange(s)}
                    style={({ pressed }) => [
                        styles.snap,
                        s === value && styles.snapActive,
                        pressed && styles.snapPressed,
                    ]}
                >
                    <Text style={[styles.snapText, s === value && styles.snapTextActive]}>{s}</Text>
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
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        borderRadius: 14,
        backgroundColor: colors.surface ?? '#f4f4f5',
        gap: spacing.sm,
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'baseline',
    },
    value: {
        fontSize: 28,
        fontWeight: '700',
        color: colors.foreground,
    },
    range: {
        fontSize: 12,
        color: colors.textSecondary ?? '#888',
    },
    trackWeb: {
        paddingVertical: spacing.xs,
    },
    trackNative: {
        paddingVertical: spacing.xs,
    },
    snapRow: {
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: 6,
        paddingVertical: spacing.xs,
    },
    snap: {
        paddingVertical: 6,
        paddingHorizontal: 12,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: colors.divider ?? '#d4d4d4',
        backgroundColor: 'transparent',
    },
    snapActive: {
        backgroundColor: colors.foreground,
        borderColor: colors.foreground,
    },
    snapPressed: {
        opacity: 0.7,
    },
    snapText: {
        fontSize: 13,
        color: colors.foreground,
    },
    snapTextActive: {
        color: colors.background ?? '#fff',
    },
    submit: {
        marginTop: spacing.xs,
        paddingVertical: spacing.sm + 2,
        paddingHorizontal: spacing.md,
        borderRadius: 999,
        backgroundColor: colors.foreground,
        alignItems: 'center',
    },
    submitPressed: {
        opacity: 0.85,
    },
    submitDisabled: {
        opacity: 0.4,
    },
    submitText: {
        color: colors.background ?? '#fff',
        fontWeight: '600',
        fontSize: 15,
    },
});
