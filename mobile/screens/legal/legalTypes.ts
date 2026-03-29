/** Structured legal copy — no cross-links between in-app legal pages; external URLs + mailto only. */
export type LegalBlock =
    | { type: 'meta'; text: string }
    | { type: 'h2'; text: string }
    | { type: 'h3'; text: string }
    | { type: 'p'; text: string }
    | { type: 'bullets'; items: string[] }
    | { type: 'callout'; title?: string; text: string }
    /** Opens in browser (Apple docs, etc.) */
    | { type: 'external'; label: string; url: string }
    /** Inline: before + tappable email + after */
    | { type: 'mailtoLine'; before: string; after?: string };
