import type { PhoneCountry } from '../constants/phoneCountryCodes';

/**
 * Single field for email, username, or national / formatted phone.
 * Phone uses selected country dial code + digits from input.
 */
export function buildLoginIdentifier(raw: string, phoneCountry: PhoneCountry): string {
    const t = raw.trim();
    if (!t) return '';
    if (t.includes('@')) return t.toLowerCase();
    if (/^[a-zA-Z0-9_]+$/.test(t) && !/^\d+$/.test(t)) return t.toLowerCase();
    const digits = t.replace(/\D/g, '');
    if (digits.length >= 7) return phoneCountry.dialCode + digits;
    return t.toLowerCase();
}

/** E.164-style number for SMS reset (national digits + selected dial code). */
export function buildFullPhoneNational(nationalRaw: string, phoneCountry: PhoneCountry): string {
    const digits = nationalRaw.replace(/\D/g, '');
    if (digits.length < 7) return '';
    return phoneCountry.dialCode + digits;
}
