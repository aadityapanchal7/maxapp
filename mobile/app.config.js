/**
 * Merges app.json with optional build-time env for App Store–required URLs and support email.
 * Set in EAS Dashboard → Secrets, or a local .env loaded by EAS, or: EXPO_PUBLIC_* before `eas build`.
 */
// eslint-disable-next-line @typescript-eslint/no-var-requires
const appJson = require('./app.json');

module.exports = () => {
    const ex = appJson.expo;
    const baseExtra = ex.extra || {};
    const supportEmail = process.env.EXPO_PUBLIC_SUPPORT_EMAIL;
    const privacyPolicyUrl = process.env.EXPO_PUBLIC_PRIVACY_POLICY_URL;
    const termsOfServiceUrl = process.env.EXPO_PUBLIC_TERMS_URL;

    return {
        expo: {
            ...ex,
            extra: {
                ...baseExtra,
                supportEmail: supportEmail || baseExtra.supportEmail,
                privacyPolicyUrl: privacyPolicyUrl || baseExtra.privacyPolicyUrl,
                termsOfServiceUrl: termsOfServiceUrl || baseExtra.termsOfServiceUrl,
            },
        },
    };
};
