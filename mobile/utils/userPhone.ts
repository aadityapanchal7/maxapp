/** True if user has enough digits on file to use for SMS / Sendblue (signup or profile). */
export function userHasSignupPhone(user: { phone_number?: string } | null | undefined): boolean {
    const p = user?.phone_number?.trim();
    if (!p) return false;
    const digits = p.replace(/\D/g, '');
    return digits.length >= 10;
}
