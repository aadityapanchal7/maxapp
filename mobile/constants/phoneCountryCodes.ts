/**
 * Common dial codes for signup phone field (dropdown + national number).
 * dialCode is E.164 prefix including + (e.g. "+1", "+44").
 */
export type PhoneCountry = {
    name: string;
    dialCode: string;
    flag: string;
};

/** US/CA first, then alphabetical by name for the rest. */
export const PHONE_COUNTRIES: PhoneCountry[] = [
    { name: 'United States / Canada', dialCode: '+1', flag: '🇺🇸' },
    { name: 'United Kingdom', dialCode: '+44', flag: '🇬🇧' },
    { name: 'Australia', dialCode: '+61', flag: '🇦🇺' },
    { name: 'Brazil', dialCode: '+55', flag: '🇧🇷' },
    { name: 'China', dialCode: '+86', flag: '🇨🇳' },
    { name: 'France', dialCode: '+33', flag: '🇫🇷' },
    { name: 'Germany', dialCode: '+49', flag: '🇩🇪' },
    { name: 'India', dialCode: '+91', flag: '🇮🇳' },
    { name: 'Ireland', dialCode: '+353', flag: '🇮🇪' },
    { name: 'Italy', dialCode: '+39', flag: '🇮🇹' },
    { name: 'Japan', dialCode: '+81', flag: '🇯🇵' },
    { name: 'Mexico', dialCode: '+52', flag: '🇲🇽' },
    { name: 'Netherlands', dialCode: '+31', flag: '🇳🇱' },
    { name: 'New Zealand', dialCode: '+64', flag: '🇳🇿' },
    { name: 'Nigeria', dialCode: '+234', flag: '🇳🇬' },
    { name: 'Pakistan', dialCode: '+92', flag: '🇵🇰' },
    { name: 'Philippines', dialCode: '+63', flag: '🇵🇭' },
    { name: 'Poland', dialCode: '+48', flag: '🇵🇱' },
    { name: 'Russia', dialCode: '+7', flag: '🇷🇺' },
    { name: 'Saudi Arabia', dialCode: '+966', flag: '🇸🇦' },
    { name: 'Singapore', dialCode: '+65', flag: '🇸🇬' },
    { name: 'South Africa', dialCode: '+27', flag: '🇿🇦' },
    { name: 'South Korea', dialCode: '+82', flag: '🇰🇷' },
    { name: 'Spain', dialCode: '+34', flag: '🇪🇸' },
    { name: 'Sweden', dialCode: '+46', flag: '🇸🇪' },
    { name: 'Switzerland', dialCode: '+41', flag: '🇨🇭' },
    { name: 'United Arab Emirates', dialCode: '+971', flag: '🇦🇪' },
];

/** Match stored E.164 against known dial codes (longest prefix wins). */
export function parseE164WithKnownCountries(
    raw: string | null | undefined,
): { country: PhoneCountry; nationalDigits: string } | null {
    const allDigits = (raw || '').replace(/\D/g, '');
    if (!allDigits) return null;
    const byDialLen = [...PHONE_COUNTRIES].sort(
        (a, b) => b.dialCode.replace(/\D/g, '').length - a.dialCode.replace(/\D/g, '').length,
    );
    for (const c of byDialLen) {
        const dc = c.dialCode.replace(/\D/g, '');
        if (dc && allDigits.startsWith(dc)) {
            return { country: c, nationalDigits: allDigits.slice(dc.length) };
        }
    }
    return null;
}
