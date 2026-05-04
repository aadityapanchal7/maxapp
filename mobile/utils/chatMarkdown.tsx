/**
 * Tiny markdown renderer for chat bubbles.
 *
 * Handles ONLY the syntax the backend actually emits:
 *   **bold**          → <Text fontWeight=700>bold</Text>
 *   *italic*          → <Text fontStyle=italic>italic</Text> (very light — only when not a list bullet)
 *   `code`            → monospace inline
 *   ### Heading       → larger bold heading line (no hash sign)
 *   ## Subheading     → bold heading
 *   # Heading         → bold heading
 *   - bullet          → indented bullet line
 *   1. numbered       → indented number line
 *   [text](url)       → tappable link
 *   bare http(s)://   → tappable link
 *
 * NOT a real CommonMark parser. Single-line, single-pass, regex-based.
 * That's deliberate — full markdown libs are 50–100kb and we only need
 * a fraction of the syntax.
 */

import React from 'react';
import { Text, View, StyleSheet, type TextStyle } from 'react-native';

export interface RenderOpts {
    baseStyle: any;
    onLinkPress: (url: string) => void;
    /** Optional override for headings — defaults to a slightly larger bold line. */
    headingStyle?: TextStyle;
    /** Optional override for the contrast color when the bubble is dark (user). */
    isOnDark?: boolean;
}

const URL_TOKEN_RE = /(\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s)]+)/g;
const MD_LINK_RE = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/;
const BARE_URL_RE = /^https?:\/\//;
const BOLD_RE = /\*\*([^*]+)\*\*/g;
const CODE_RE = /`([^`]+)`/g;

/** Render a multi-line markdown-ish string into a React element tree. */
export function renderRichText(text: string, opts: RenderOpts): React.ReactNode {
    if (!text) return null;
    const lines = text.split('\n');
    return (
        <View>
            {lines.map((line, i) => renderLine(line, i, opts))}
        </View>
    );
}

function renderLine(line: string, key: number, opts: RenderOpts): React.ReactNode {
    const trimmed = line.trim();

    // Headings — strip the # marks and apply a heading style.
    let headingMatch = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (headingMatch) {
        const level = headingMatch[1].length;
        const text = headingMatch[2];
        const style =
            level === 1 ? styles.h1
            : level === 2 ? styles.h2
            : styles.h3;
        return (
            <Text key={key} style={[opts.baseStyle, style, opts.headingStyle]}>
                {renderInline(text, opts, key)}
            </Text>
        );
    }

    // Blank line → spacer.
    if (!trimmed) {
        return <View key={key} style={styles.blankLine} />;
    }

    // Bullet list.
    let bulletMatch = /^[-*•]\s+(.*)$/.exec(trimmed);
    if (bulletMatch) {
        return (
            <View key={key} style={styles.bulletRow}>
                <Text style={[opts.baseStyle, styles.bulletDot]}>•</Text>
                <Text style={[opts.baseStyle, styles.bulletText]}>
                    {renderInline(bulletMatch[1], opts, key)}
                </Text>
            </View>
        );
    }

    // Numbered list (1. text, 2) text, etc.).
    let numMatch = /^(\d{1,2})[.)]\s+(.*)$/.exec(trimmed);
    if (numMatch) {
        return (
            <View key={key} style={styles.bulletRow}>
                <Text style={[opts.baseStyle, styles.numIdx]}>{numMatch[1]}.</Text>
                <Text style={[opts.baseStyle, styles.bulletText]}>
                    {renderInline(numMatch[2], opts, key)}
                </Text>
            </View>
        );
    }

    // Default paragraph line.
    return (
        <Text key={key} style={opts.baseStyle}>
            {renderInline(line, opts, key)}
        </Text>
    );
}

/** Render inline spans: bold, code, and links. Returns an array of Text nodes. */
function renderInline(text: string, opts: RenderOpts, parentKey: number): React.ReactNode {
    // First split on URL tokens so we can wrap them in tappable Text spans.
    const urlParts = text.split(URL_TOKEN_RE);
    const out: React.ReactNode[] = [];
    let nodeIdx = 0;

    for (const part of urlParts) {
        if (!part) continue;
        const mdLink = MD_LINK_RE.exec(part);
        if (mdLink) {
            out.push(
                <Text
                    key={`${parentKey}-l-${nodeIdx++}`}
                    style={styles.linkText}
                    onPress={() => opts.onLinkPress(mdLink[2])}
                >
                    {mdLink[1]}
                </Text>
            );
            continue;
        }
        if (BARE_URL_RE.test(part)) {
            out.push(
                <Text
                    key={`${parentKey}-l-${nodeIdx++}`}
                    style={styles.linkText}
                    onPress={() => opts.onLinkPress(part)}
                >
                    {part}
                </Text>
            );
            continue;
        }
        // Otherwise render bold + code inline within this segment.
        out.push(...renderBoldAndCode(part, `${parentKey}-${nodeIdx++}`));
    }
    return out;
}

/** Walk a string and produce Text nodes with **bold** and `code` styling. */
function renderBoldAndCode(text: string, keyPrefix: string): React.ReactNode[] {
    // Combine bold + code into a single tokenizer pass so they don't fight.
    const tokens: { type: 'plain' | 'bold' | 'code'; text: string }[] = [];
    let cursor = 0;
    const combined = /\*\*([^*]+)\*\*|`([^`]+)`/g;
    let m: RegExpExecArray | null;
    while ((m = combined.exec(text)) !== null) {
        if (m.index > cursor) {
            tokens.push({ type: 'plain', text: text.slice(cursor, m.index) });
        }
        if (m[1] !== undefined) {
            tokens.push({ type: 'bold', text: m[1] });
        } else if (m[2] !== undefined) {
            tokens.push({ type: 'code', text: m[2] });
        }
        cursor = m.index + m[0].length;
    }
    if (cursor < text.length) {
        tokens.push({ type: 'plain', text: text.slice(cursor) });
    }
    if (!tokens.length) {
        return [<Text key={keyPrefix}>{text}</Text>];
    }
    return tokens.map((tok, i) => {
        if (tok.type === 'bold') {
            return <Text key={`${keyPrefix}-${i}`} style={styles.bold}>{tok.text}</Text>;
        }
        if (tok.type === 'code') {
            return <Text key={`${keyPrefix}-${i}`} style={styles.code}>{tok.text}</Text>;
        }
        return <Text key={`${keyPrefix}-${i}`}>{tok.text}</Text>;
    });
}

const styles = StyleSheet.create({
    h1: { fontSize: 18, fontWeight: '700', marginTop: 6, marginBottom: 2 },
    h2: { fontSize: 16, fontWeight: '700', marginTop: 6, marginBottom: 2 },
    h3: { fontSize: 15, fontWeight: '700', marginTop: 4, marginBottom: 2 },
    blankLine: { height: 6 },
    bold: { fontWeight: '700' },
    code: { fontFamily: 'Menlo', fontSize: 13, backgroundColor: 'rgba(0,0,0,0.06)', paddingHorizontal: 4, borderRadius: 4 },
    bulletRow: { flexDirection: 'row', gap: 8, paddingLeft: 4, marginVertical: 1 },
    bulletDot: { lineHeight: 22, width: 12 },
    numIdx: { lineHeight: 22, width: 18, fontWeight: '600' },
    bulletText: { flex: 1 },
    linkText: { textDecorationLine: 'underline' },
});
