import React, { useEffect, useState } from 'react';
import { Text, StyleSheet, TextStyle } from 'react-native';
import { colors } from '../theme/dark';

export type ChatTypingMode = 'default' | 'schedule';

type Props = {
  mode?: ChatTypingMode;
  style?: TextStyle;
};

/**
 * Animated trailing dots. "schedule" mode for maxx schedule generation waits;
 * "default" is generic chat typing.
 */
export function ChatTypingIndicator({ mode = 'default', style }: Props) {
  const [dots, setDots] = useState('');
  useEffect(() => {
    const id = setInterval(() => setDots((d) => (d.length >= 3 ? '' : `${d}.`)), 400);
    return () => clearInterval(id);
  }, []);
  const label = mode === 'schedule' ? 'Generating schedule' : 'typing';
  return (
    <Text style={[styles.text, style]}>
      {label}
      {dots}
    </Text>
  );
}

const styles = StyleSheet.create({
  text: { fontSize: 14, color: colors.textMuted, fontStyle: 'italic' },
});
