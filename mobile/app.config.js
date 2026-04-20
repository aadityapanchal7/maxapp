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
    const communityGuidelinesUrl = process.env.EXPO_PUBLIC_COMMUNITY_GUIDELINES_URL;
    const cookieNoticeUrl = process.env.EXPO_PUBLIC_COOKIE_NOTICE_URL;
    const stripePublishableKey = process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY;
    const buildPlatform =
        process.env.EAS_BUILD_PLATFORM ||
        process.env.EXPO_OS ||
        process.env.PLATFORM ||
        '';
    const isIosBuild = buildPlatform === 'ios';
    const plugins = Array.isArray(ex.plugins) ? ex.plugins : [];
    const filteredPlugins = isIosBuild
        ? plugins.filter((plugin) => {
            const name = Array.isArray(plugin) ? plugin[0] : plugin;
            return name !== '@stripe/stripe-react-native';
        })
        : plugins;

    return {
        expo: {
            ...ex,
            plugins: filteredPlugins,
            extra: {
                ...baseExtra,
                supportEmail: supportEmail || baseExtra.supportEmail,
                privacyPolicyUrl: privacyPolicyUrl || baseExtra.privacyPolicyUrl,
                termsOfServiceUrl: termsOfServiceUrl || baseExtra.termsOfServiceUrl,
                communityGuidelinesUrl: communityGuidelinesUrl || baseExtra.communityGuidelinesUrl,
                cookieNoticeUrl: cookieNoticeUrl || baseExtra.cookieNoticeUrl,
                stripePublishableKey: stripePublishableKey || baseExtra.stripePublishableKey || '',
            },
        },
    };
};
